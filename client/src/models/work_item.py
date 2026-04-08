"""
OS-APOW Unified Work Item Model

Canonical data model shared by both the Sentinel Orchestrator and the
Work Event Notifier. Both components import from this module to prevent
model divergence.

See: OS-APOW Plan Review, I-1 / R-3
"""

import re
from enum import Enum
from pydantic import BaseModel


class TaskType(str, Enum):
    """The kind of work the agent should perform."""

    PLAN = "PLAN"
    IMPLEMENT = "IMPLEMENT"
    BUGFIX = "BUGFIX"


class WorkItemStatus(str, Enum):
    """Maps directly to GitHub Issue labels used as state indicators."""

    QUEUED = "agent:queued"
    IN_PROGRESS = "agent:in-progress"
    RECONCILING = "agent:reconciling"
    SUCCESS = "agent:success"
    ERROR = "agent:error"
    INFRA_FAILURE = "agent:infra-failure"
    STALLED_BUDGET = "agent:stalled-budget"


class WorkItem(BaseModel):
    """Unified work item used across all OS-APOW components.

    All fields are required. Both the Notifier and Sentinel construct
    WorkItems with all fields populated from their respective data sources.
    """

    id: str
    issue_number: int
    source_url: str
    context_body: str
    target_repo_slug: str
    task_type: TaskType
    status: WorkItemStatus
    node_id: str


# --- Credential Scrubber (R-7) ---
_SECRET_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9_]{36,}"),
    re.compile(r"ghs_[A-Za-z0-9_]{36,}"),
    re.compile(r"gho_[A-Za-z0-9_]{36,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"token\s+[A-Za-z0-9\-._~+/]{20,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"[A-Za-z0-9]{32,}\.zhipu[A-Za-z0-9]*"),
]


def scrub_secrets(text: str, replacement: str = "***REDACTED***") -> str:
    """Strip known secret patterns from text for safe public posting."""
    if not text:
        return ""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def classify_task_type(issue: dict) -> TaskType:
    """Determine the TaskType from issue title and labels.

    Centralized logic used by both the Notifier and the Sentinel
    to ensure consistent classification.
    """
    labels = [label["name"] for label in issue.get("labels", [])]
    title = issue.get("title", "")

    if "[Application Plan]" in title or "[Plan]" in title or "agent:plan" in labels:
        return TaskType.PLAN
    elif "bug" in labels:
        return TaskType.BUGFIX
    return TaskType.IMPLEMENT
