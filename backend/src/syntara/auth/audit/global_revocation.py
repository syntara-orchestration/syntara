"""Audit events and handlers for global token revocation."""

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
from syntara.audit.utils import resolve_actor_type
from syntara.core.models.principal import PrincipalType

# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


@dataclass
class GlobalRevocationEvent:
    """Domain event emitted when an admin sets the global revocation timestamp."""

    actor_username: str
    actor_source: str  # "cli" (future-proofing for "api")
    revocation_timestamp: str  # ISO 8601


@dataclass
class GlobalRevocationRejectEvent:
    """Domain event emitted when a request is rejected due to global revocation."""

    user_id: UUID | None
    username: str | None
    token_issued_at: str  # ISO 8601
    revocation_timestamp: str  # ISO 8601
    token_type: str = field(default="access")  # "access" or "refresh"
    principal_type: PrincipalType | None = field(default=None)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


class GlobalRevocationHandler(AuditEventHandler[GlobalRevocationEvent]):
    """Maps a GlobalRevocationEvent to a normalized AuditEvent."""

    def handle(self, event: GlobalRevocationEvent) -> AuditEvent:
        """Map a GlobalRevocationEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="global-revocation",
            revocation_timestamp=event.revocation_timestamp,
            actor_source=event.actor_source,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.CRITICAL,
            event_status=EventStatus.SUCCESS,
            event_action="global_token_revocation",
            event_message=(
                f"Global token revocation set by {event.actor_username} "
                f"via {event.actor_source} at {event.revocation_timestamp}"
            ),
            source_component="syntara.auth.revocation",
            structured_data=data,
            actor_type=PrincipalType.USER,
            actor_username=event.actor_username,
        )


class GlobalRevocationRejectHandler(AuditEventHandler[GlobalRevocationRejectEvent]):
    """Maps a GlobalRevocationRejectEvent to a normalized AuditEvent."""

    def handle(self, event: GlobalRevocationRejectEvent) -> AuditEvent:
        """Map a GlobalRevocationRejectEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="global-revocation-reject",
            token_type=event.token_type,
            token_issued_at=event.token_issued_at,
            revocation_timestamp=event.revocation_timestamp,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.ERROR,
            event_action="globally_revoked_token_rejected",
            event_message=(
                f"Rejected {event.token_type} token for {event.username or 'unknown'}: "
                f"issued at {event.token_issued_at}, revoked at {event.revocation_timestamp}"
            ),
            source_component="syntara.auth.revocation",
            structured_data=data,
            actor_id=event.user_id,
            actor_type=resolve_actor_type(actor_id=event.user_id, principal_type=event.principal_type),
            actor_username=event.username,
        )
