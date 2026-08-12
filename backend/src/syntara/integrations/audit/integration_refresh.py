"""IntegrationRefreshEvent and handler for integration resource-refresh audit.

Refresh discovers and syncs tools from a saved integration's MCP server.
This event captures the outcome and the resulting tool counts.
"""

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
from syntara.integrations.models.integration import IntegrationRefreshStatus

# ---------------------------------------------------------------------------
# Domain event
# ---------------------------------------------------------------------------


@dataclass
class IntegrationRefreshEvent:
    """Domain event representing an integration resource refresh.

    The error_type field can be:
    - None: Success (refresh completed)
    - str: Technical exception class name or sentinel (e.g., "DiscoverFailed", "IntegrationNotFoundError")
    """

    integration_id: UUID
    integration_name: str
    integration_type: str
    result_status: IntegrationRefreshStatus | None = field(default=None)
    synced_count: int = field(default=0)
    updated_count: int = field(default=0)
    missing_count: int = field(default=0)
    error_type: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class IntegrationRefreshHandler(AuditEventHandler[IntegrationRefreshEvent]):
    """Maps an IntegrationRefreshEvent to a normalized AuditEvent."""

    def handle(self, event: IntegrationRefreshEvent) -> AuditEvent:
        """Map an IntegrationRefreshEvent to a normalized AuditEvent."""
        action = "integration_refreshed"
        is_error = event.error_type is not None

        if is_error:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.WARNING
            status = EventStatus.ERROR
            message = f"Integration refresh failed: {event.integration_name}"
            error_message: str | None = OPERATIONAL_LOGS_HINT
        else:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"Integration refresh successful: {event.integration_name}"
            error_message = None

        data = AuditContextData(
            data_type="integration-refresh-context",
            error_type=event.error_type,
            error_message=error_message,
            integration_name=event.integration_name,
            integration_type=event.integration_type,
            result_status=event.result_status.value if event.result_status else None,
            synced_count=event.synced_count,
            updated_count=event.updated_count,
            missing_count=event.missing_count,
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
