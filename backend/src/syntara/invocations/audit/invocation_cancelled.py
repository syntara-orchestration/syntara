"""InvocationCancelledEvent and InvocationCancelledHandler for invocations-domain audit."""

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from syntara.agent_orchestrator.models import InvocationStatus
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData

# ---------------------------------------------------------------------------
# Helper types
# ---------------------------------------------------------------------------


class InvocationCancellationResult(StrEnum):
    """Result of an invocation cancellation attempt."""

    SUCCESS = "success"
    NOT_FOUND = "not_found"
    NOT_CANCELLABLE = "not_cancellable"


# ---------------------------------------------------------------------------
# Domain event
# ---------------------------------------------------------------------------


@dataclass
class InvocationCancelledEvent:
    """Domain event representing an invocation cancellation attempt.

    The error_type field can be:
    - None: Success or business error (NOT_FOUND, NOT_CANCELLABLE)
    - str: Technical exception class name (e.g., "SQLAlchemyError")
    """

    invocation_id: UUID
    result: InvocationCancellationResult
    reason: str
    files_cleaned: list[UUID] = field(default_factory=list)
    current_status: InvocationStatus | None = field(default=None)
    error_type: str | None = field(default=None)
    activity_id: str | None = field(default=None)
    activity_name: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class InvocationCancelledHandler(AuditEventHandler[InvocationCancelledEvent]):
    """Maps an InvocationCancelledEvent to a normalized AuditEvent."""

    def handle(self, event: InvocationCancelledEvent) -> AuditEvent:
        """Map an InvocationCancelledEvent to a normalized AuditEvent."""
        action = "invocation_cancelled"
        is_error = event.error_type is not None
        error_message: str | None = None

        if is_error:
            # Technical exception
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.ERROR
            status = EventStatus.ERROR
            message = "Invocation cancellation failed due to system error"
            error_message = "Look at the Operational Logs for full diagnosis"
            error_type_str = event.error_type
        elif event.result == InvocationCancellationResult.SUCCESS:
            # Success
            category = EventCategory.USER_ACTION
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"Invocation cancelled: {event.reason}"
            error_type_str = None
        elif event.result == InvocationCancellationResult.NOT_FOUND:
            # Business error - not found
            category = EventCategory.USER_ACTION
            severity = EventSeverity.WARNING
            status = EventStatus.ERROR
            message = "Invocation cancellation failed (not found)"
            error_message = message
            error_type_str = None
        else:
            # Business error - not cancellable
            category = EventCategory.USER_ACTION
            severity = EventSeverity.WARNING
            status = EventStatus.ERROR
            message = f"Invocation cancellation failed (status: {event.current_status})"
            error_message = message
            error_type_str = None

        data = AuditContextData(
            data_type="invocation-cancelled-context",
            error_type=error_type_str,
            error_message=error_message,
            invocation_id=event.invocation_id,
            cancellation_result=event.result.value,
            cancellation_reason=event.reason,
            files_cleaned=event.files_cleaned,
            current_status=event.current_status,
        )

        return AuditEvent(
            event_category=category,
            event_severity=severity,
            event_status=status,
            event_action=action,
            event_message=message,
            source_component="syntara.invocations.cancel",
            structured_data=data,
            activity_id=event.activity_id,
            resource_urn=f"urn:syntara:invocation:{event.invocation_id}",
            resource_name=event.activity_name,
        )
