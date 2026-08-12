"""Workflow execution completed — domain event and audit handler.

Fired by ActivitySyncService when a workflow execution reaches a terminal
state (COMPLETED, FAILED, or CANCELLED) in Temporal.  Captures execution
summary metrics: duration, node count, and error count.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, WorkflowTerminalStatus

if TYPE_CHECKING:
    from uuid import UUID


@dataclass
class WorkflowCompletedEvent:
    """Domain event fired when a workflow execution reaches a terminal state."""

    execution_id: UUID
    workflow_id: UUID
    status: WorkflowTerminalStatus
    duration_ms: int
    node_count: int
    error_count: int
    error_type: str | None = field(default=None)
    trigger_type: ActivityName | None = field(default=None)
    interface: str | None = field(default=None)
    request_id: UUID | None = field(default=None)
    workflow_name: str | None = field(default=None)


_STATUS_MESSAGE: dict[WorkflowTerminalStatus, str] = {
    WorkflowTerminalStatus.COMPLETED: "Workflow execution completed",
    WorkflowTerminalStatus.FAILED: "Workflow execution failed",
    WorkflowTerminalStatus.CANCELLED: "Workflow execution cancelled",
}


class WorkflowCompletedHandler(AuditEventHandler[WorkflowCompletedEvent]):
    """Maps a WorkflowCompletedEvent to an AuditEvent."""

    def handle(self, event: WorkflowCompletedEvent) -> AuditEvent:
        """Map a WorkflowCompletedEvent to a normalized AuditEvent."""
        is_failure = event.status == WorkflowTerminalStatus.FAILED

        data = AuditContextData(
            data_type="workflow-execution-completed",
            error_type=event.error_type,
            status=event.status.value,
            duration_ms=event.duration_ms,
            node_count=event.node_count,
            error_count=event.error_count,
        )
        if event.trigger_type is not None:
            data.trigger_type = event.trigger_type.value
        if event.interface is not None:
            data.interface = event.interface

        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.ERROR if is_failure else EventSeverity.INFO,
            event_status=EventStatus.ERROR if is_failure else EventStatus.SUCCESS,
            event_action="workflow_execution_completed",
            event_message=_STATUS_MESSAGE.get(event.status, "Workflow execution completed"),
            source_component="syntara.workflows",
            structured_data=data,
            execution_id=event.execution_id,
            workflow_id=event.workflow_id,
            resource_urn=f"urn:syntara:workflow:{event.workflow_id}",
            resource_name=event.workflow_name,
        )
