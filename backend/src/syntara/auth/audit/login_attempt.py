"""LoginAttemptEvent and LoginAttemptHandler for auth-domain audit."""

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
from syntara.audit.utils import resolve_actor_type
from syntara.core.models.principal import PrincipalType


class LoginMethod(StrEnum):
    """Authentication method used for a login attempt."""

    PASSWORD = "password"  # noqa: S105
    OIDC = "oidc"
    CLIENT_CREDENTIALS = "client_credentials"


class LoginErrorReason(StrEnum):
    """Classified error reason for an unsuccessful login attempt."""

    UNKNOWN_USER = "unknown_user"
    BAD_PASSWORD = "bad_password"  # noqa: S105
    INACTIVE_ACCOUNT = "inactive_account"
    LOCAL_LOGIN_DISABLED = "local_login_disabled"
    SESSION_STORE_UNAVAILABLE = "session_store_unavailable"
    DISABLED_SERVICE_ACCOUNT = "disabled_service_account"
    DELETED_SERVICE_ACCOUNT = "deleted_service_account"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Domain event
# ---------------------------------------------------------------------------


@dataclass
class LoginAttemptEvent:
    """Domain event representing a single login attempt.

    The error_type field can be:
    - None: Success (no error)
    - LoginErrorReason: Business/classified error (e.g., BAD_PASSWORD, UNKNOWN_USER)
    - str: Technical exception class name (e.g., "SQLAlchemyError")
    """

    username: str | None
    method: LoginMethod
    user_id: UUID | None = field(default=None)
    error_type: str | LoginErrorReason | None = field(default=None)
    principal_type: PrincipalType | None = field(default=None)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class LoginAttemptHandler(AuditEventHandler[LoginAttemptEvent]):
    """Maps a LoginAttemptEvent to a normalized AuditEvent."""

    def handle(self, event: LoginAttemptEvent) -> AuditEvent:
        """Map a LoginAttemptEvent to a normalized AuditEvent."""
        action = "login"
        actor_type = (
            resolve_actor_type(actor_id=event.user_id, principal_type=event.principal_type)
            if event.user_id or event.principal_type
            else PrincipalType.SYSTEM
        )

        is_error = event.error_type is not None

        if is_error:
            if isinstance(event.error_type, LoginErrorReason):
                # Business/classified error
                category = EventCategory.SECURITY_EVENT
                severity = EventSeverity.WARNING
                status = EventStatus.ERROR
                message = f"Login attempt failed ({event.error_type.value})"
                error_message: str | None = message
                error_type_str = None
            else:
                # Technical exception
                category = EventCategory.SECURITY_EVENT
                severity = EventSeverity.ERROR
                status = EventStatus.ERROR
                message = "Login failed due to system error"
                error_message = "Look at the Operational Logs for full diagnosis"
                error_type_str = event.error_type
        else:
            # Success
            category = EventCategory.USER_ACTION
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"User logged in via {event.method}"
            error_message = None
            error_type_str = None

        data = AuditContextData(
            data_type="login-context",
            error_type=error_type_str,
            error_message=error_message,
            method=event.method.value,
        )

        return AuditEvent(
            event_category=category,
            event_severity=severity,
            event_status=status,
            event_action=action,
            event_message=message,
            source_component="syntara.auth.login",
            structured_data=data,
            actor_id=event.user_id,
            actor_type=actor_type,
            actor_username=event.username,
            resource_urn=f"urn:syntara:user:{quote(event.username, safe='')}" if event.username else None,
            resource_name=event.username,
        )
