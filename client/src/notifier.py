"""
OS-APOW Work Event Notifier

A FastAPI-based webhook receiver that maps provider events (GitHub, etc.)
to a unified Work Item queue. Receives GitHub App webhooks and triages
them into WorkItems for the Sentinel to process.

Adapted from plan_docs/notifier_service.py for the standalone
client/server architecture.
"""

import hmac
import hashlib
import json
import logging
import os
import sys
from typing import Any

from fastapi import FastAPI, Request, HTTPException, Header, Depends

from src.models.work_item import (
    TaskType,
    WorkItemStatus,
    WorkItem,
)
from src.queue.github_queue import ITaskQueue, GitHubQueue
from src.config import WEBHOOK_SECRET, GITHUB_TOKEN

logger = logging.getLogger("OS-APOW-Notifier")

# --- 0. Environment validation at import time (I-5 / R-6) ---

_PLACEHOLDER_VALUES = {"your_webhook_secret_here", "YOUR_GITHUB_TOKEN", ""}

if WEBHOOK_SECRET in _PLACEHOLDER_VALUES:
    print(
        "FATAL: WEBHOOK_SECRET is missing or still set to a placeholder value. "
        "Set it to the GitHub App webhook secret.",
        file=sys.stderr,
    )
    sys.exit(1)

if GITHUB_TOKEN in _PLACEHOLDER_VALUES:
    print(
        "FATAL: GITHUB_TOKEN is missing or still set to a placeholder value.",
        file=sys.stderr,
    )
    sys.exit(1)

_WEBHOOK_SECRET_BYTES = WEBHOOK_SECRET.encode()

# --- 1. FastAPI Application ---

app = FastAPI(title="OS-APOW Event Notifier")


def get_queue() -> ITaskQueue:
    """Dependency injection for the queue implementation.
    Phase 1: GitHub. Can be swapped for Linear, Jira, etc."""
    return GitHubQueue(token=GITHUB_TOKEN)


async def verify_signature(request: Request, x_hub_signature_256: str = Header(None)):
    if not x_hub_signature_256:
        raise HTTPException(status_code=401, detail="X-Hub-Signature-256 missing")

    body = await request.body()
    signature = (
        "sha256=" + hmac.new(_WEBHOOK_SECRET_BYTES, body, hashlib.sha256).hexdigest()
    )

    if not hmac.compare_digest(signature, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")


# --- 2. Event Handlers ---


def _classify_task_type(issue: dict) -> TaskType:
    """Determine the TaskType from issue title and labels."""
    labels = [label["name"] for label in issue.get("labels", [])]
    title = issue.get("title", "")

    if "[Application Plan]" in title or "[Plan]" in title or "agent:plan" in labels:
        return TaskType.PLAN
    elif "bug" in labels:
        return TaskType.BUGFIX
    return TaskType.IMPLEMENT


def _issue_to_work_item(issue: dict, repo_slug: str) -> WorkItem:
    """Convert a GitHub issue payload to a WorkItem."""
    return WorkItem(
        id=str(issue["id"]),
        issue_number=issue["number"],
        source_url=issue["html_url"],
        target_repo_slug=repo_slug,
        task_type=_classify_task_type(issue),
        context_body=issue.get("body") or "",
        status=WorkItemStatus.QUEUED,
        node_id=issue["node_id"],
    )


# --- 3. Endpoints ---


@app.post("/webhooks/github", dependencies=[Depends(verify_signature)])
async def handle_github_webhook(
    request: Request, queue: ITaskQueue = Depends(get_queue)
):
    payload = await request.json()
    event_type = request.headers.get("X-GitHub-Event")
    action = payload.get("action")
    repo_slug = payload.get("repository", {}).get("full_name", "")

    logger.info(f"Received event: {event_type}.{action} from {repo_slug}")

    # issues.opened — new issue triaged by title/labels
    if event_type == "issues" and action == "opened":
        issue = payload["issue"]
        labels = [label["name"] for label in issue.get("labels", [])]

        if (
            "[Application Plan]" in issue["title"]
            or "[Plan]" in issue["title"]
            or "agent:plan" in labels
        ):
            work_item = _issue_to_work_item(issue, repo_slug)
            await queue.add_to_queue(work_item)
            return {"status": "accepted", "item_id": work_item.id}

    # issues.labeled — label-driven orchestration (matches orchestrator-agent.yml trigger)
    if event_type == "issues" and action == "labeled":
        issue = payload["issue"]
        label_name = payload.get("label", {}).get("name", "")

        if label_name == WorkItemStatus.QUEUED.value:
            # Already queued — the Sentinel will pick it up via polling
            logger.info(
                f"Issue #{issue['number']} labeled {label_name} — Sentinel will poll"
            )
            return {"status": "acknowledged", "issue": issue["number"]}

    # workflow_dispatch — manual trigger
    if event_type == "workflow_dispatch":
        logger.info(f"Workflow dispatch received for {repo_slug}")
        return {"status": "acknowledged", "event": "workflow_dispatch"}

    return {"status": "ignored", "reason": "No actionable OS-APOW event mapping found"}


@app.get("/health")
def health_check():
    return {"status": "online", "system": "OS-APOW Notifier"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
