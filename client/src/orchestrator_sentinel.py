"""Shell-bridge dispatcher for OS-APOW.

This module provides the interface between the webhook notifier and the
devcontainer-based opencode orchestration system. It dispatches work items
to the shell-bridge for processing by AI agents.

Integration with scripts/devcontainer-opencode.sh:
- Uses 'prompt' command to dispatch work to the agent
- Passes assembled prompt files via -f flag
- Manages environment variables for API keys
- Monitors execution status and results
"""

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


class WorkItemStatus(str, Enum):
    """Status of a work item in the queue."""

    PENDING = "pending"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DispatchError(Exception):
    """Error during shell-bridge dispatch."""

    pass


@dataclass
class ShellBridgeConfig:
    """Configuration for the shell-bridge dispatcher.

    Attributes:
        workspace_folder: Path to the repository workspace
        devcontainer_config: Path to devcontainer.json
        opencode_server_url: URL of the opencode server
        opencode_server_dir: Working directory inside the container
        script_path: Path to devcontainer-opencode.sh
        api_keys: Dictionary of API key environment variable names to values
    """

    workspace_folder: Path = field(default_factory=lambda: Path.cwd())
    devcontainer_config: str = ".devcontainer/devcontainer.json"
    opencode_server_url: str = "http://127.0.0.1:4096"
    opencode_server_dir: str | None = None
    script_path: str = "scripts/devcontainer-opencode.sh"
    api_keys: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Resolve paths after initialization."""
        if isinstance(self.workspace_folder, str):
            self.workspace_folder = Path(self.workspace_folder)

        # Derive server-side directory from workspace basename if not set
        if self.opencode_server_dir is None:
            self.opencode_server_dir = f"/workspaces/{self.workspace_folder.name}"


@dataclass
class WorkItem:
    """Represents a work item to be dispatched to the orchestration system.

    Attributes:
        id: Unique identifier for the work item
        event_type: Type of event (e.g., 'issues', 'pull_request')
        action: Action within the event (e.g., 'labeled', 'opened')
        payload: Raw event payload data
        status: Current status of the work item
        prompt_file: Path to the assembled prompt file (if dispatched)
        result: Result of the dispatch (if completed)
        error: Error message (if failed)
    """

    id: str
    event_type: str
    action: str | None
    payload: dict[str, Any]
    status: WorkItemStatus = WorkItemStatus.PENDING
    prompt_file: Path | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_prompt_content(self) -> str:
        """Generate prompt content from the work item.

        Returns:
            Formatted prompt string for the orchestrator agent
        """
        return json.dumps(
            {
                "event_type": self.event_type,
                "action": self.action,
                "payload": self.payload,
                "work_item_id": self.id,
            },
            indent=2,
        )


class OrchestratorSentinel:
    """Shell-bridge dispatcher for the orchestration system.

    This class manages the dispatch of work items to the devcontainer-based
    opencode orchestration system via the shell-bridge interface.

    Example:
        ```python
        config = ShellBridgeConfig(
            workspace_folder=Path("/path/to/repo"),
            api_keys={
                "ZHIPU_API_KEY": os.environ["ZHIPU_API_KEY"],
                "GH_ORCHESTRATION_AGENT_TOKEN": os.environ["GH_TOKEN"],
            },
        )
        sentinel = OrchestratorSentinel(config)

        work_item = WorkItem(
            id="issue-123",
            event_type="issues",
            action="labeled",
            payload={"issue": {"number": 123}},
        )

        await sentinel.dispatch(work_item)
        ```
    """

    def __init__(self, config: ShellBridgeConfig) -> None:
        """Initialize the orchestrator sentinel.

        Args:
            config: Configuration for the shell-bridge dispatcher
        """
        self.config = config
        self._work_queue: asyncio.Queue[WorkItem] = asyncio.Queue()
        self._pending_items: dict[str, WorkItem] = {}
        logger.info(
            "orchestrator_sentinel_initialized",
            workspace=str(config.workspace_folder),
            server_url=config.opencode_server_url,
        )

    async def dispatch(self, work_item: WorkItem) -> WorkItemStatus:
        """Dispatch a work item to the orchestration system.

        Args:
            work_item: The work item to dispatch

        Returns:
            The status of the work item after dispatch

        Raises:
            DispatchError: If the dispatch fails
        """
        logger.info(
            "dispatching_work_item",
            work_item_id=work_item.id,
            event_type=work_item.event_type,
            action=work_item.action,
        )

        work_item.status = WorkItemStatus.DISPATCHED
        self._pending_items[work_item.id] = work_item

        try:
            # Write prompt file
            prompt_content = work_item.to_prompt_content()
            prompt_file = (
                self.config.workspace_folder / ".work-queue" / f"{work_item.id}.prompt.json"
            )
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text(prompt_content)
            work_item.prompt_file = prompt_file

            logger.debug("prompt_file_written", path=str(prompt_file))

            # Execute dispatch via shell-bridge
            work_item.status = WorkItemStatus.RUNNING
            result = await self._execute_dispatch(prompt_file)

            work_item.result = result
            work_item.status = WorkItemStatus.COMPLETED
            logger.info(
                "work_item_completed",
                work_item_id=work_item.id,
            )

        except Exception as e:
            work_item.status = WorkItemStatus.FAILED
            work_item.error = str(e)
            logger.error(
                "work_item_failed",
                work_item_id=work_item.id,
                error=str(e),
            )
            raise DispatchError(f"Failed to dispatch work item {work_item.id}: {e}") from e

        finally:
            # Cleanup pending items
            self._pending_items.pop(work_item.id, None)

        return work_item.status

    async def _execute_dispatch(self, prompt_file: Path) -> dict[str, Any]:
        """Execute the dispatch via the shell-bridge.

        Args:
            prompt_file: Path to the assembled prompt file

        Returns:
            Result dictionary from the dispatch

        Raises:
            DispatchError: If the dispatch command fails
        """
        # Build environment with API keys
        env = os.environ.copy()
        env.update(self.config.api_keys)

        # Build command
        cmd = [
            "bash",
            self.config.script_path,
            "prompt",
            "-c",
            self.config.devcontainer_config,
            "-w",
            str(self.config.workspace_folder),
            "-f",
            str(prompt_file),
            "-u",
            self.config.opencode_server_url,
        ]

        if self.config.opencode_server_dir:
            cmd.extend(["-d", self.config.opencode_server_dir])

        logger.debug("executing_dispatch_command", command=" ".join(cmd))

        # Run the dispatch command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=str(self.config.workspace_folder),
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode() or stdout.decode()
            raise DispatchError(
                f"Dispatch command failed with code {process.returncode}: {error_msg}"
            )

        return {
            "returncode": process.returncode,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
        }

    async def queue_work_item(self, work_item: WorkItem) -> None:
        """Add a work item to the queue for processing.

        Args:
            work_item: The work item to queue
        """
        await self._work_queue.put(work_item)
        logger.info(
            "work_item_queued",
            work_item_id=work_item.id,
            queue_size=self._work_queue.qsize(),
        )

    async def process_queue(self) -> None:
        """Process work items from the queue continuously.

        This method runs indefinitely, processing work items as they are
        added to the queue.
        """
        logger.info("queue_processor_started")

        while True:
            work_item = await self._work_queue.get()
            try:
                await self.dispatch(work_item)
            except DispatchError:
                # Error already logged in dispatch()
                pass
            finally:
                self._work_queue.task_done()

    def get_status(self, work_item_id: str) -> WorkItemStatus | None:
        """Get the status of a work item.

        Args:
            work_item_id: The ID of the work item

        Returns:
            The status of the work item, or None if not found
        """
        item = self._pending_items.get(work_item_id)
        return item.status if item else None


# Interface definition for work queue implementations
class IWorkQueue:
    """Interface for work queue implementations.

    This interface defines the contract for work queue backends
    that can be used with the orchestrator sentinel.
    """

    async def enqueue(self, work_item: WorkItem) -> None:
        """Add a work item to the queue.

        Args:
            work_item: The work item to enqueue
        """
        raise NotImplementedError

    async def dequeue(self) -> WorkItem:
        """Remove and return the next work item from the queue.

        Returns:
            The next work item to process
        """
        raise NotImplementedError

    async def peek(self) -> WorkItem | None:
        """Return the next work item without removing it.

        Returns:
            The next work item, or None if the queue is empty
        """
        raise NotImplementedError

    async def size(self) -> int:
        """Return the number of items in the queue.

        Returns:
            The queue size
        """
        raise NotImplementedError

    async def is_empty(self) -> bool:
        """Check if the queue is empty.

        Returns:
            True if the queue is empty, False otherwise
        """
        raise NotImplementedError
