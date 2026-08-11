"""Workflow execution error — domain event and audit handler.

Fired by ActivitySyncService when the Temporal engine reports a
workflow-level or activity-level timeout, or an activity retry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData

if TYPE_CHECKING:
    from uuid import UUID

    from syntara.telemetry.events.workflow_error import TimedOutComponent


@dataclass
class WorkflowExecutionErrorEvent:
    """Domain event fired for engine-level workflow/activity timeouts and retries."""

    execution_id: UUID
    workflow_id: UUID | None
    timed_out_component: TimedOutComponent
    configured_timeout_seconds: float
    elapsed_time_ms: int
    activity_id: str | None = field(default=None)
    retry_count: int = field(default=0)
    error_type: str | None = field(default=None)
    retry_reason: str | None = field(default=None)
    request_id: UUID | None = field(default=None)
    workflow_name: str | None = field(default=None)


class WorkflowExecutionErrorHandler(AuditEventHandler[WorkflowExecutionErrorEvent]):
    """Maps a WorkflowExecutionErrorEvent to a normalized AuditEvent."""

    def handle(self, event: WorkflowExecutionErrorEvent) -> AuditEvent:
        """Map a WorkflowExecutionErrorEvent to a normalized AuditEvent."""
        component = str(event.timed_out_component.value)
        message = f"Workflow engine error: {component} {event.error_type or 'timeout'}"

        data = AuditContextData(
            data_type="workflow-execution-error",
            error_type=event.error_type,
            timed_out_component=component,
            configured_timeout_seconds=event.configured_timeout_seconds,
            elapsed_time_ms=event.elapsed_time_ms,
            retry_count=event.retry_count,
            retry_reason=event.retry_reason,
        )

        resource_urn = f"urn:syntara:workflow:{event.workflow_id}" if event.workflow_id else None

        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.ERROR,
            event_status=EventStatus.ERROR,
            event_action="workflow_execution_error",
            event_message=message,
            source_component="syntara.workflows.engine",
            structured_data=data,
            execution_id=event.execution_id,
            workflow_id=event.workflow_id,
            activity_id=event.activity_id,
            resource_urn=resource_urn,
            resource_name=event.workflow_name,
        )
