"""SessionLifecycleEvent and SessionLifecycleHandler for auth-domain audit."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import ClassVar
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

# ---------------------------------------------------------------------------
# Helper types
# ---------------------------------------------------------------------------


class SessionAction(StrEnum):
    """Session lifecycle action being audited."""

    CREATE = "create"
    REVOKE = "revoke"
    REFRESH = "refresh"


# ---------------------------------------------------------------------------
# Domain event
# ---------------------------------------------------------------------------


@dataclass
class SessionLifecycleEvent:
    """Domain event representing a session lifecycle action."""

    action: SessionAction
    user_id: UUID
    username: str | None = field(default=None)
    jti: str | None = field(default=None)
    idp: str | None = field(default=None)
    error_type: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class SessionLifecycleHandler(AuditEventHandler[SessionLifecycleEvent]):
    """Maps a SessionLifecycleEvent to a normalized AuditEvent."""

    _ACTION_NAMES: ClassVar[dict[SessionAction, str]] = {
        SessionAction.CREATE: "session_created",
        SessionAction.REVOKE: "session_revoked",
        SessionAction.REFRESH: "session_refreshed",
    }

    def handle(self, event: SessionLifecycleEvent) -> AuditEvent:
        """Map a SessionLifecycleEvent to a normalized AuditEvent."""
        action = SessionLifecycleHandler._ACTION_NAMES[event.action]
        is_error = event.error_type is not None

        if is_error:
            category = EventCategory.SECURITY_EVENT
            severity = EventSeverity.ERROR
            status = EventStatus.ERROR
            message = f"Session {event.action} failed"
            error_message: str | None = "Look at the Operational Logs for full diagnosis"
        else:
            category = EventCategory.USER_ACTION
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"Session {event.action}"
            error_message = None

        data = AuditContextData(
            data_type="session-lifecycle-context",
            error_type=event.error_type,
            error_message=error_message,
            jti=event.jti,
            idp=event.idp,
            lifecycle_action=event.action.value,
        )

        # Use username if available, otherwise fall back to user_id
        resource_identifier = event.username if event.username is not None else str(event.user_id)

        return AuditEvent(
            event_category=category,
            event_severity=severity,
            event_status=status,
            event_action=action,
            event_message=message,
            source_component="syntara.auth.session",
            structured_data=data,
            actor_id=event.user_id,
            actor_type=PrincipalType.USER,
            actor_username=event.username,
            resource_urn=f"urn:syntara:user:{quote(resource_identifier, safe='')}",
            resource_name=resource_identifier,
        )
