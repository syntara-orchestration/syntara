"""Form prompt lifecycle events and audit handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.audit.utils import resolve_actor_type
from syntara.core.models.principal import PrincipalType

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID


_SOURCE_COMPONENT = "syntara.forms"


@dataclass
class FormPromptCreatedEvent:
    """Fired after a workflow creates a form prompt."""

    prompt_id: UUID
    workflow_id: UUID
    execution_id: UUID
    prompt_node_id: str
    initiated_by: UUID
    created_at: datetime


@dataclass
class FormPromptSubmittedEvent:
    """Fired after a user successfully submits a form prompt."""

    prompt_id: UUID
    workflow_id: UUID | None
    execution_id: UUID
    prompt_node_id: str
    submitted_by: UUID
    submitted_at: datetime
    wait_time_ms: int
    field_count: int
    outcome: str = "submitted"
    principal_type: PrincipalType | None = None


@dataclass
class FormPromptExpiredEvent:
    """Fired when a pending prompt transitions to expired after its timeout."""

    prompt_id: UUID
    workflow_id: UUID | None
    execution_id: UUID
    prompt_node_id: str
    initiated_by: UUID | None
    expired_at: datetime
    timeout_at: datetime | None = None


class FormPromptCreatedHandler(AuditEventHandler[FormPromptCreatedEvent]):
    """Map a prompt-created domain event to the standard audit schema."""

    def handle(self, event: FormPromptCreatedEvent) -> AuditEvent:
        """Convert a creation event into its persisted audit representation."""
        data = AuditContextData(
            data_type="form-prompt-created",
            initiated_by=event.initiated_by,
            created_at=event.created_at,
        )
        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="form_prompt_created",
            event_message="Form prompt created during workflow execution",
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            actor_type=PrincipalType.SYSTEM,
            workflow_id=event.workflow_id,
            execution_id=event.execution_id,
            activity_id=event.prompt_node_id,
            resource_urn=f"urn:syntara:form_prompt:{event.prompt_id}",
            resource_name=event.prompt_node_id,
        )


class FormPromptSubmittedHandler(AuditEventHandler[FormPromptSubmittedEvent]):
    """Map a prompt-submitted domain event to the standard audit schema."""

    def handle(self, event: FormPromptSubmittedEvent) -> AuditEvent:
        """Convert a submission event into its persisted audit representation."""
        data = AuditContextData(
            data_type="form-prompt-submitted",
            outcome=event.outcome,
            submitted_at=event.submitted_at,
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
            workflow_id=event.workflow_id,
            execution_id=event.execution_id,
            activity_id=event.prompt_node_id,
            resource_urn=f"urn:syntara:form_prompt:{event.prompt_id}",
            resource_name=event.prompt_node_id,
        )


class FormPromptExpiredHandler(AuditEventHandler[FormPromptExpiredEvent]):
    """Map a prompt-expired domain event to the standard audit schema."""

    def handle(self, event: FormPromptExpiredEvent) -> AuditEvent:
        """Convert an expiry event into its persisted audit representation."""
        data = AuditContextData(
            data_type="form-prompt-expired",
            initiated_by=event.initiated_by,
            expired_at=event.expired_at,
            timeout_at=event.timeout_at,
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
            workflow_id=event.workflow_id,
            execution_id=event.execution_id,
            activity_id=event.prompt_node_id,
            resource_urn=f"urn:syntara:form_prompt:{event.prompt_id}",
            resource_name=event.prompt_node_id,
        )
