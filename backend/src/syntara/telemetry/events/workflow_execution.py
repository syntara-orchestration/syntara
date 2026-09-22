"""Workflow execution telemetry event models.

Defines SQLModel models for workflow execution start and completion events.
"""

from __future__ import annotations

from uuid import UUID  # noqa: TC003

from sqlmodel import Field

from syntara.telemetry.events.base import BaseTelemetryEvent
from syntara.workflows.models.execution import ExecutionMode  # noqa: TC001
from syntara.workflows.workflow_engine.models.workflow_definition import (  # noqa: TC001
    ActivityName,
    WorkflowTerminalStatus,
)


class WorkflowExecutionStartEvent(BaseTelemetryEvent):
    """Telemetry event emitted when workflow execution begins.

    Attributes:
        workflow_execution_id: Unique workflow execution identifier (UUID v4 format).
        workflow_id: Parent workflow identifier (UUID v4 format).
        trigger_type: Type of trigger that started the workflow (e.g. manual_trigger).
        interface: Originating interface (ui or api).
        mode: Execution mode (standard, test, debug).
        workflow_version: Sequential version number of the workflow definition that ran.
        used_published: Whether the run executed the workflow's published version.
        is_retry: Whether this run was started as a retry of a previous execution.

    """

    workflow_execution_id: UUID = Field(description="Unique workflow execution identifier (UUID v4)")
    workflow_id: UUID | None = Field(default=None, description="Parent workflow identifier (UUID v4)")
    trigger_type: ActivityName | None = Field(default=None, description="Type of trigger that started the workflow")
    interface: str | None = Field(default=None, description="Originating interface (ui or api)")
    mode: ExecutionMode | None = Field(default=None, description="Execution mode (standard, test, debug)")
    workflow_version: int | None = Field(default=None, description="Version number of the workflow definition that ran")
    used_published: bool | None = Field(
        default=None,
        description="Whether the run executed the workflow's published version",
    )
    is_retry: bool = Field(default=False, description="Whether this run was started as a retry")


class WorkflowExecutionCompletedEvent(BaseTelemetryEvent):
    """Telemetry event emitted when workflow execution finishes.

    Attributes:
        workflow_execution_id: Unique workflow execution identifier (UUID v4 format).
        workflow_id: Parent workflow identifier (UUID v4 format).
        status: Final execution status.
        duration_ms: Duration in milliseconds.
        node_count: Total number of nodes executed.
        error_count: Number of nodes that failed.
        error_type: Categorized error type if the workflow failed
            (``WorkflowTimedOut`` for engine-level timeouts,
            ``ActivityExecutionError`` for other failures); null otherwise.
        trigger_type: Type of trigger that started the workflow.
        interface: Originating interface (ui or api).
        mode: Execution mode (standard, test, debug).
        workflow_version: Sequential version number of the workflow definition that ran.
        used_published: Whether the run executed the workflow's published version.
        is_retry: Whether this run was started as a retry of a previous execution.

    """

    workflow_execution_id: UUID = Field(description="Unique workflow execution identifier (UUID v4)")
    workflow_id: UUID | None = Field(default=None, description="Parent workflow identifier (UUID v4)")
    status: WorkflowTerminalStatus
    duration_ms: int = Field(ge=0, description="Duration in milliseconds")
    node_count: int = Field(ge=0, description="Total number of nodes executed")
    error_count: int = Field(ge=0, description="Number of nodes that failed")
    error_type: str | None = Field(
        default=None,
        description=(
            "Categorized error type if the workflow failed "
            "(`WorkflowTimedOut` for engine-level timeouts, "
            "`ActivityExecutionError` for other failures); null otherwise"
        ),
    )
    trigger_type: ActivityName | None = Field(default=None, description="Type of trigger that started the workflow")
    interface: str | None = Field(default=None, description="Originating interface (ui or api)")
    mode: ExecutionMode | None = Field(default=None, description="Execution mode (standard, test, debug)")
    workflow_version: int | None = Field(default=None, description="Version number of the workflow definition that ran")
    used_published: bool | None = Field(
        default=None,
        description="Whether the run executed the workflow's published version",
    )
    is_retry: bool = Field(default=False, description="Whether this run was started as a retry")
