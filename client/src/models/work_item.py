"""WorkItem Pydantic models for the work queue.

This module defines the core WorkItem schema used throughout the
orchestration service for tracking and processing work items.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class WorkItemStatus(str, Enum):
    """Status of a work item in the processing pipeline."""

    PENDING = "pending"
    """Work item is waiting to be processed."""

    QUEUED = "queued"
    """Work item has been added to the processing queue."""

    DISPATCHED = "dispatched"
    """Work item has been dispatched to the orchestrator."""

    RUNNING = "running"
    """Work item is currently being processed by the orchestrator."""

    COMPLETED = "completed"
    """Work item has been successfully processed."""

    FAILED = "failed"
    """Work item processing failed with an error."""

    CANCELLED = "cancelled"
    """Work item was cancelled before completion."""

    RETRYING = "retrying"
    """Work item is being retried after a failure."""


class WorkItemPriority(int, Enum):
    """Priority level for work items.

    Higher values indicate higher priority.
    """

    LOW = 1
    """Low priority - background tasks."""

    NORMAL = 5
    """Normal priority - standard processing."""

    HIGH = 10
    """High priority - time-sensitive items."""

    CRITICAL = 20
    """Critical priority - urgent items requiring immediate attention."""


class WorkItemSchema(BaseModel):
    """Schema for a work item in the orchestration queue.

    This model represents a unit of work that needs to be processed
    by the orchestration system. It contains the event information,
    processing state, and metadata.

    Attributes:
        id: Unique identifier for the work item
        event_type: Type of event (e.g., 'issues', 'pull_request')
        action: Action within the event (e.g., 'labeled', 'opened')
        payload: Raw event payload data from GitHub
        status: Current processing status
        priority: Processing priority level
        created_at: Timestamp when the work item was created
        updated_at: Timestamp when the work item was last updated
        started_at: Timestamp when processing started
        completed_at: Timestamp when processing completed
        attempts: Number of processing attempts
        max_attempts: Maximum number of retry attempts
        error_message: Error message if processing failed
        error_details: Detailed error information
        result: Processing result data
        metadata: Additional metadata for processing
    """

    id: str = Field(..., description="Unique identifier for the work item")
    event_type: str = Field(..., description="Type of event from GitHub webhook")
    action: str | None = Field(None, description="Action within the event")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw event payload data",
    )
    status: WorkItemStatus = Field(
        default=WorkItemStatus.PENDING,
        description="Current processing status",
    )
    priority: WorkItemPriority = Field(
        default=WorkItemPriority.NORMAL,
        description="Processing priority level",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the work item was created",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the work item was last updated",
    )
    started_at: datetime | None = Field(
        default=None,
        description="Timestamp when processing started",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Timestamp when processing completed",
    )
    attempts: int = Field(
        default=0,
        ge=0,
        description="Number of processing attempts",
    )
    max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of retry attempts",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if processing failed",
    )
    error_details: dict[str, Any] | None = Field(
        default=None,
        description="Detailed error information",
    )
    result: dict[str, Any] | None = Field(
        default=None,
        description="Processing result data",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata for processing",
    )

    def mark_dispatched(self) -> None:
        """Mark the work item as dispatched to the orchestrator."""
        self.status = WorkItemStatus.DISPATCHED
        self.updated_at = datetime.utcnow()

    def mark_running(self) -> None:
        """Mark the work item as currently being processed."""
        self.status = WorkItemStatus.RUNNING
        self.started_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def mark_completed(self, result: dict[str, Any] | None = None) -> None:
        """Mark the work item as successfully completed.

        Args:
            result: Optional result data from processing
        """
        self.status = WorkItemStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        if result:
            self.result = result

    def mark_failed(
        self,
        error_message: str,
        error_details: dict[str, Any] | None = None,
    ) -> None:
        """Mark the work item as failed.

        Args:
            error_message: Human-readable error message
            error_details: Optional detailed error information
        """
        self.attempts += 1
        self.error_message = error_message
        self.error_details = error_details
        self.updated_at = datetime.utcnow()

        if self.attempts >= self.max_attempts:
            self.status = WorkItemStatus.FAILED
        else:
            self.status = WorkItemStatus.RETRYING

    def can_retry(self) -> bool:
        """Check if the work item can be retried.

        Returns:
            True if the item can be retried, False otherwise
        """
        return self.attempts < self.max_attempts and self.status in (
            WorkItemStatus.FAILED,
            WorkItemStatus.RETRYING,
        )

    class Config:
        """Pydantic model configuration."""

        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
