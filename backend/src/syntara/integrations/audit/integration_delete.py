"""IntegrationDeleteEvent and handler for integration deletion audit."""

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
from syntara.integrations.audit.constants import OPERATIONAL_LOGS_HINT

# ---------------------------------------------------------------------------
# Domain event
# ---------------------------------------------------------------------------


@dataclass
class IntegrationDeleteEvent:
    """Domain event representing integration deletion.

    The error_type field can be:
    - None: Success (no error)
    - str: Technical exception class name (e.g., "IntegrationNotFoundError")
    """

    integration_id: UUID
    integration_name: str
    tools_deleted: int = field(default=0)
    error_type: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class IntegrationDeleteHandler(AuditEventHandler[IntegrationDeleteEvent]):
    """Maps an IntegrationDeleteEvent to a normalized AuditEvent."""

    def handle(self, event: IntegrationDeleteEvent) -> AuditEvent:
        """Map an IntegrationDeleteEvent to a normalized AuditEvent."""
        action = "integration_deleted"
        is_error = event.error_type is not None

        if is_error:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.ERROR
            status = EventStatus.ERROR
            message = f"Integration deletion failed: {event.integration_name}"
            error_message: str | None = OPERATIONAL_LOGS_HINT
        else:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"Integration deleted: {event.integration_name}"
            error_message = None

        data = AuditContextData(
            data_type="integration-delete-context",
            error_type=event.error_type,
            error_message=error_message,
            integration_name=event.integration_name,
            tools_deleted=event.tools_deleted,
        )

        return AuditEvent(
            event_category=category,
            event_severity=severity,
            event_status=status,
            event_action=action,
            event_message=message,
            source_component="syntara.integrations.integration",
            structured_data=data,
            resource_urn=f"urn:syntara:integration:{event.integration_id}",
            resource_name=event.integration_name,
        )
