"""Form prompt domain events and audit handlers.

Emits audit trail events for form prompt creation and submission.
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
from syntara.audit.utils import resolve_actor_type

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from syntara.core.models.principal import PrincipalType


_SOURCE_COMPONENT = "syntara.forms"

# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


@dataclass
class FormPromptExpiredEvent:
    """Domain event fired when a pending form prompt expires due to response window timeout."""

    prompt_id: UUID
    execution_id: UUID
    prompt_node_id: str


@dataclass
class FormPromptSubmittedEvent:
    """Domain event fired when a form prompt is submitted."""

    prompt_id: UUID
    execution_id: UUID
    prompt_node_id: str
    submitted_by: UUID
    submitted_at: datetime
    wait_time_ms: int  # ms between prompt creation and submission
    field_count: int  # number of fields in the submitted form
    outcome: str = field(default="submitted")  # outcome value sent to workflow
    principal_type: PrincipalType | None = field(default=None)


# ---------------------------------------------------------------------------
# Audit handlers (produce AuditEvent for persistence)
# ---------------------------------------------------------------------------


class FormPromptExpiredHandler(AuditEventHandler[FormPromptExpiredEvent]):
    """Maps a FormPromptExpiredEvent to an AuditEvent."""

    def handle(self, event: FormPromptExpiredEvent) -> AuditEvent:
        """Map a FormPromptExpiredEvent to a normalized AuditEvent."""
        from syntara.core.models.principal import PrincipalType  # noqa: PLC0415

        data = AuditContextData(
            data_type="form-prompt-expired",
        )

        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.SUCCESS,
            event_action="form_prompt_expired",
            event_message="Form prompt expired due to response window timeout",
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            actor_type=PrincipalType.SYSTEM,
            execution_id=event.execution_id,
            activity_id=event.prompt_node_id,
            resource_urn=f"urn:syntara:form_prompt:{event.prompt_id}",
            resource_name=event.prompt_node_id,
        )


class FormPromptSubmittedHandler(AuditEventHandler[FormPromptSubmittedEvent]):
    """Maps a FormPromptSubmittedEvent to an AuditEvent."""

    def handle(self, event: FormPromptSubmittedEvent) -> AuditEvent:
        """Map a FormPromptSubmittedEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="form-prompt-submitted",
            outcome=event.outcome,
            wait_time_ms=event.wait_time_ms,
            field_count=event.field_count,
        )

        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="form_prompt_submitted",
            event_message=f"Form prompt submitted with {event.field_count} field(s)",
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            actor_id=event.submitted_by,
            actor_type=resolve_actor_type(actor_id=event.submitted_by, principal_type=event.principal_type),
            execution_id=event.execution_id,
            activity_id=event.prompt_node_id,
            resource_urn=f"urn:syntara:form_prompt:{event.prompt_id}",
            resource_name=event.prompt_node_id,
        )
