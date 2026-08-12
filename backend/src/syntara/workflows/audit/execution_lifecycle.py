"""Execution lifecycle — domain event and audit handler.

Fired by ExecutionService when a user starts or cancels an execution via
the API.  This records the API-level intent; the actual Temporal state
transitions are tracked separately by WorkflowStartEvent (PENDING →
RUNNING) and WorkflowCompletedEvent (terminal state).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
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


class ExecutionAction(StrEnum):
    """Actions that can occur during an execution lifecycle."""

    STARTED = "started"
    CANCELLED = "cancelled"


@dataclass
class ExecutionLifecycleEvent:
    """Domain event fired when an execution lifecycle action completes."""

    execution_id: UUID
    workflow_id: UUID
    workflow_name: str
    action: ExecutionAction
    mode: str | None = field(default=None)
    error_type: str | None = field(default=None)


class ExecutionLifecycleHandler(AuditEventHandler[ExecutionLifecycleEvent]):
    """Maps an ExecutionLifecycleEvent to an AuditEvent."""

    def handle(self, event: ExecutionLifecycleEvent) -> AuditEvent:
        """Map an ExecutionLifecycleEvent to a normalized AuditEvent."""
        is_error = event.error_type is not None

        data = AuditContextData(
            data_type="execution-lifecycle",
            action=event.action,
            workflow_name=event.workflow_name,
        )
        if event.mode is not None:
            data.mode = event.mode
        if is_error:
            data.error_type = event.error_type

        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.ERROR if is_error else EventSeverity.INFO,
            event_status=EventStatus.ERROR if is_error else EventStatus.SUCCESS,
            event_action=f"execution_{event.action}",
            event_message=f"Execution {event.action}: {event.workflow_name}",
            source_component="syntara.workflows",
            structured_data=data,
            workflow_id=event.workflow_id,
            execution_id=event.execution_id,
            resource_urn=f"urn:syntara:workflow:{event.workflow_id}",
            resource_name=event.workflow_name,
        )
