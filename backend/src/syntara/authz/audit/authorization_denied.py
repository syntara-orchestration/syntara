"""AuthorizationDeniedEvent and handler for authz-domain audit."""

from dataclasses import dataclass, field
from urllib.parse import quote
from uuid import UUID

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData
from syntara.audit.utils import resolve_actor_type
from syntara.core.models.principal import PrincipalType


@dataclass
class AuthorizationDeniedEvent:
    """Domain event emitted when a principal is denied access to a resource."""

    user_id: UUID
    username: str
    resource_id: str
    resource_type: str
    resource_name: str
    action: str
    denied_by: str | None = field(default=None)
    principal_type: PrincipalType | None = field(default=None)


class AuthorizationDeniedHandler(AuditEventHandler[AuthorizationDeniedEvent]):
    """Maps an AuthorizationDeniedEvent to a normalized AuditEvent."""

    def handle(self, event: AuthorizationDeniedEvent) -> AuditEvent:
        """Map an AuthorizationDeniedEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="authorization-denied",
            resource_type=event.resource_type,
            action=event.action,
            denied_by=event.denied_by,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.ERROR,
            event_action="authorization_denied",
            event_message=f"Authorization denied: {event.action} on {event.resource_type}",
            source_component="syntara.authz",
            structured_data=data,
            actor_id=event.user_id,
            actor_type=resolve_actor_type(actor_id=event.user_id, principal_type=event.principal_type),
            actor_username=event.username,
            resource_urn=f"urn:syntara:{quote(event.resource_type, safe='')}:{quote(event.resource_id, safe='')}",
            resource_name=event.resource_name,
        )
