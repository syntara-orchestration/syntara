"""ToolBulkUpdateEvent and handler for tool bulk update audit."""

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
class ToolBulkUpdateEvent:
    """Domain event representing tool bulk update operation.

    The error_type field can be:
    - None: Success (no error)
    - str: Technical exception class name (e.g., "ToolBulkUpdateValidationError")
    """

    tool_ids: list[UUID] = field(default_factory=list)
    enabled: bool = field(default=False)
    updated_count: int = field(default=0)
    skipped_count: int = field(default=0)
    duplicate_count: int = field(default=0)
    not_found_count: int = field(default=0)
    error_type: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class ToolBulkUpdateHandler(AuditEventHandler[ToolBulkUpdateEvent]):
    """Maps a ToolBulkUpdateEvent to a normalized AuditEvent."""

    def handle(self, event: ToolBulkUpdateEvent) -> AuditEvent:
        """Map a ToolBulkUpdateEvent to a normalized AuditEvent."""
        action = "tools_bulk_updated"
        is_error = event.error_type is not None

        if is_error:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.ERROR
            status = EventStatus.ERROR
            message = f"Tool bulk update failed: requested {len(event.tool_ids)} tools"
            error_message: str | None = "Look at the Operational Logs for full diagnosis"
        else:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            enabled_str = "enabled" if event.enabled else "disabled"
            message = f"Tool bulk update completed: {event.updated_count} tools {enabled_str}" + (
                f", {event.skipped_count} skipped" if event.skipped_count > 0 else ""
            )
            error_message = None

        data = AuditContextData(
            data_type="tool-bulk-update-context",
            error_type=event.error_type,
            error_message=error_message,
            tool_count=len(event.tool_ids),
            enabled=event.enabled,
            updated_count=event.updated_count,
            skipped_count=event.skipped_count,
            duplicate_count=event.duplicate_count,
            not_found_count=event.not_found_count,
        )

        return AuditEvent(
            event_category=category,
            event_severity=severity,
            event_status=status,
            event_action=action,
            event_message=message,
            source_component="syntara.tool_manager.tool",
            structured_data=data,
            resource_urn=None,  # Bulk operation has no single resource
            resource_name=None,
        )
