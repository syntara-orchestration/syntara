"""Form-trigger submission audit events and handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.audit.utils import resolve_actor_type

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from syntara.core.models.principal import PrincipalType


_SOURCE_COMPONENT = "syntara.workflows"


@dataclass
class FormTriggerSubmittedEvent:
    """Fired after a form-trigger submission has started and committed an execution.

    ``field_count`` is the number of form fields.
    """

    workflow_id: UUID
    workflow_name: str
    execution_id: UUID
    trigger_node_id: str
    submitted_by: UUID
    submitted_at: datetime
    field_count: int
    field_types: list[str]
    principal_type: PrincipalType | None = None


class FormTriggerSubmittedHandler(AuditEventHandler[FormTriggerSubmittedEvent]):
    """Map a form-trigger submission event to the standard audit schema."""

    def handle(self, event: FormTriggerSubmittedEvent) -> AuditEvent:
        """Convert the submission event to a metadata-only audit record."""
        data = AuditContextData(
            data_type="form-trigger-submitted",
            submitted_at=event.submitted_at,
            field_count=event.field_count,
            field_types=event.field_types,
        )
        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="form_trigger_submitted",
            event_message=f"Form trigger submitted with {event.field_count} field(s)",
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            actor_id=event.submitted_by,
            actor_type=resolve_actor_type(actor_id=event.submitted_by, principal_type=event.principal_type),
            workflow_id=event.workflow_id,
            execution_id=event.execution_id,
            activity_id=event.trigger_node_id,
            resource_urn=f"urn:syntara:workflow:{event.workflow_id}",
            resource_name=event.workflow_name,
        )
