"""Telemetry handler for UserLoginEvent.

Emits Segment telemetry events on successful authentication:
- ``user_login`` on every login
- ``new_user`` additionally on the user's first login
"""

import hashlib
import hmac

import structlog

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent
from syntara.auth.audit.user_login import UserLoginEvent
from syntara.core.config.base import get_settings
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.new_user import NewUserEvent
from syntara.telemetry.events.user_login import UserLoginEvent as UserLoginTelemetryEvent

logger = structlog.stdlib.get_logger(__name__)


class UserLoginTelemetryHandler(AuditEventHandler[UserLoginEvent]):
    """Emits Segment telemetry events on user login."""

    def handle(self, event: UserLoginEvent) -> AuditEvent | None:
        """Emit telemetry (side-effect only, no AuditEvent produced)."""
        try:
            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return None

            user_id_hash = hmac.new(
                registry.installation_salt.encode(),
                str(event.user_id).encode(),
                hashlib.sha256,
            ).hexdigest()

            entitlement_id = registry.entitlement_id

            if get_settings().segment_high_volume_events_enabled:
                registry.send_event(
                    UserLoginTelemetryEvent(
                        user_id_hash=user_id_hash,
                        amr=event.amr,
                        idp=event.idp,
                        entitlement_id=entitlement_id,
                    )
                )
                logger.debug("Emitted user_login telemetry", amr=event.amr, idp=event.idp)

            if event.is_first_login:
                registry.send_event(
                    NewUserEvent(
                        user_id_hash=user_id_hash,
                        amr=event.amr,
                        idp=event.idp,
                        entitlement_id=entitlement_id,
                    )
                )
                logger.debug("Emitted new_user telemetry", amr=event.amr, idp=event.idp)
        except Exception:
            logger.exception("Failed to emit login telemetry (non-fatal)")

        return None
