"""Audit events and handlers for account management operations."""

from dataclasses import dataclass
from urllib.parse import quote

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
# Domain events
# ---------------------------------------------------------------------------


@dataclass
class AccountEnableEvent:
    """Domain event emitted when an admin re-enables a disabled user account via CLI."""

    actor_username: str
    actor_source: str
    target_username: str
    sessions_revoked: int


@dataclass
class PasswordResetEvent:
    """Domain event emitted when an admin resets a user's password via CLI."""

    actor_username: str
    actor_source: str
    target_username: str
    sessions_revoked: int


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


class AccountEnableHandler(AuditEventHandler[AccountEnableEvent]):
    """Maps an AccountEnableEvent to a normalized AuditEvent."""

    def handle(self, event: AccountEnableEvent) -> AuditEvent:
        """Map an AccountEnableEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="account-enable",
            target_username=event.target_username,
            sessions_revoked=event.sessions_revoked,
            actor_source=event.actor_source,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.SUCCESS,
            event_action="account_enable",
            event_message=(
                f"Re-enabled account '{event.target_username}' by {event.actor_username} via {event.actor_source}"
            ),
            source_component="syntara.auth.account_management",
            structured_data=data,
            actor_type=PrincipalType.USER,
            actor_username=event.actor_username,
            resource_urn=f"urn:syntara:user:{quote(event.target_username, safe='')}",
            resource_name=event.target_username,
        )


class PasswordResetHandler(AuditEventHandler[PasswordResetEvent]):
    """Maps a PasswordResetEvent to a normalized AuditEvent."""

    def handle(self, event: PasswordResetEvent) -> AuditEvent:
        """Map a PasswordResetEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="password-reset",
            target_username=event.target_username,
            sessions_revoked=event.sessions_revoked,
            actor_source=event.actor_source,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.CRITICAL,
            event_status=EventStatus.SUCCESS,
            event_action="password_reset",
            event_message=(
                f"Reset password for '{event.target_username}' by {event.actor_username} via {event.actor_source}"
            ),
            source_component="syntara.auth.account_management",
            structured_data=data,
            actor_type=PrincipalType.USER,
            actor_username=event.actor_username,
            resource_urn=f"urn:syntara:user:{quote(event.target_username, safe='')}",
            resource_name=event.target_username,
        )
