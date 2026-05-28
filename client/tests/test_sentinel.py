"""
Unit tests for client/src/sentinel.py — D3 adaptation verification.

Coverage:
  - _check_server_health: returns True on HTTP 200, False on ConnectError,
    False on ReadTimeout (VAL-SEN-001)
  - Failed health check causes process_task to skip the shell bridge (VAL-SEN-002)
  - Shell bridge argv includes -u / -d and has no up / start stages (VAL-SEN-010)
  - The value passed to -u matches OPENCODE_SERVER_URL (VAL-SEN-011)
  - Heartbeat loop passes OPENCODE_SERVER_URL to post_heartbeat (VAL-SEN-022)
  - --once flag exits run_forever after one pass
"""

from __future__ import annotations

import asyncio
import contextlib
import subprocess
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest
import respx

from src.models.work_item import TaskType, WorkItem, WorkItemStatus
from src.sentinel import Sentinel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_SERVER_URL = "http://test-sentinel-server:9999"
_FAKE_SERVER_DIR = "/opt/test-orchestration"
_FAKE_BRIDGE_PATH = "/usr/local/bin/devcontainer-opencode.sh"


def _make_work_item(issue_number: int = 42) -> WorkItem:
    """Build a minimal WorkItem suitable for unit tests."""
    return WorkItem(
        id=str(issue_number),
        issue_number=issue_number,
        source_url=f"https://github.com/org/repo/issues/{issue_number}",
        context_body="Do the thing",
        target_repo_slug="org/repo",
        task_type=TaskType.IMPLEMENT,
        status=WorkItemStatus.QUEUED,
        node_id="NODE_FAKE",
    )


def _make_queue() -> AsyncMock:
    """Return an AsyncMock that quacks like GitHubQueue."""
    queue = AsyncMock()
    queue.post_heartbeat = AsyncMock()
    queue.update_status = AsyncMock()
    queue.claim_task = AsyncMock(return_value=True)
    queue.fetch_queued_tasks = AsyncMock(return_value=[])
    queue.close = AsyncMock()
    return queue


def _ok_result(args: list) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=args, returncode=0, stdout="done", stderr="")


# ---------------------------------------------------------------------------
# _check_server_health — VAL-SEN-001
# ---------------------------------------------------------------------------


class TestCheckServerHealth:
    """Health probe: _check_server_health() returns True/False correctly."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_true_on_200(self) -> None:
        """HTTP 200 response → server is healthy → returns True."""
        respx.get(f"{_FAKE_SERVER_URL}/").mock(return_value=httpx.Response(200))
        with patch("src.sentinel.OPENCODE_SERVER_URL", _FAKE_SERVER_URL):
            sentinel = Sentinel(_make_queue())
            result = await sentinel._check_server_health()
        assert result is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_true_on_other_2xx(self) -> None:
        """HTTP 204 response → still healthy (any 2xx is accepted)."""
        respx.get(f"{_FAKE_SERVER_URL}/").mock(return_value=httpx.Response(204))
        with patch("src.sentinel.OPENCODE_SERVER_URL", _FAKE_SERVER_URL):
            sentinel = Sentinel(_make_queue())
            result = await sentinel._check_server_health()
        assert result is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_false_on_connect_error(self) -> None:
        """ConnectError → server unreachable → returns False."""
        respx.get(f"{_FAKE_SERVER_URL}/").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        with patch("src.sentinel.OPENCODE_SERVER_URL", _FAKE_SERVER_URL):
            sentinel = Sentinel(_make_queue())
            result = await sentinel._check_server_health()
        assert result is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_false_on_read_timeout(self) -> None:
        """ReadTimeout → server unreachable → returns False."""
        respx.get(f"{_FAKE_SERVER_URL}/").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )
        with patch("src.sentinel.OPENCODE_SERVER_URL", _FAKE_SERVER_URL):
            sentinel = Sentinel(_make_queue())
            result = await sentinel._check_server_health()
        assert result is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_false_on_server_error(self) -> None:
        """HTTP 503 → non-2xx → returns False."""
        respx.get(f"{_FAKE_SERVER_URL}/").mock(return_value=httpx.Response(503))
        with patch("src.sentinel.OPENCODE_SERVER_URL", _FAKE_SERVER_URL):
            sentinel = Sentinel(_make_queue())
            result = await sentinel._check_server_health()
        assert result is False


# ---------------------------------------------------------------------------
# Failed health probe skips shell bridge — VAL-SEN-002
# ---------------------------------------------------------------------------


class TestHealthProbeFailSkipsBridge:
    """When _check_server_health returns False, process_task must not invoke the shell bridge."""

    @pytest.mark.asyncio
    async def test_health_fail_skips_shell_bridge(self) -> None:
        """run_shell_command is never called when health check returns False."""
        queue = _make_queue()
        sentinel = Sentinel(queue)
        item = _make_work_item()

        with patch.object(sentinel, "_check_server_health", return_value=False):
            with patch("src.sentinel.run_shell_command", new_callable=AsyncMock) as mock_bridge:
                await sentinel.process_task(item)

        mock_bridge.assert_not_called()

    @pytest.mark.asyncio
    async def test_health_fail_updates_status_to_infra_failure(self) -> None:
        """On health probe failure, update_status is called with INFRA_FAILURE."""
        queue = _make_queue()
        sentinel = Sentinel(queue)
        item = _make_work_item()

        with patch.object(sentinel, "_check_server_health", return_value=False):
            with patch("src.sentinel.run_shell_command", new_callable=AsyncMock):
                await sentinel.process_task(item)

        queue.update_status.assert_called_once()
        _item, status, _msg = queue.update_status.call_args[0]
        assert status == WorkItemStatus.INFRA_FAILURE


# ---------------------------------------------------------------------------
# Shell bridge argv composition — VAL-SEN-010, VAL-SEN-011
# ---------------------------------------------------------------------------


class TestShellBridgeArgv:
    """D3 enforcement: argv must include -u/-d flags and must not include up/start stages."""

    async def _capture_argv(
        self,
        server_url: str = _FAKE_SERVER_URL,
        server_dir: str = _FAKE_SERVER_DIR,
        bridge_path: str = _FAKE_BRIDGE_PATH,
    ) -> list[str]:
        """Run process_task with a healthy mock server and capture argv."""
        queue = _make_queue()
        sentinel = Sentinel(queue)
        item = _make_work_item()
        captured: list[list[str]] = []

        async def mock_shell_command(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
            captured.append(list(args))
            return _ok_result(args)

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                patch.object(sentinel, "_check_server_health", return_value=True)
            )
            stack.enter_context(patch("src.sentinel.OPENCODE_SERVER_URL", server_url))
            stack.enter_context(patch("src.sentinel.OPENCODE_SERVER_DIR", server_dir))
            stack.enter_context(patch("src.sentinel.SHELL_BRIDGE_PATH", bridge_path))
            stack.enter_context(
                patch("src.sentinel.run_shell_command", side_effect=mock_shell_command)
            )
            await sentinel.process_task(item)

        assert captured, "run_shell_command was not called"
        return captured[0]

    @pytest.mark.asyncio
    async def test_argv_contains_prompt_subcommand(self) -> None:
        """The shell bridge must be called with the 'prompt' subcommand."""
        argv = await self._capture_argv()
        assert "prompt" in argv

    @pytest.mark.asyncio
    async def test_argv_has_u_flag_with_server_url(self) -> None:
        """Shell bridge argv must include -u <OPENCODE_SERVER_URL>."""
        argv = await self._capture_argv(server_url=_FAKE_SERVER_URL)
        assert "-u" in argv
        idx = argv.index("-u")
        assert argv[idx + 1] == _FAKE_SERVER_URL

    @pytest.mark.asyncio
    async def test_argv_has_d_flag_with_server_dir(self) -> None:
        """Shell bridge argv must include -d <OPENCODE_SERVER_DIR>."""
        argv = await self._capture_argv(server_dir=_FAKE_SERVER_DIR)
        assert "-d" in argv
        idx = argv.index("-d")
        assert argv[idx + 1] == _FAKE_SERVER_DIR

    @pytest.mark.asyncio
    async def test_argv_has_no_up_stage(self) -> None:
        """'up' must not appear as a positional arg (D3: drop up stage)."""
        argv = await self._capture_argv()
        assert "up" not in argv

    @pytest.mark.asyncio
    async def test_argv_has_no_start_stage(self) -> None:
        """'start' must not appear as a positional arg (D3: drop start stage)."""
        argv = await self._capture_argv()
        assert "start" not in argv

    @pytest.mark.asyncio
    async def test_argv_u_value_is_opencode_server_url(self) -> None:
        """The value after -u must equal OPENCODE_SERVER_URL (VAL-SEN-011)."""
        custom_url = "http://custom-host:12345"
        argv = await self._capture_argv(server_url=custom_url)
        idx = argv.index("-u")
        assert argv[idx + 1] == custom_url, (
            f"Expected -u to be {custom_url!r}, got {argv[idx + 1]!r}"
        )

    @pytest.mark.asyncio
    async def test_argv_d_value_is_opencode_server_dir(self) -> None:
        """The value after -d must equal OPENCODE_SERVER_DIR (VAL-SEN-011 shape)."""
        custom_dir = "/custom/orch/dir"
        argv = await self._capture_argv(server_dir=custom_dir)
        idx = argv.index("-d")
        assert argv[idx + 1] == custom_dir, (
            f"Expected -d to be {custom_dir!r}, got {argv[idx + 1]!r}"
        )


# ---------------------------------------------------------------------------
# Heartbeat includes OPENCODE_SERVER_URL — VAL-SEN-022
# ---------------------------------------------------------------------------


class TestHeartbeatContent:
    """_heartbeat_loop passes OPENCODE_SERVER_URL to post_heartbeat (D3 requirement)."""

    @pytest.mark.asyncio
    async def test_heartbeat_passes_server_url(self) -> None:
        """post_heartbeat is called with server_url=OPENCODE_SERVER_URL."""
        queue = _make_queue()
        sentinel = Sentinel(queue)
        item = _make_work_item()

        with patch("src.sentinel.HEARTBEAT_INTERVAL", 0.01):
            with patch("src.sentinel.OPENCODE_SERVER_URL", _FAKE_SERVER_URL):
                start_time = asyncio.get_event_loop().time()
                heartbeat_task = asyncio.create_task(
                    sentinel._heartbeat_loop(item, start_time)
                )
                # Allow at least one heartbeat to fire
                await asyncio.sleep(0.05)
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

        queue.post_heartbeat.assert_called()
        # Each call must include server_url keyword arg with the patched URL
        for call_args in queue.post_heartbeat.call_args_list:
            assert call_args.kwargs.get("server_url") == _FAKE_SERVER_URL, (
                f"Expected server_url={_FAKE_SERVER_URL!r} in heartbeat call, "
                f"got kwargs={call_args.kwargs!r}"
            )


# ---------------------------------------------------------------------------
# --once flag exits after one polling pass
# ---------------------------------------------------------------------------


class TestOnceFlag:
    """run_forever(once=True) exits after a single polling cycle."""

    @pytest.mark.asyncio
    async def test_once_exits_after_one_pass(self) -> None:
        """With once=True, the loop runs exactly one iteration."""
        queue = _make_queue()
        sentinel = Sentinel(queue)

        poll_count = 0

        async def mock_fetch() -> list:
            nonlocal poll_count
            poll_count += 1
            return []

        queue.fetch_queued_tasks = mock_fetch

        with patch("src.sentinel.POLL_INTERVAL", 999):  # ensure sleep is never reached
            await sentinel.run_forever(once=True)

        assert poll_count == 1, f"Expected exactly 1 poll, got {poll_count}"

    @pytest.mark.asyncio
    async def test_once_does_not_sleep(self) -> None:
        """With once=True, asyncio.sleep is not called between polls."""
        queue = _make_queue()
        sentinel = Sentinel(queue)

        with patch("src.sentinel.POLL_INTERVAL", 999):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await sentinel.run_forever(once=True)

        mock_sleep.assert_not_called()
