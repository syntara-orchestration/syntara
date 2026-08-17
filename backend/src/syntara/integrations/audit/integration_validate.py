"""IntegrationValidateEvent and handler for integration validation audit.

Validation in the integrations domain is a lightweight connectivity ping
(separate from tool sync via refresh). This event captures the outcome of
the health-check only.
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
from syntara.integrations.models.integration import IntegrationStatus

# ---------------------------------------------------------------------------
# Domain event
# ---------------------------------------------------------------------------


@dataclass
class IntegrationValidateEvent:
    """Domain event representing integration validation (lightweight connectivity ping).

    The error_type field can be:
    - None: Success (validation passed)
    - str: Technical exception class name or sentinel (e.g., "HealthCheckFailed", "TimeoutError")

    The error_message field contains the user-facing error message from the validation result.
    """

    integration_name: str
    integration_type: str
    integration_id: UUID | None = field(default=None)
    timeout: bool = field(default=False)
    result_status: IntegrationStatus | None = field(default=None)
    error_type: str | None = field(default=None)
    error_message: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class IntegrationValidateHandler(AuditEventHandler[IntegrationValidateEvent]):
    """Maps an IntegrationValidateEvent to a normalized AuditEvent."""

    def handle(self, event: IntegrationValidateEvent) -> AuditEvent:
        """Map an IntegrationValidateEvent to a normalized AuditEvent."""
        action = "integration_validated"
        is_error = event.error_type is not None

        if is_error:
            if event.timeout:
                category = EventCategory.SYSTEM_OPERATION
                severity = EventSeverity.WARNING
                status = EventStatus.ERROR
                message = f"Integration validation timeout: {event.integration_name}"
            else:
                category = EventCategory.SYSTEM_OPERATION
                severity = EventSeverity.WARNING
                status = EventStatus.ERROR
                message = f"Integration validation failed: {event.integration_name}"
            # Use the actual error message from the validation result instead of generic hint
            error_message: str | None = event.error_message or OPERATIONAL_LOGS_HINT
        else:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"Integration validation successful: {event.integration_name}"
            error_message = None

        data = AuditContextData(
            data_type="integration-validate-context",
            error_type=event.error_type,
            error_message=error_message,
            integration_name=event.integration_name,
            integration_type=event.integration_type,
            timeout=event.timeout,
            result_status=event.result_status.value if event.result_status else None,
        )

        return AuditEvent(
            event_category=category,
            event_severity=severity,
            event_status=status,
            event_action=action,
            event_message=message,
            source_component="syntara.integrations.integration",
            structured_data=data,
            resource_urn=f"urn:syntara:integration:{event.integration_id}" if event.integration_id else None,
            resource_name=event.integration_name,
        )
