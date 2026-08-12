"""User account change events and handlers for auth-domain audit."""

from dataclasses import dataclass
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


class AccountStatus(StrEnum):
    """Whether a user account is enabled or disabled."""

    ENABLED = "enabled"
    DISABLED = "disabled"


# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


@dataclass
class UserPasswordChangedEvent:
    """Domain event emitted when a user's password is changed via the REST API."""

    actor_id: UUID
    actor_username: str
    target_user_id: UUID
    target_username: str


@dataclass
class UserAccountStatusChangedEvent:
    """Domain event emitted when a user account is enabled or disabled via the REST API."""

    actor_id: UUID
    actor_username: str
    target_user_id: UUID
    target_username: str
    new_status: AccountStatus


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


class UserPasswordChangedHandler(AuditEventHandler[UserPasswordChangedEvent]):
    """Maps a UserPasswordChangedEvent to a normalized AuditEvent."""

    def handle(self, event: UserPasswordChangedEvent) -> AuditEvent:
        """Map a UserPasswordChangedEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="password-changed",
            target_user_id=str(event.target_user_id),
            target_username=event.target_username,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.SUCCESS,
            event_action="password_changed",
            event_message=f"Password changed for user '{event.target_username}'",
            source_component="syntara.auth.account_management",
            structured_data=data,
            actor_id=event.actor_id,
            actor_type=PrincipalType.USER,
            actor_username=event.actor_username,
            resource_urn=f"urn:syntara:user:{quote(event.target_username, safe='')}",
            resource_name=event.target_username,
        )


class UserAccountStatusChangedHandler(AuditEventHandler[UserAccountStatusChangedEvent]):
    """Maps a UserAccountStatusChangedEvent to a normalized AuditEvent."""

    def handle(self, event: UserAccountStatusChangedEvent) -> AuditEvent:
        """Map a UserAccountStatusChangedEvent to a normalized AuditEvent."""
        action = f"account_{event.new_status}"

        data = AuditContextData(
            data_type="account-status-changed",
            target_user_id=str(event.target_user_id),
            target_username=event.target_username,
            new_status=event.new_status,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.SUCCESS,
            event_action=action,
            event_message=f"Account {event.new_status}: '{event.target_username}'",
            source_component="syntara.auth.account_management",
            structured_data=data,
            actor_id=event.actor_id,
            actor_type=PrincipalType.USER,
            actor_username=event.actor_username,
            resource_urn=f"urn:syntara:user:{quote(event.target_username, safe='')}",
            resource_name=event.target_username,
        )
