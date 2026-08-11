"""UserLoginEvent and UserLoginHandler for auth-domain audit.

Emits an audit event (for the audit trail) on every successful user
login. Telemetry emission is handled separately by the telemetry
handler in ``syntara.telemetry.handlers``.

Requirement: AAP-72352
"""

from dataclasses import dataclass, field
from enum import StrEnum
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
from syntara.core.models.principal import PrincipalType


class AMR(StrEnum):
    """Authentication method reference values (RFC 8176)."""

    PASSWORD = "pwd"  # noqa: S105
    FEDERATED = "fed"


@dataclass
class UserLoginEvent:
    """Domain event representing a successful user login.

    Dispatched after a successful DB commit so that telemetry is only
    emitted for logins that actually persisted.
    """

    user_id: UUID
    username: str | None = None
    amr: list[AMR] = field(default_factory=list)
    idp: str = "local"
    is_first_login: bool = False


class UserLoginHandler(AuditEventHandler[UserLoginEvent]):
    """Maps a UserLoginEvent to an AuditEvent."""

    def handle(self, event: UserLoginEvent) -> AuditEvent:
        """Map a UserLoginEvent to a normalized AuditEvent."""
        action = "new_user_login" if event.is_first_login else "user_login"
        message = f"First login via {event.idp}" if event.is_first_login else f"User logged in via {event.idp}"

        data = AuditContextData(
            data_type="user-login-context",
            amr=event.amr,
            idp=event.idp,
            is_first_login=event.is_first_login,
        )

        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action=action,
            event_message=message,
            source_component="syntara.auth.login",
            structured_data=data,
            actor_id=event.user_id,
            actor_type=PrincipalType.USER,
            actor_username=event.username,
            resource_urn=f"urn:syntara:user:{quote(event.username, safe='')}" if event.username else None,
            resource_name=event.username,
        )
