"""OIDCFlowEvent and OIDCFlowHandler for OIDC flow audit."""

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

# ---------------------------------------------------------------------------
# Helper types
# ---------------------------------------------------------------------------


class OIDCStage(StrEnum):
    """Stage of the OIDC flow being audited."""

    AUTHORIZE = "authorize"
    CALLBACK = "callback"


# ---------------------------------------------------------------------------
# Domain event
# ---------------------------------------------------------------------------


@dataclass
class OIDCFlowEvent:
    """Domain event representing a step or completion in an OIDC flow."""

    provider_id: UUID | None
    stage: OIDCStage
    user_id: UUID | None = None
    username: str | None = None
    error_type: str | None = None


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class OIDCFlowHandler(AuditEventHandler[OIDCFlowEvent]):
    """Maps an OIDCFlowEvent to a normalized AuditEvent."""

    def handle(self, event: OIDCFlowEvent) -> AuditEvent:
        """Map an OIDCFlowEvent to a normalized AuditEvent."""
        provider_id_str = str(event.provider_id) if event.provider_id is not None else None
        actor_type = PrincipalType.USER if event.user_id else PrincipalType.SYSTEM
        action = f"oidc_{event.stage}"

        is_error = event.error_type is not None

        if is_error:
            category = EventCategory.SECURITY_EVENT
            status = EventStatus.ERROR
            severity = EventSeverity.ERROR
            message = f"OIDC {event.stage} failed"
            error_message: str | None = "Look at the Operational Logs for full diagnosis"
        else:
            category = EventCategory.USER_ACTION
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"OIDC {event.stage} completed"
            error_message = None

        data = AuditContextData(
            data_type="oidc-context",
            error_type=event.error_type,
            error_message=error_message,
            provider_id=provider_id_str,
            stage=event.stage.value,
        )

        # Determine resource identifier with cascading fallback
        # 1. Prefer username if available
        # 2. Fall back to user_id if username is None
        # 3. If both are None, leave resource fields as None
        resource_identifier: str | None = None
        if event.username is not None:
            resource_identifier = event.username
        elif event.user_id is not None:
            resource_identifier = str(event.user_id)

        resource_urn = f"urn:syntara:user:{quote(resource_identifier, safe='')}" if resource_identifier else None

        return AuditEvent(
            event_category=category,
            event_severity=severity,
            event_status=status,
            event_action=action,
            event_message=message,
            source_component="syntara.auth.oidc",
            structured_data=data,
            actor_id=event.user_id,
            actor_type=actor_type,
            actor_username=event.username,
            resource_urn=resource_urn,
            resource_name=resource_identifier,
        )
