"""DisabledUserRejectionEvent and handler for auth-domain audit."""

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar
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


class RejectionContext(StrEnum):
    """Where the disabled-user rejection originated."""

    MIDDLEWARE = "middleware"
    TOKEN_REFRESH = "token_refresh"  # noqa: S105


@dataclass
class DisabledUserRejectionEvent:
    """Domain event emitted when a disabled user's request is rejected."""

    user_id: str
    context: RejectionContext
    user_name: str | None = None


class DisabledUserRejectionHandler(AuditEventHandler[DisabledUserRejectionEvent]):
    """Maps a DisabledUserRejectionEvent to a normalized AuditEvent."""

    _SOURCE: ClassVar[dict[str, str]] = {
        "middleware": "syntara.auth.middleware",
        "token_refresh": "syntara.auth.token_refresh",
    }

    def handle(self, event: DisabledUserRejectionEvent) -> AuditEvent:
        """Map a DisabledUserRejectionEvent to a normalized AuditEvent."""
        try:
            actor_id: UUID | None = UUID(event.user_id)
        except ValueError:
            logger.warning("invalid_user_id_in_audit_event", user_id=event.user_id)
            actor_id = None

        data = AuditContextData(
            data_type="disabled-user-rejection",
            context=event.context,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.ERROR,
            event_action="disabled_user_rejected",
            event_message=f"Rejected request from disabled user ({event.context})",
            source_component=self._SOURCE.get(event.context, "syntara.auth"),
            structured_data=data,
            actor_id=actor_id,
            actor_type=PrincipalType.USER,
            resource_urn=f"urn:syntara:user:{quote(event.user_id, safe='')}",
            resource_name=event.user_name or event.user_id,
        )
