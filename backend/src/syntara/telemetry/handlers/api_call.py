"""Telemetry handler for HTTPRequestEvent.

Emits a Segment ``api_call`` analytics event for every HTTP request
that passes through the audit middleware, reusing the audit dispatcher
instead of a separate ASGI middleware.

Also feeds the :class:`~syntara.telemetry.api_usage_accumulator.APIUsageAccumulator`
with per-request caller and endpoint data for periodic unique-caller
and feature-usage aggregation.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import TYPE_CHECKING, Any, cast

import structlog

from syntara.audit.events.http_request import HTTPRequestEvent
from syntara.audit.handler import AuditEventHandler
from syntara.core.config.base import get_settings
from syntara.telemetry.api_usage_accumulator import get_accumulator
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.api_call import APICallEvent

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent

logger = structlog.stdlib.get_logger(__name__)


class APICallTelemetryHandler(AuditEventHandler[HTTPRequestEvent]):
    """Emits a Segment ``api_call`` event for each HTTP request."""

    def handle(self, event: HTTPRequestEvent) -> AuditEvent | None:
        """Emit telemetry and record usage metrics (side-effect only)."""
        self._record_usage(event)
        self._emit_api_call_event(event)
        return None

    @staticmethod
    def _emit_api_call_event(event: HTTPRequestEvent) -> None:
        """Send the per-request Segment api_call event (high-volume, gated)."""
        try:
            if not get_settings().segment_high_volume_events_enabled:
                return

            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return

            registry.send_event(
                APICallEvent(
                    endpoint=event.path,
                    http_method=cast("Any", event.method),
                    status_code=event.status_code,
                    response_time_ms=event.response_time_ms,
                    request_payload_size=event.request_payload_size,
                    entitlement_id=registry.entitlement_id,
                )
            )
            logger.debug(
                "analytics_event_sent",
                endpoint=event.path,
                http_method=event.method,
                status_code=event.status_code,
                response_time_ms=event.response_time_ms,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "analytics_event_failed",
                endpoint=event.path,
                http_method=event.method,
                exc_info=True,
            )

    @staticmethod
    def _record_usage(event: HTTPRequestEvent) -> None:
        """Feed the in-memory accumulator for periodic unique-caller/feature-usage aggregation."""
        try:
            actor_id = event.actor_context.actor_id
            if actor_id is None:
                return

            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return

            actor_id_hash = hmac.new(
                registry.installation_salt.encode(),
                str(actor_id).encode(),
                hashlib.sha256,
            ).hexdigest()

            principal_type = (
                event.actor_context.actor_type.value if event.actor_context.actor_type is not None else "unknown"
            )
            endpoint = event.endpoint_template
            if endpoint is None:
                return

            get_accumulator().record(
                actor_id_hash=actor_id_hash,
                principal_type=principal_type,
                endpoint_template=endpoint,
                http_method=event.method,
                interface=event.interface,
            )
        except Exception:  # noqa: BLE001
            logger.debug("api_usage_record_failed", exc_info=True)
