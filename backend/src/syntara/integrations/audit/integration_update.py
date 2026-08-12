"""IntegrationUpdateEvent and handler for integration update audit."""

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
class IntegrationUpdateEvent:
    """Domain event representing integration update.

    The error_type field can be:
    - None: Success (no error)
    - str: Technical exception class name (e.g., "IntegrationNameConflictError", "IntegrationNotFoundError")
    """

    integration_id: UUID
    integration_name: str
    updated_fields: list[str] = field(default_factory=list)
    integration_type: str | None = field(default=None)
    error_type: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class IntegrationUpdateHandler(AuditEventHandler[IntegrationUpdateEvent]):
    """Maps an IntegrationUpdateEvent to a normalized AuditEvent."""

    def handle(self, event: IntegrationUpdateEvent) -> AuditEvent:
        """Map an IntegrationUpdateEvent to a normalized AuditEvent."""
        action = "integration_updated"
        is_error = event.error_type is not None

        if is_error:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.ERROR
            status = EventStatus.ERROR
            message = f"Integration update failed: {event.integration_name}"
            error_message: str | None = OPERATIONAL_LOGS_HINT
        else:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"Integration updated: {event.integration_name}"
            error_message = None

        data = AuditContextData(
            data_type="integration-update-context",
            error_type=event.error_type,
            error_message=error_message,
            integration_name=event.integration_name,
            integration_type=event.integration_type,
            updated_fields=event.updated_fields,
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
