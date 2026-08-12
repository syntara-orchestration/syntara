"""FunctionExecutionEvent and FunctionExecutionHandler for @audit decorator."""

from dataclasses import dataclass, field
from typing import Any

from syntara.audit.emitter import AuditActorContext
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData
from syntara.audit.utils import escalate_severity

# ---------------------------------------------------------------------------
# Domain event
# ---------------------------------------------------------------------------


@dataclass
class FunctionExecutionEvent:
    """Domain event for function execution tracked by @audit decorator.

    Captures the complete execution context including arguments, result,
    and error state for audit purposes.
    """

    event_category: EventCategory
    event_action: str
    source_component: str
    actor_context: AuditActorContext
    event_severity: EventSeverity
    function_args: dict[str, Any] = field(default_factory=dict)
    function_result: Any | None = field(default=None)
    error_type: str | None = field(default=None)
    error_message: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class FunctionExecutionHandler(AuditEventHandler[FunctionExecutionEvent]):
    """Maps a FunctionExecutionEvent to a normalized AuditEvent."""

    def handle(self, event: FunctionExecutionEvent) -> AuditEvent:
        """Map a FunctionExecutionEvent to a normalized AuditEvent.

        Args:
            event: The function execution event to handle.

        Returns:
            A normalized AuditEvent for persistence and querying.

        """
        # Extract actor fields from User object
        actor_id = event.actor_context.actor_id
        actor_type = event.actor_context.actor_type
        actor_username = event.actor_context.actor_username

        is_error = event.error_type is not None

        # Build structured data
        structured_data_dict: dict[str, Any] = {
            "data_type": "function",
            "error_type": event.error_type,
            "error_message": event.error_message,
            "function_args": event.function_args,
        }

        # Add function result only if present and not an error
        if event.function_result is not None and not is_error:
            structured_data_dict["function_result"] = event.function_result

        structured_data = AuditContextData(**structured_data_dict)

        if is_error:
            # Escalate severity on error
            severity = escalate_severity(event.event_severity, EventSeverity.ERROR)
            return AuditEvent(
                event_category=event.event_category,
                event_severity=severity,
                event_status=EventStatus.ERROR,
                event_action=f"{event.event_action}_error",
                event_message=f"Function {event.event_action} failed with {event.error_type}",
                source_component=event.source_component,
                structured_data=structured_data,
                actor_id=actor_id,
                actor_type=actor_type,
                actor_username=actor_username,
            )

        # Success path
        return AuditEvent(
            event_category=event.event_category,
            event_severity=event.event_severity,
            event_status=EventStatus.SUCCESS,
            event_action=event.event_action,
            event_message=f"Function {event.event_action} executed successfully",
            source_component=event.source_component,
            structured_data=structured_data,
            actor_id=actor_id,
            actor_type=actor_type,
            actor_username=actor_username,
        )
