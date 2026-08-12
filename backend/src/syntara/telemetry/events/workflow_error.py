"""Workflow error telemetry event model.

Defines the event emitted for engine-level (Temporal) workflow errors:
timeouts and automatic retries. Distinct from tool-level timeouts
tracked by ToolExecutionEvent.
"""

from __future__ import annotations

from enum import StrEnum

from sqlmodel import Field

from syntara.telemetry.events.base import BaseTelemetryEvent

RETRY_REASON_MAX_LENGTH = 500


class TimedOutComponent(StrEnum):
    """Component that timed out in a workflow."""

    WORKFLOW = "workflow"
    ACTIVITY = "activity"


class WorkflowErrorEvent(BaseTelemetryEvent):
    """Telemetry event emitted when a workflow or activity times out at the engine level.

    Attributes:
        workflow_execution_id: Unique workflow execution identifier (UUID v4).
        timed_out_component: Whether the timeout occurred at the workflow or activity level.
        configured_timeout_seconds: The timeout threshold that was configured.
        elapsed_time_ms: Actual elapsed time before the timeout fired.
        activity_id: Activity node ID, populated only for activity-level timeouts.

    """

    workflow_execution_id: str = Field(description="Unique workflow execution identifier (UUID v4)")
    timed_out_component: TimedOutComponent = Field(
        description="Whether the workflow or an activity timed out",
    )
    configured_timeout_seconds: float = Field(
        ge=0,
        description="Configured timeout threshold in seconds",
    )
    elapsed_time_ms: int = Field(
        ge=0,
        description="Actual elapsed time in milliseconds before timeout",
    )
    activity_id: str | None = Field(
        default=None,
        description="Activity node ID (only for activity-level timeouts)",
    )
    retry_count: int = Field(
        default=0,
        ge=0,
        description="Number of retry attempts before timeout (0 = first attempt)",
    )
    error_type: str | None = Field(
        default=None,
        description="Name of the exception that caused the error",
    )
    retry_reason: str | None = Field(
        default=None,
        max_length=RETRY_REASON_MAX_LENGTH,
        description="Failure message from the previous attempt, truncated (only for retry events)",
    )
