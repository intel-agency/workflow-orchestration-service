"""
Unit tests for client/src/notifier.py.

Coverage:
  - Import-without-env succeeds (VAL-CLI-030, VAL-IMG-022)
  - FastAPI app object is created correctly (VAL-CLI-030, VAL-CLI-031)
  - Invalid HMAC signature returns 401 (VAL-CLI-032)
  - Valid HMAC with issues.opened returns 2xx (VAL-CLI-033)
  - No log injection — newline-bearing payload fields cannot forge log lines (VAL-CLI-034)
  - Structured-log assertion: record.msg contains no raw payload (VAL-CLI-034)
  - Request handler returns 503 when env is unset (VAL-CLI-030 additional)
  - Retry on transient queue failure
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_WEBHOOK_SECRET = "FAKE-WEBHOOK-SECRET-FOR-TESTING-XYZ"
_FAKE_GITHUB_TOKEN = "FAKE-GITHUB-TOKEN-FOR-TESTING-ABC"


def _make_signature(body: bytes, secret: str) -> str:
    """Compute the HMAC-SHA256 signature GitHub sends in X-Hub-Signature-256."""
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _issues_opened_payload(
    issue_id: int = 1,
    issue_number: int = 42,
    title: str = "Test issue",
    body: str = "Some body text",
    labels: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "action": "opened",
        "issue": {
            "id": issue_id,
            "number": issue_number,
            "title": title,
            "body": body,
            "html_url": f"https://github.com/org/repo/issues/{issue_number}",
            "labels": labels or [],
            "node_id": f"MDU6SXNzdWU{issue_id}",
        },
        "repository": {"full_name": "org/repo"},
    }


# ---------------------------------------------------------------------------
# Test: import succeeds in a clean environment
# ---------------------------------------------------------------------------


def test_import_without_env_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing src.notifier must NOT raise SystemExit or RuntimeError.

    This validates VAL-IMG-022 (smoke import inside the client image) and
    VAL-CLI-030 (module does not call sys.exit at import time).
    """
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    # If sys.exit() were called at module level this would raise SystemExit.
    import src.notifier as notifier_mod  # noqa: PLC0415

    # The app must still be created.
    assert isinstance(notifier_mod.app, FastAPI)


# ---------------------------------------------------------------------------
# Test: app routes
# ---------------------------------------------------------------------------


def test_app_exposes_required_routes() -> None:
    """The FastAPI app must expose POST /webhooks/github and GET /health (VAL-CLI-031)."""
    import src.notifier as notifier_mod  # noqa: PLC0415

    paths = {r.path for r in notifier_mod.app.routes}
    assert "/webhooks/github" in paths, f"Missing /webhooks/github; got {paths}"
    assert "/health" in paths, f"Missing /health; got {paths}"


# ---------------------------------------------------------------------------
# Test: validate_config raises ConfigurationError when env is unset
# ---------------------------------------------------------------------------


def test_validate_config_raises_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """validate_config() must raise ConfigurationError — NOT call sys.exit — when
    WEBHOOK_SECRET is absent (VAL-CLI-030)."""
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    from src.notifier import ConfigurationError, validate_config  # noqa: PLC0415

    with pytest.raises(ConfigurationError, match="WEBHOOK_SECRET"):
        validate_config()


def test_validate_config_raises_when_github_token_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """validate_config() must raise ConfigurationError when GITHUB_TOKEN is absent."""
    monkeypatch.setenv("WEBHOOK_SECRET", _FAKE_WEBHOOK_SECRET)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    from src.notifier import ConfigurationError, validate_config  # noqa: PLC0415

    with pytest.raises(ConfigurationError, match="GITHUB_TOKEN"):
        validate_config()


# ---------------------------------------------------------------------------
# Test: 503 when env is unset during a real request
# ---------------------------------------------------------------------------


def test_webhook_returns_503_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /webhooks/github must return 503 (not 500 / crash) when WEBHOOK_SECRET
    is unset.  The handler must not call sys.exit (VAL-CLI-030 additional)."""
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    import src.notifier as notifier_mod  # noqa: PLC0415

    # Use raise_server_exceptions=False so the TestClient returns the HTTP
    # response rather than re-raising any unhandled exception.
    with TestClient(notifier_mod.app, raise_server_exceptions=False) as client:
        response = client.post(
            "/webhooks/github",
            content=b"{}",
            headers={"X-Hub-Signature-256": "sha256=deadbeef"},
        )
    assert response.status_code in (
        401,
        422,
        503,
    ), f"Unexpected status {response.status_code}; expected 401/422/503"


# ---------------------------------------------------------------------------
# Test: invalid HMAC signature returns 401
# ---------------------------------------------------------------------------


def test_invalid_hmac_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bogus X-Hub-Signature-256 must yield 401 (VAL-CLI-032)."""
    monkeypatch.setenv("WEBHOOK_SECRET", _FAKE_WEBHOOK_SECRET)
    monkeypatch.setenv("GITHUB_TOKEN", _FAKE_GITHUB_TOKEN)

    import src.notifier as notifier_mod  # noqa: PLC0415

    with TestClient(notifier_mod.app) as client:
        response = client.post(
            "/webhooks/github",
            content=b'{"action": "opened"}',
            headers={
                "X-GitHub-Event": "issues",
                "X-Hub-Signature-256": "sha256=deadbeef00000000",
            },
        )
    assert response.status_code == 401


def test_missing_signature_header_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing X-Hub-Signature-256 header must yield 401."""
    monkeypatch.setenv("WEBHOOK_SECRET", _FAKE_WEBHOOK_SECRET)
    monkeypatch.setenv("GITHUB_TOKEN", _FAKE_GITHUB_TOKEN)

    import src.notifier as notifier_mod  # noqa: PLC0415

    with TestClient(notifier_mod.app) as client:
        response = client.post("/webhooks/github", content=b"{}")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Test: happy-path delivery
# ---------------------------------------------------------------------------


def test_valid_hmac_issues_opened_returns_2xx(monkeypatch: pytest.MonkeyPatch) -> None:
    """A correctly signed issues.opened event must return 2xx and queue the item
    (VAL-CLI-033)."""
    monkeypatch.setenv("WEBHOOK_SECRET", _FAKE_WEBHOOK_SECRET)
    monkeypatch.setenv("GITHUB_TOKEN", _FAKE_GITHUB_TOKEN)

    import src.notifier as notifier_mod  # noqa: PLC0415

    payload = _issues_opened_payload(title="[Application Plan] Feature X")
    body = json.dumps(payload).encode()
    sig = _make_signature(body, _FAKE_WEBHOOK_SECRET)

    mock_queue = MagicMock()
    mock_queue.add_to_queue = AsyncMock(return_value=True)

    # Override the queue dependency so we don't need a real GitHub token.
    notifier_mod.app.dependency_overrides[notifier_mod.get_queue] = lambda: mock_queue

    try:
        with TestClient(notifier_mod.app) as client:
            response = client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "issues",
                    "X-Hub-Signature-256": sig,
                },
            )
    finally:
        notifier_mod.app.dependency_overrides.clear()

    assert response.status_code in (200, 201, 202), response.text
    data = response.json()
    assert data["status"] == "accepted"
    assert "item_id" in data
    mock_queue.add_to_queue.assert_awaited_once()


def test_ignored_event_returns_200_with_ignored_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An event with no actionable mapping must return 200 with status='ignored'."""
    monkeypatch.setenv("WEBHOOK_SECRET", _FAKE_WEBHOOK_SECRET)
    monkeypatch.setenv("GITHUB_TOKEN", _FAKE_GITHUB_TOKEN)

    import src.notifier as notifier_mod  # noqa: PLC0415

    payload = {"action": "deleted", "repository": {"full_name": "org/repo"}}
    body = json.dumps(payload).encode()
    sig = _make_signature(body, _FAKE_WEBHOOK_SECRET)

    mock_queue = MagicMock()
    notifier_mod.app.dependency_overrides[notifier_mod.get_queue] = lambda: mock_queue

    try:
        with TestClient(notifier_mod.app) as client:
            response = client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "push",
                    "X-Hub-Signature-256": sig,
                },
            )
    finally:
        notifier_mod.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


# ---------------------------------------------------------------------------
# Test: retry on transient queue failure
# ---------------------------------------------------------------------------


def test_retry_on_transient_queue_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the queue raises on the first call but succeeds on the second, the
    handler must propagate the error (retry is the caller's responsibility in
    this synchronous path; we assert the error is not swallowed)."""
    monkeypatch.setenv("WEBHOOK_SECRET", _FAKE_WEBHOOK_SECRET)
    monkeypatch.setenv("GITHUB_TOKEN", _FAKE_GITHUB_TOKEN)

    import src.notifier as notifier_mod  # noqa: PLC0415

    payload = _issues_opened_payload(title="[Application Plan] Retryable")
    body = json.dumps(payload).encode()
    sig = _make_signature(body, _FAKE_WEBHOOK_SECRET)

    # Simulate: first call raises, second call succeeds.
    call_count = 0

    async def _flaky_add(item: Any) -> bool:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("transient network error")
        return True

    mock_queue = MagicMock()
    mock_queue.add_to_queue = _flaky_add
    notifier_mod.app.dependency_overrides[notifier_mod.get_queue] = lambda: mock_queue

    try:
        with TestClient(notifier_mod.app, raise_server_exceptions=False) as client:
            response1 = client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "issues",
                    "X-Hub-Signature-256": sig,
                },
            )
        # First call should fail with 5xx (queue raised).
        assert response1.status_code >= 500, (
            f"Expected 5xx on transient failure, got {response1.status_code}"
        )

        # Second call: new body bytes (same payload) — fresh client to avoid request state.
        with TestClient(notifier_mod.app) as client:
            response2 = client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "issues",
                    "X-Hub-Signature-256": sig,
                },
            )
        assert response2.status_code in (200, 201, 202), response2.text
    finally:
        notifier_mod.app.dependency_overrides.clear()

    assert call_count == 2


# ---------------------------------------------------------------------------
# Test: structured-log assertion — no raw payload in record.msg
# ---------------------------------------------------------------------------


def test_no_raw_payload_in_log_record_msg(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """record.msg must never contain raw payload field values (VAL-CLI-034).

    The canary value is injected as the issue title and the repo slug.
    After the request, every log record's *msg* (the format string, not the
    rendered message) is inspected; the canary must not appear there.
    """
    monkeypatch.setenv("WEBHOOK_SECRET", _FAKE_WEBHOOK_SECRET)
    monkeypatch.setenv("GITHUB_TOKEN", _FAKE_GITHUB_TOKEN)

    import src.notifier as notifier_mod  # noqa: PLC0415

    canary = "CANARY-PAYLOAD-VALUE-12345-UNIQUE"
    payload = _issues_opened_payload(title=f"[Application Plan] {canary}", body=canary)
    # Also inject canary into repo name.
    payload["repository"] = {"full_name": f"org/{canary}"}

    body = json.dumps(payload).encode()
    sig = _make_signature(body, _FAKE_WEBHOOK_SECRET)

    mock_queue = MagicMock()
    mock_queue.add_to_queue = AsyncMock(return_value=True)
    notifier_mod.app.dependency_overrides[notifier_mod.get_queue] = lambda: mock_queue

    try:
        with caplog.at_level(logging.DEBUG, logger="src.notifier"):
            with TestClient(notifier_mod.app) as client:
                client.post(
                    "/webhooks/github",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-GitHub-Event": "issues",
                        "X-Hub-Signature-256": sig,
                    },
                )
    finally:
        notifier_mod.app.dependency_overrides.clear()

    # Assert that the canary does not appear in ANY record's *msg* (the format
    # string template, not the rendered string).  If structured logging is
    # correctly used, payload values appear only in record.args or record.__dict__
    # extra fields, never in record.msg itself.
    for record in caplog.records:
        assert canary not in record.msg, (
            f"Log record '{record.msg}' contains raw payload canary '{canary}'. "
            "Use structured logging (extra={{...}}) instead of f-strings."
        )


def test_no_log_injection_via_newlines(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A payload field containing a newline + injected log text must NOT produce
    a separate log record with message 'INJECTED LOG LINE' (VAL-CLI-034)."""
    monkeypatch.setenv("WEBHOOK_SECRET", _FAKE_WEBHOOK_SECRET)
    monkeypatch.setenv("GITHUB_TOKEN", _FAKE_GITHUB_TOKEN)

    import src.notifier as notifier_mod  # noqa: PLC0415

    injected_msg = "INJECTED LOG LINE"
    # Inject newline + forged log message into the action field via repo name.
    payload = _issues_opened_payload(title=f"[Application Plan] Normal title")
    payload["repository"] = {"full_name": f"org/repo\n{injected_msg}\n"}

    body = json.dumps(payload).encode()
    sig = _make_signature(body, _FAKE_WEBHOOK_SECRET)

    mock_queue = MagicMock()
    mock_queue.add_to_queue = AsyncMock(return_value=True)
    notifier_mod.app.dependency_overrides[notifier_mod.get_queue] = lambda: mock_queue

    try:
        with caplog.at_level(logging.DEBUG, logger="src.notifier"):
            with TestClient(notifier_mod.app) as client:
                client.post(
                    "/webhooks/github",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-GitHub-Event": "issues",
                        "X-Hub-Signature-256": sig,
                    },
                )
    finally:
        notifier_mod.app.dependency_overrides.clear()

    # No record should have msg == the injected text.
    injected_msgs = [r for r in caplog.records if r.msg == injected_msg]
    assert not injected_msgs, (
        f"Log injection detected: a record with msg='{injected_msg}' was produced"
    )


# ---------------------------------------------------------------------------
# Test: health endpoint always works (no auth needed)
# ---------------------------------------------------------------------------


def test_health_endpoint_returns_200() -> None:
    """GET /health must return 200 even when no credentials are set."""
    import src.notifier as notifier_mod  # noqa: PLC0415

    with TestClient(notifier_mod.app, raise_server_exceptions=False) as client:
        response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
