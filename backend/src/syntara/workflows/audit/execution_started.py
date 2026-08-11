"""Workflow execution started — domain event and audit handler.

Fired by ActivitySyncService when a workflow execution transitions from
PENDING to RUNNING in Temporal.
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
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName  # noqa: TC001

if TYPE_CHECKING:
    from uuid import UUID


@dataclass
class WorkflowStartEvent:
    """Domain event fired when a workflow execution begins."""

    execution_id: UUID
    workflow_id: UUID
    workflow_name: str
    trigger_type: ActivityName | None = field(default=None)
    interface: str | None = field(default=None)
    request_id: UUID | None = field(default=None)


class WorkflowStartHandler(AuditEventHandler[WorkflowStartEvent]):
    """Maps a WorkflowStartEvent to an AuditEvent."""

    def handle(self, event: WorkflowStartEvent) -> AuditEvent:
        """Map a WorkflowStartEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="workflow-execution-started",
            workflow_name=event.workflow_name,
        )
        if event.trigger_type is not None:
            data.trigger_type = event.trigger_type.value
        if event.interface is not None:
            data.interface = event.interface

        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="workflow_execution_started",
            event_message=f"Workflow execution started: {event.workflow_name}",
            source_component="syntara.workflows",
            structured_data=data,
            workflow_id=event.workflow_id,
            execution_id=event.execution_id,
            resource_urn=f"urn:syntara:workflow:{event.workflow_id}",
            resource_name=event.workflow_name,
        )
