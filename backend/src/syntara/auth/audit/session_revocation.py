"""Audit events and handlers for targeted session revocation."""

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
# Domain event
# ---------------------------------------------------------------------------


@dataclass
class SessionRevocationEvent:
    """Domain event emitted when an admin revokes sessions for a user or IdP."""

    actor_username: str
    actor_source: str  # "cli" (future-proofing for "api")
    target_type: str  # "user" or "idp"
    target_identifier: str  # username or IdP name
    sessions_revoked: int


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class SessionRevocationHandler(AuditEventHandler[SessionRevocationEvent]):
    """Maps a SessionRevocationEvent to a normalized AuditEvent."""

    def handle(self, event: SessionRevocationEvent) -> AuditEvent:
        """Map a SessionRevocationEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="session-revocation",
            target_type=event.target_type,
            target_identifier=event.target_identifier,
            sessions_revoked=event.sessions_revoked,
            actor_source=event.actor_source,
        )

        # Construct resource URN based on target type
        # URL-encode the identifier to comply with RFC 8141 (URNs cannot contain spaces or special characters)
        encoded_identifier = quote(event.target_identifier, safe="")

        if event.target_type == "user":
            resource_urn = f"urn:syntara:user:{encoded_identifier}"
        elif event.target_type == "idp":
            resource_urn = f"urn:syntara:identity_provider:{encoded_identifier}"
        else:
            # Fallback for unknown target types
            resource_urn = f"urn:syntara:{event.target_type}:{encoded_identifier}"

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.CRITICAL,
            event_status=EventStatus.SUCCESS,
            event_action="session_revocation",
            event_message=(
                f"Revoked {event.sessions_revoked} session(s) for "
                f"{event.target_type} '{event.target_identifier}' "
                f"by {event.actor_username} via {event.actor_source}"
            ),
            source_component="syntara.auth.revocation",
            structured_data=data,
            actor_type=PrincipalType.USER,
            actor_username=event.actor_username,
            resource_urn=resource_urn,
            resource_name=event.target_identifier,
        )
