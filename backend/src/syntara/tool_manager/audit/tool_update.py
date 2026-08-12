"""ToolUpdateEvent and handler for tool update audit."""

from dataclasses import dataclass, field
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
class ToolUpdateEvent:
    """Domain event representing tool update operation.

    The error_type field can be:
    - None: Success (no error)
    - str: Technical exception class name (e.g., "ToolNotFoundError")
    """

    tool_id: UUID
    tool_name: str
    namespaced_name: str
    integration_id: UUID | None
    updated_fields: list[str] = field(default_factory=list)
    error_type: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class ToolUpdateHandler(AuditEventHandler[ToolUpdateEvent]):
    """Maps a ToolUpdateEvent to a normalized AuditEvent."""

    def handle(self, event: ToolUpdateEvent) -> AuditEvent:
        """Map a ToolUpdateEvent to a normalized AuditEvent."""
        action = "tool_updated"
        is_error = event.error_type is not None

        if is_error:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.ERROR
            status = EventStatus.ERROR
            message = f"Tool update failed: {event.tool_name}"
            error_message: str | None = "Look at the Operational Logs for full diagnosis"
        else:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            fields_str = ", ".join(event.updated_fields) if event.updated_fields else "none"
            message = f"Tool updated: {event.tool_name} (fields: {fields_str})"
            error_message = None

        data = AuditContextData(
            data_type="tool-update-context",
            error_type=event.error_type,
            error_message=error_message,
            tool_name=event.tool_name,
            namespaced_name=event.namespaced_name,
            integration_id=str(event.integration_id) if event.integration_id else None,
            updated_fields=event.updated_fields,
        )

        return AuditEvent(
            event_category=category,
            event_severity=severity,
            event_status=status,
            event_action=action,
            event_message=message,
            source_component="syntara.tool_manager.tool",
            structured_data=data,
            resource_urn=f"urn:syntara:tool:{event.tool_id}",
            resource_name=event.tool_name,
        )
