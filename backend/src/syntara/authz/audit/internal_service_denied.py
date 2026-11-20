"""InternalServiceDeniedEvent and handler for authz-domain audit."""

from dataclasses import dataclass

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData


@dataclass
class InternalServiceDeniedEvent:
    """Domain event emitted when a non-service caller is rejected from an internal service endpoint."""

    reason: str
    path: str
    method: str
    cert_cn: str | None = None


class InternalServiceDeniedHandler(AuditEventHandler[InternalServiceDeniedEvent]):
    """Maps an InternalServiceDeniedEvent to a normalized AuditEvent."""

    def handle(self, event: InternalServiceDeniedEvent) -> AuditEvent:
        """Map an InternalServiceDeniedEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="internal-service-denied",
            reason=event.reason,
            path=event.path,
            method=event.method,
            cert_cn=event.cert_cn,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.ERROR,
            event_action="internal_service_denied",
            event_message=f"Rejected non-service caller on internal endpoint {event.method} {event.path} "
            f"({event.reason})",
            source_component="syntara.authz",
            structured_data=data,
        )
