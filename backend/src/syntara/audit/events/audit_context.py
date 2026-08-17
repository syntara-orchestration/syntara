"""AuditContextEvent and AuditContextHandler for context-managed audit operations."""

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

# ---------------------------------------------------------------------------
# Domain event
# ---------------------------------------------------------------------------


@dataclass
class AuditContextEvent:
    """Domain event for operations captured via audit_context manager.

    Represents either successful completion or error for an audited operation.
    Error state is determined by the presence of error_type.
    """

    event_category: EventCategory
    event_action: str
    source_component: str
    actor_context: AuditActorContext
    event_severity: EventSeverity
    resource_urn: str | None = field(default=None)
    resource_name: str | None = field(default=None)
    error_type: str | None = field(default=None)
    error_message: str | None = field(default=None)
    context_data: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class AuditContextHandler(AuditEventHandler[AuditContextEvent]):
    """Maps an AuditContextEvent to a normalized AuditEvent."""

    def handle(self, event: AuditContextEvent) -> AuditEvent:
        """Map an AuditContextEvent to a normalized AuditEvent.

        Args:
            event: The audit context event to handle.

        Returns:
            A normalized AuditEvent for persistence and querying.

        """
        # Extract actor fields from User object
        actor_id = event.actor_context.actor_id
        actor_type = event.actor_context.actor_type
        actor_username = event.actor_context.actor_username

        # Determine if this is an error based on presence of error_type
        is_error = event.error_type is not None

        if is_error:
            # Error path: include error details in structured data
            structured_data = AuditContextData(
                data_type="context",
                error_type=event.error_type,
                error_message=event.error_message,
                **event.context_data,
            )
            return AuditEvent(
                event_category=event.event_category,
                event_severity=event.event_severity,
                event_status=EventStatus.ERROR,
                event_action=f"{event.event_action}_error",
                event_message=f"Operation {event.event_action} failed with {event.error_type}",
                source_component=event.source_component,
                resource_urn=event.resource_urn,
                resource_name=event.resource_name,
                structured_data=structured_data,
                actor_id=actor_id,
                actor_type=actor_type,
                actor_username=actor_username,
            )

        # Success path
        structured_data = AuditContextData(data_type="context", **event.context_data)
        return AuditEvent(
            event_category=event.event_category,
            event_severity=event.event_severity,
            event_status=EventStatus.SUCCESS,
            event_action=event.event_action,
            event_message=f"Operation {event.event_action} completed successfully",
            source_component=event.source_component,
            resource_urn=event.resource_urn,
            resource_name=event.resource_name,
            structured_data=structured_data,
            actor_id=actor_id,
            actor_type=actor_type,
            actor_username=actor_username,
        )
