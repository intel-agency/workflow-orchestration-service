"""
workflow-orchestration-service Work Event Notifier

A FastAPI-based webhook receiver that maps provider events (GitHub, etc.)
to a unified Work Item queue. Receives GitHub App webhooks and triages
them into WorkItems for the Sentinel to process.

Derived from plan_docs-self-contained/src/notifier_service.py.
Structured logging is used throughout — raw payload fields are NEVER
spliced into log format strings (see VAL-XCT-011, VAL-CLI-034).

Env validation is deferred to startup/first-request so that
``import src.notifier`` succeeds in a clean environment (VAL-IMG-022,
VAL-CLI-030).
"""

import hashlib
import hmac
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from src.models.work_item import TaskType, WorkItem, WorkItemStatus
from src.queue.github_queue import GitHubQueue, ITaskQueue

logger = logging.getLogger(__name__)

# --- Sentinel values that indicate a var is unset / a stub ---
_PLACEHOLDER_VALUES: frozenset[str] = frozenset(
    {"your_webhook_secret_here", "YOUR_GITHUB_TOKEN", ""}
)


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


class ConfigurationError(RuntimeError):
    """Raised when a required environment variable is missing or has a placeholder value.

    Callers (per-request checks) catch this and surface a 503.
    """


def validate_config() -> tuple[bytes, str]:
    """Read and validate webhook credentials from the environment.

    Raises ConfigurationError if any required value is absent or is still a
    placeholder.  Returns ``(webhook_secret_bytes, github_token)`` on success.

    This function is intentionally NOT called at module-import time so that
    ``import src.notifier`` works in any environment (e.g., the container's
    Python import smoke test, unit tests, mypy runs).
    """
    webhook_secret = os.environ.get("WEBHOOK_SECRET", "")
    github_token = os.environ.get("GITHUB_TOKEN", "")

    if webhook_secret in _PLACEHOLDER_VALUES:
        raise ConfigurationError(
            "WEBHOOK_SECRET is missing or still set to a placeholder value. "
            "Set it to the GitHub App webhook secret."
        )
    if github_token in _PLACEHOLDER_VALUES:
        raise ConfigurationError(
            "GITHUB_TOKEN is missing or still set to a placeholder value."
        )

    return webhook_secret.encode(), github_token


# ---------------------------------------------------------------------------
# FastAPI application — lifespan (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(application: FastAPI):  # type: ignore[type-arg]
    """ASGI lifespan context.

    At startup: check env config and emit a structured WARNING if credentials
    are missing (rather than raising) so the server can still service the
    /health probe.  Per-request handlers enforce config via validate_config()
    and return 503 if credentials are absent.
    """
    try:
        validate_config()
        logger.info("Notifier startup: configuration validated successfully")
    except ConfigurationError as exc:
        # Emit a warning but do NOT raise — the server should still start so
        # that /health probes succeed.  The webhook endpoint will return 503
        # until the operator supplies valid credentials.
        logger.warning(
            "Notifier startup: configuration incomplete — webhook requests will fail",
            extra={"detail": str(exc)},
        )
    yield  # Application is now serving requests.


app = FastAPI(
    title="workflow-orchestration-service Event Notifier",
    lifespan=_lifespan,
)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_queue() -> ITaskQueue:
    """Dependency injection for the queue implementation.

    Phase 1: GitHub Issues. Can be swapped for Linear, Jira, etc. by
    replacing this provider.
    """
    _, github_token = validate_config()
    return GitHubQueue(token=github_token)


async def verify_signature(
    request: Request, x_hub_signature_256: str = Header(None)
) -> None:
    """Verify the GitHub HMAC-SHA256 webhook signature.

    Returns 401 if the signature is missing or incorrect.
    Returns 503 if the server is not configured (WEBHOOK_SECRET unset).
    """
    # Health-probe before dispatch — validate config before touching the secret.
    try:
        webhook_secret_bytes, _ = validate_config()
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not x_hub_signature_256:
        raise HTTPException(status_code=401, detail="X-Hub-Signature-256 missing")

    body = await request.body()
    expected = "sha256=" + hmac.new(
        webhook_secret_bytes, body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _issue_to_work_item(issue: dict[str, Any], repo_slug: str) -> WorkItem:
    """Convert a GitHub issue payload dict to a WorkItem."""
    labels = [lbl["name"] for lbl in issue.get("labels", [])]

    # Determine task type from title keywords and labels (mirrors reference logic).
    if (
        "[Application Plan]" in issue.get("title", "")
        or "[Plan]" in issue.get("title", "")
        or "agent:plan" in labels
    ):
        task_type = TaskType.PLAN
    elif "agent:bugfix" in labels or "bug" in labels:
        task_type = TaskType.BUGFIX
    else:
        task_type = TaskType.IMPLEMENT

    return WorkItem(
        id=str(issue["id"]),
        issue_number=issue["number"],
        source_url=issue["html_url"],
        target_repo_slug=repo_slug,
        task_type=task_type,
        context_body=issue.get("body") or "",
        status=WorkItemStatus.QUEUED,
        node_id=issue["node_id"],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/webhooks/github", dependencies=[Depends(verify_signature)])
async def handle_github_webhook(
    request: Request, queue: ITaskQueue = Depends(get_queue)
) -> dict[str, Any]:
    """Receive a GitHub webhook event and triage it into the work queue.

    Structured logging is used for every field derived from the payload so
    that raw user-controlled data never appears in a log *format string*.
    """
    payload: dict[str, Any] = await request.json()
    event_type = request.headers.get("X-GitHub-Event", "")
    action = payload.get("action", "")
    repo_slug = payload.get("repository", {}).get("full_name", "")

    # Structured log: delivery_id and event_type are safe static headers;
    # repo_slug is user-controlled — passed via extra= so it stays in the
    # log record's structured fields and never touches the format string.
    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    logger.info(
        "webhook received",
        extra={
            "delivery_id": delivery_id,
            "event_type": event_type,
            "action": repr(action),
            "repo": repr(repo_slug),
        },
    )

    # --- issues.opened ---
    if event_type == "issues" and action == "opened":
        issue = payload["issue"]
        work_item = _issue_to_work_item(issue, repo_slug)

        if work_item.task_type in (TaskType.PLAN, TaskType.IMPLEMENT, TaskType.BUGFIX):
            await queue.add_to_queue(work_item)
            logger.info(
                "work item queued",
                extra={
                    "issue_number": issue.get("number"),
                    "task_type": work_item.task_type.value,
                    "item_id": work_item.id,
                },
            )
            return {"status": "accepted", "item_id": work_item.id}

    # --- issues.labeled ---
    if event_type == "issues" and action == "labeled":
        issue = payload["issue"]
        label_name = payload.get("label", {}).get("name", "")
        if label_name == WorkItemStatus.QUEUED.value:
            # Sentinel picks up queued items via polling — no action needed here.
            logger.info(
                "agent:queued label applied; sentinel will poll",
                extra={"issue_number": issue.get("number")},
            )
            return {"status": "acknowledged", "issue": issue.get("number")}

    # --- workflow_dispatch ---
    if event_type == "workflow_dispatch":
        logger.info("workflow_dispatch event received")
        return {"status": "acknowledged", "event": "workflow_dispatch"}

    logger.info(
        "webhook ignored",
        extra={"event_type": event_type, "action": repr(action)},
    )
    return {
        "status": "ignored",
        "reason": "No actionable workflow-orchestration-service event mapping found",
    }


@app.get("/health")
def health_check() -> dict[str, str]:
    """Liveness probe — returns 200 as soon as the process is up."""
    return {"status": "online", "system": "workflow-orchestration-service Notifier"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
