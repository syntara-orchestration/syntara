"""IntegrationDiscoverEvent and handler for integration discovery audit.

Discover is a test-connection operation on an unsaved integration. No
database writes occur; the event captures whether the probe succeeded and
how many resources (tools, models) were found.
"""

from dataclasses import dataclass, field

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
class IntegrationDiscoverEvent:
    """Domain event representing a test-connection discovery probe.

    The error_type field can be:
    - None: Success (discover succeeded)
    - str: Technical exception class name or sentinel (e.g., "DiscoverFailed", "TimeoutError")
    """

    integration_type: str
    tools_found_count: int = field(default=0)
    models_found_count: int = field(default=0)
    error_type: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class IntegrationDiscoverHandler(AuditEventHandler[IntegrationDiscoverEvent]):
    """Maps an IntegrationDiscoverEvent to a normalized AuditEvent."""

    def handle(self, event: IntegrationDiscoverEvent) -> AuditEvent:
        """Map an IntegrationDiscoverEvent to a normalized AuditEvent."""
        action = "integration_discovered"
        is_error = event.error_type is not None

        if is_error:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.WARNING
            status = EventStatus.ERROR
            message = f"Integration discovery failed: {event.integration_type}"
            error_message: str | None = OPERATIONAL_LOGS_HINT
        else:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"Integration discovery successful: {event.integration_type}"
            error_message = None

        data = AuditContextData(
            data_type="integration-discover-context",
            error_type=event.error_type,
            error_message=error_message,
            integration_type=event.integration_type,
            tools_found_count=event.tools_found_count,
            models_found_count=event.models_found_count,
        )

        return AuditEvent(
            event_category=category,
            event_severity=severity,
            event_status=status,
            event_action=action,
            event_message=message,
            source_component="syntara.integrations.integration",
            structured_data=data,
        )
