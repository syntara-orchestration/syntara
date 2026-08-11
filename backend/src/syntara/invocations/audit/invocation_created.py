"""InvocationCreatedEvent and InvocationCreatedHandler for invocations-domain audit."""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData

# ---------------------------------------------------------------------------
# Domain event
# ---------------------------------------------------------------------------


@dataclass
class InvocationCreatedEvent:
    """Domain event representing an invocation creation attempt.

    Captures the complete request context. PII sanitization is handled
    by the audit framework in emitter.py.

    The error_type field can be:
    - None: Success (no error)
    - str: Technical exception class name (e.g., "SQLAlchemyError", "OSError")
    """

    invocation_id: UUID
    session_id: str
    file_ids: list[str] = field(default_factory=list)
    agent: str | None = None
    model: str | None = None
    metadata: dict[str, Any] | None = None
    error_type: str | None = field(default=None)
    activity_id: str | None = field(default=None)
    activity_name: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class InvocationCreatedHandler(AuditEventHandler[InvocationCreatedEvent]):
    """Maps an InvocationCreatedEvent to a normalized AuditEvent."""

    def handle(self, event: InvocationCreatedEvent) -> AuditEvent:
        """Map an InvocationCreatedEvent to a normalized AuditEvent."""
        action = "invocation_created"
        is_error = event.error_type is not None

        if is_error:
            # Technical exception
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.ERROR
            status = EventStatus.ERROR
            message = "Invocation creation failed due to system error"
            error_message: str | None = "Look at the Operational Logs for full diagnosis"
            error_type_str = event.error_type
        else:
            # Success
            category = EventCategory.USER_ACTION
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"Invocation created for session {event.session_id}"
            error_message = None
            error_type_str = None

        data = AuditContextData(
            data_type="invocation-created-context",
            error_type=error_type_str,
            error_message=error_message,
            invocation_id=event.invocation_id,
            session_id=event.session_id,
            file_ids=event.file_ids,
            agent=event.agent,
            model=event.model,
            metadata=event.metadata,
        )

        return AuditEvent(
            event_category=category,
            event_severity=severity,
            event_status=status,
            event_action=action,
            event_message=message,
            source_component="syntara.invocations.create",
            structured_data=data,
            activity_id=event.activity_id,
            resource_urn=f"urn:syntara:invocation:{event.invocation_id}",
            resource_name=event.activity_name,
        )
