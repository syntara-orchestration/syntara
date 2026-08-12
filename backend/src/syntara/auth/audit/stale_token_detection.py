"""StaleTokenDetectionEvent and handler for auth-domain audit."""

from dataclasses import dataclass
from urllib.parse import quote
from uuid import UUID

import structlog

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData
from syntara.core.models.principal import PrincipalType

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class StaleTokenDetectionEvent:
    """Domain event emitted when a stale access token is detected."""

    user_id: str
    token_version: int
    current_version: int
    user_name: str | None = None


class StaleTokenDetectionHandler(AuditEventHandler[StaleTokenDetectionEvent]):
    """Maps a StaleTokenDetectionEvent to a normalized AuditEvent."""

    def handle(self, event: StaleTokenDetectionEvent) -> AuditEvent:
        """Map a StaleTokenDetectionEvent to a normalized AuditEvent."""
        try:
            actor_id: UUID | None = UUID(event.user_id)
        except ValueError:
            logger.warning("invalid_user_id_in_audit_event", user_id=event.user_id)
            actor_id = None

        data = AuditContextData(
            data_type="stale-token-detection",
            token_version=event.token_version,
            current_version=event.current_version,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="stale_token_detected",
            event_message="Stale access token detected",
            source_component="syntara.auth.middleware",
            structured_data=data,
            actor_id=actor_id,
            actor_type=PrincipalType.USER,
            resource_urn=f"urn:syntara:user:{quote(event.user_id, safe='')}",
            resource_name=event.user_name or event.user_id,
        )
