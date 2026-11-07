"""Data models for service layer responses.

These models provide type-safe, structured responses from service operations.
"""

from typing import Any

from pydantic import BaseModel, Field


class WorkflowStartResponse(BaseModel):
    """Response from starting a workflow execution.

    Attributes:
        execution_id: Internal execution identifier (database record)
        workflow_id: Internal workflow identifier
        temporal_workflow_id: Temporal workflow ID (use for Temporal API calls)
        temporal_run_id: Temporal run ID (specific execution run)
        status: Current workflow status
        started_at: ISO 8601 timestamp when workflow started

    """

    execution_id: str = Field(..., description="Internal execution identifier")
    workflow_id: str = Field(..., description="Internal workflow identifier")
    temporal_workflow_id: str = Field(..., description="Temporal workflow ID for API calls")
    temporal_run_id: str | None = Field(None, description="Temporal run ID")
    status: str = Field(..., description="Workflow execution status")
    started_at: str = Field(..., description="ISO 8601 timestamp when workflow started")


class WorkflowStatusResponse(BaseModel):
    """Response from querying workflow status.

    Attributes:
        temporal_workflow_id: Temporal workflow ID
        temporal_run_id: Temporal run ID
        status: Current workflow status
        start_time: ISO 8601 timestamp when workflow started (None if not started)
        close_time: ISO 8601 timestamp when workflow completed (None if still running)
        failure_message: Error message if workflow failed (None if not failed)

    """

    temporal_workflow_id: str = Field(..., description="Temporal workflow ID")
    temporal_run_id: str = Field(..., description="Temporal run ID")
    status: str = Field(..., description="Workflow status (running, completed, failed, etc.)")
    start_time: str | None = Field(None, description="ISO 8601 start timestamp")
    close_time: str | None = Field(None, description="ISO 8601 close timestamp")
    failure_message: str | None = Field(None, description="Error message if workflow failed")


class WorkflowResultResponse(BaseModel):
    """Response from getting workflow execution result.

    Attributes:
        status: Final workflow status
        execution_id: Internal execution identifier
        activity_outputs: Dictionary of activity outputs keyed by activity ID
        completed_activities: List of completed activity IDs

    """

    status: str = Field(..., description="Final workflow status")
    execution_id: str = Field(..., description="Internal execution identifier")
    activity_outputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Activity outputs keyed by activity ID",
    )
    completed_activities: list[str] = Field(
        default_factory=list,
        description="List of completed activity IDs",
    )
