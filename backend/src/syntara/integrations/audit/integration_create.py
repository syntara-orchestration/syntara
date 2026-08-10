"""IntegrationCreateEvent and handler for integration creation audit."""

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
from syntara.integrations.models.integration import IntegrationStatus

# ---------------------------------------------------------------------------
# Domain event
# ---------------------------------------------------------------------------


@dataclass
class IntegrationCreateEvent:
    """Domain event representing integration creation.

    The error_type field can be:
    - None: Success (no error)
    - str: Technical exception class name (e.g., "IntegrityError")
    """

    integration_id: UUID
    integration_name: str
    integration_type: str
    description: str | None = field(default=None)
    initial_status: IntegrationStatus = field(default=IntegrationStatus.VALIDATING)
    error_type: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class IntegrationCreateHandler(AuditEventHandler[IntegrationCreateEvent]):
    """Maps an IntegrationCreateEvent to a normalized AuditEvent."""

    def handle(self, event: IntegrationCreateEvent) -> AuditEvent:
        """Map an IntegrationCreateEvent to a normalized AuditEvent."""
        action = "integration_created"
        is_error = event.error_type is not None

        if is_error:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.ERROR
            status = EventStatus.ERROR
            message = f"Integration creation failed: {event.integration_name}"
            error_message: str | None = OPERATIONAL_LOGS_HINT
        else:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"Integration created: {event.integration_name}"
            error_message = None

        data = AuditContextData(
            data_type="integration-create-context",
            error_type=event.error_type,
            error_message=error_message,
            integration_type=event.integration_type,
            integration_name=event.integration_name,
            description=event.description,
            initial_status=event.initial_status.value,
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
