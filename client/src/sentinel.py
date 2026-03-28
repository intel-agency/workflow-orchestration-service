"""
OS-APOW Sentinel Orchestrator

Persistent background service that polls GitHub for issues labeled
'agent:queued', claims them via assign-then-verify locking, and
dispatches orchestration prompts to a remote opencode server via
the devcontainer-opencode.sh shell bridge.

Adapted from plan_docs/orchestrator_sentinel.py for the standalone
client/server architecture.
"""

import asyncio
import os
import signal
import subprocess
import random
import uuid
import logging
import sys
from typing import List, Optional

import httpx

from src.models.work_item import TaskType, WorkItemStatus, WorkItem
from src.queue.github_queue import GitHubQueue
from src.config import (
    OPENCODE_SERVER_URL,
    OPENCODE_SERVER_DIR,
    POLL_INTERVAL,
    MAX_BACKOFF,
    HEARTBEAT_INTERVAL,
    SUBPROCESS_TIMEOUT,
    SENTINEL_BOT_LOGIN,
    SHELL_BRIDGE_PATH,
    GITHUB_TOKEN,
    GITHUB_ORG,
    GITHUB_REPO,
)

SENTINEL_ID = f"sentinel-{uuid.uuid4().hex[:8]}"

# Setup Structured Logging
logging.basicConfig(
    level=logging.INFO,
    format=f"%(asctime)s [%(levelname)s] {SENTINEL_ID} - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("OS-APOW-Sentinel")

# Graceful shutdown flag (R-4)
_shutdown_requested = False


def _handle_signal(signum, frame):
    """Set shutdown flag on SIGTERM/SIGINT so the current task can finish."""
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name} — will shut down after current task finishes")
    _shutdown_requested = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


# --- Shell Bridge Interface ---


async def run_shell_command(
    args: List[str], timeout: Optional[int] = None
) -> subprocess.CompletedProcess:
    """Invokes the local shell bridge (devcontainer-opencode.sh).

    Args:
        args: Command and arguments.
        timeout: Maximum seconds to wait. None = no limit.
    """
    try:
        logger.info(f"Executing Bridge: {' '.join(args)}")
        process = await asyncio.create_subprocess_exec(
            *args, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Shell command timed out after {timeout}s — killing")
            process.kill()
            stdout, stderr = await process.communicate()
            return subprocess.CompletedProcess(
                args=args,
                returncode=-1,
                stdout=stdout.decode().strip() if stdout else "",
                stderr=f"TIMEOUT after {timeout}s\n"
                + (stderr.decode().strip() if stderr else ""),
            )

        return subprocess.CompletedProcess(
            args=args,
            returncode=process.returncode,
            stdout=stdout.decode().strip() if stdout else "",
            stderr=stderr.decode().strip() if stderr else "",
        )
    except Exception as e:
        logger.error(f"Critical shell execution error: {str(e)}")
        raise


# --- Orchestration Logic ---


class Sentinel:
    def __init__(self, queue: GitHubQueue):
        self.queue = queue
        self._current_backoff = POLL_INTERVAL

    async def _check_server_health(self) -> bool:
        """Verify the orchestration server is reachable before dispatching."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{OPENCODE_SERVER_URL}/")
                return resp.status_code == 200
        except Exception as exc:
            logger.warning(f"Server health check failed: {exc}")
            return False

    async def _heartbeat_loop(self, item: WorkItem, start_time: float):
        """Post periodic heartbeat comments while a task is running."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            elapsed = int(asyncio.get_event_loop().time() - start_time)
            await self.queue.post_heartbeat(item, SENTINEL_ID, elapsed)

    async def process_task(self, item: WorkItem):
        logger.info(f"Processing Task #{item.issue_number}...")
        start_time = asyncio.get_event_loop().time()

        # Launch heartbeat as a background task (R-1)
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(item, start_time))

        try:
            # Health check — verify the remote server is reachable
            if not await self._check_server_health():
                err = (
                    f"❌ **Infrastructure Failure**: Orchestration server at "
                    f"`{OPENCODE_SERVER_URL}` is not reachable."
                )
                await self.queue.update_status(item, WorkItemStatus.INFRA_FAILURE, err)
                return

            # Build prompt instruction from the work item
            workflow_map = {
                TaskType.PLAN: "create-app-plan.md",
                TaskType.IMPLEMENT: "perform-task.md",
                TaskType.BUGFIX: "recover-from-error.md",
            }
            workflow = workflow_map.get(item.task_type, "perform-task.md")
            instruction = f"Execute workflow {workflow} for context: {item.source_url}"

            # Dispatch to remote server via shell bridge
            res_prompt = await run_shell_command(
                [
                    SHELL_BRIDGE_PATH,
                    "prompt",
                    "-p",
                    instruction,
                    "-u",
                    OPENCODE_SERVER_URL,
                    "-d",
                    OPENCODE_SERVER_DIR,
                ],
                timeout=SUBPROCESS_TIMEOUT,
            )

            # Handle completion
            if res_prompt.returncode == 0:
                success_msg = (
                    f"✅ **Workflow Complete**\n"
                    f"Sentinel successfully executed `{workflow}`. "
                    f"Please review Pull Requests."
                )
                await self.queue.update_status(
                    item, WorkItemStatus.SUCCESS, success_msg
                )
            else:
                log_tail = (
                    res_prompt.stderr[-1500:]
                    if res_prompt.stderr
                    else "No error output captured."
                )
                fail_msg = f"❌ **Execution Error** during `{workflow}`:\n```\n...{log_tail}\n```"
                await self.queue.update_status(item, WorkItemStatus.ERROR, fail_msg)

        except Exception as e:
            logger.exception(f"Internal Sentinel Error on Task #{item.issue_number}")
            await self.queue.update_status(
                item,
                WorkItemStatus.INFRA_FAILURE,
                f"🚨 Sentinel encountered an unhandled exception: {str(e)}",
            )
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    async def run_forever(self):
        logger.info(
            f"Sentinel {SENTINEL_ID} entering polling loop "
            f"(interval: {POLL_INTERVAL}s, server: {OPENCODE_SERVER_URL})"
        )

        while not _shutdown_requested:
            try:
                tasks = await self.queue.fetch_queued_tasks()
                if tasks:
                    logger.info(f"Found {len(tasks)} queued task(s).")
                    for task in tasks:
                        if _shutdown_requested:
                            break
                        if await self.queue.claim_task(
                            task, SENTINEL_ID, SENTINEL_BOT_LOGIN
                        ):
                            await self.process_task(task)
                            break

                # Reset backoff on successful poll (I-3)
                self._current_backoff = POLL_INTERVAL

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in (403, 429):
                    # Jittered exponential backoff (I-3)
                    jitter = random.uniform(0, self._current_backoff * 0.1)
                    wait = min(self._current_backoff + jitter, MAX_BACKOFF)
                    logger.warning(f"Rate limited ({status}) — backing off {wait:.0f}s")
                    self._current_backoff = min(self._current_backoff * 2, MAX_BACKOFF)
                    await asyncio.sleep(wait)
                    continue
                else:
                    logger.error(f"GitHub API error: {exc}")
            except Exception as e:
                logger.error(f"Polling cycle error: {str(e)}")

            await asyncio.sleep(self._current_backoff)

        logger.info("Shutdown flag set — exiting polling loop")


# --- Entry Point ---


async def _main():
    required = {"GITHUB_TOKEN": GITHUB_TOKEN, "GITHUB_ORG": GITHUB_ORG, "GITHUB_REPO": GITHUB_REPO}
    missing = [k for k, v in required.items() if not v]
    if missing:
        logger.error(
            f"Critical Error: Missing environment variables: {', '.join(missing)}"
        )
        sys.exit(1)

    if not SENTINEL_BOT_LOGIN:
        logger.warning(
            "SENTINEL_BOT_LOGIN is not set — assign-then-verify locking is disabled. "
            "Set it to the GitHub login of the bot account for concurrency safety (R-2)."
        )

    gh_queue = GitHubQueue(GITHUB_TOKEN, GITHUB_ORG, GITHUB_REPO)
    sentinel = Sentinel(gh_queue)

    try:
        await sentinel.run_forever()
    finally:
        await gh_queue.close()
        logger.info("Sentinel shut down.")


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        logger.info("Sentinel shutting down gracefully.")
