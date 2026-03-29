"""Event payload schemas for GitHub webhooks.

This module defines Pydantic models for parsing and validating
GitHub webhook event payloads received by the notifier service.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EventPayload(BaseModel):
    """Base model for event payloads.

    All specific event payload models should inherit from this base class.
    """

    pass


class GitHubUser(BaseModel):
    """GitHub user information."""

    login: str = Field(..., description="Username")
    id: int = Field(..., description="User ID")
    node_id: str | None = Field(None, description="GraphQL node ID")
    avatar_url: str | None = Field(None, description="Avatar URL")
    html_url: str | None = Field(None, description="Profile URL")
    type: str | None = Field(None, description="User type (User, Bot, etc.)")


class GitHubLabel(BaseModel):
    """GitHub label information."""

    id: int = Field(..., description="Label ID")
    node_id: str | None = Field(None, description="GraphQL node ID")
    name: str = Field(..., description="Label name")
    description: str | None = Field(None, description="Label description")
    color: str | None = Field(None, description="Label color (hex)")
    default: bool = Field(default=False, description="Is this a default label?")


class GitHubMilestone(BaseModel):
    """GitHub milestone information."""

    id: int = Field(..., description="Milestone ID")
    number: int = Field(..., description="Milestone number")
    title: str = Field(..., description="Milestone title")
    description: str | None = Field(None, description="Milestone description")
    state: str = Field(..., description="Milestone state (open, closed)")
    html_url: str | None = Field(None, description="Milestone URL")


class GitHubIssue(BaseModel):
    """GitHub issue information."""

    id: int = Field(..., description="Issue ID")
    node_id: str | None = Field(None, description="GraphQL node ID")
    number: int = Field(..., description="Issue number")
    title: str = Field(..., description="Issue title")
    body: str | None = Field(None, description="Issue body/description")
    state: str = Field(..., description="Issue state (open, closed)")
    user: GitHubUser | None = Field(None, description="Issue author")
    labels: list[GitHubLabel] = Field(
        default_factory=list,
        description="Issue labels",
    )
    milestone: GitHubMilestone | None = Field(None, description="Issue milestone")
    assignees: list[GitHubUser] = Field(
        default_factory=list,
        description="Issue assignees",
    )
    created_at: datetime | str | None = Field(None, description="Creation timestamp")
    updated_at: datetime | str | None = Field(None, description="Last update timestamp")
    html_url: str | None = Field(None, description="Issue URL")


class GitHubPullRequest(BaseModel):
    """GitHub pull request information."""

    id: int = Field(..., description="PR ID")
    node_id: str | None = Field(None, description="GraphQL node ID")
    number: int = Field(..., description="PR number")
    title: str = Field(..., description="PR title")
    body: str | None = Field(None, description="PR body/description")
    state: str = Field(..., description="PR state (open, closed)")
    draft: bool = Field(default=False, description="Is this a draft PR?")
    merged: bool = Field(default=False, description="Is this PR merged?")
    user: GitHubUser | None = Field(None, description="PR author")
    labels: list[GitHubLabel] = Field(
        default_factory=list,
        description="PR labels",
    )
    milestone: GitHubMilestone | None = Field(None, description="PR milestone")
    assignees: list[GitHubUser] = Field(
        default_factory=list,
        description="PR assignees",
    )
    requested_reviewers: list[GitHubUser] = Field(
        default_factory=list,
        description="Requested reviewers",
    )
    base_ref: str | None = Field(None, alias="base", description="Base branch info")
    head_ref: str | None = Field(None, alias="head", description="Head branch info")
    created_at: datetime | str | None = Field(None, description="Creation timestamp")
    updated_at: datetime | str | None = Field(None, description="Last update timestamp")
    merged_at: datetime | str | None = Field(None, description="Merge timestamp")
    html_url: str | None = Field(None, description="PR URL")

    class Config:
        """Allow field aliases."""

        populate_by_name = True


class GitHubRepository(BaseModel):
    """GitHub repository information."""

    id: int = Field(..., description="Repository ID")
    node_id: str | None = Field(None, description="GraphQL node ID")
    name: str = Field(..., description="Repository name")
    full_name: str = Field(..., description="Full repository name (owner/name)")
    private: bool = Field(default=False, description="Is this a private repo?")
    owner: GitHubUser | None = Field(None, description="Repository owner")
    html_url: str | None = Field(None, description="Repository URL")
    default_branch: str | None = Field(None, description="Default branch name")


class IssueEventPayload(EventPayload):
    """Payload for issue-related events.

    This model handles events like:
    - issues.opened
    - issues.closed
    - issues.labeled
    - issues.assigned
    - etc.
    """

    action: str = Field(..., description="Action that triggered the event")
    issue: GitHubIssue = Field(..., description="The issue that was affected")
    repository: GitHubRepository = Field(..., description="The repository")
    sender: GitHubUser | None = Field(None, description="The user who triggered the event")
    label: GitHubLabel | None = Field(
        None, description="Label that was added/removed (if applicable)"
    )


class PullRequestEventPayload(EventPayload):
    """Payload for pull request-related events.

    This model handles events like:
    - pull_request.opened
    - pull_request.closed
    - pull_request.labeled
    - pull_request.review_requested
    - etc.
    """

    action: str = Field(..., description="Action that triggered the event")
    pull_request: GitHubPullRequest = Field(..., description="The PR that was affected")
    repository: GitHubRepository = Field(..., description="The repository")
    sender: GitHubUser | None = Field(None, description="The user who triggered the event")
    label: GitHubLabel | None = Field(
        None, description="Label that was added/removed (if applicable)"
    )


class GitHubEventPayload(EventPayload):
    """Generic GitHub event payload.

    This model provides a flexible structure for handling any GitHub
    webhook event type when a specific model is not available.
    """

    action: str | None = Field(None, description="Action that triggered the event")
    repository: GitHubRepository | None = Field(None, description="The repository")
    sender: GitHubUser | None = Field(None, description="The user who triggered the event")

    # Allow additional fields for flexibility
    model_config = {"extra": "allow"}


class WebhookEvent(BaseModel):
    """Complete webhook event with metadata.

    This model wraps the event payload with additional metadata
    needed for processing and routing.
    """

    event_type: str = Field(..., description="GitHub event type (X-GitHub-Event header)")
    action: str | None = Field(None, description="Event action")
    delivery_id: str | None = Field(None, description="GitHub delivery UUID")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the event was received",
    )
    payload: dict[str, Any] = Field(..., description="Raw event payload")
    signature: str | None = Field(None, description="HMAC signature (if verified)")

    def parse_issue_payload(self) -> IssueEventPayload | None:
        """Parse the payload as an issue event.

        Returns:
            Parsed IssueEventPayload or None if parsing fails
        """
        if self.event_type != "issues":
            return None
        try:
            return IssueEventPayload(**self.payload)
        except Exception:
            return None

    def parse_pr_payload(self) -> PullRequestEventPayload | None:
        """Parse the payload as a pull request event.

        Returns:
            Parsed PullRequestEventPayload or None if parsing fails
        """
        if self.event_type != "pull_request":
            return None
        try:
            return PullRequestEventPayload(**self.payload)
        except Exception:
            return None
