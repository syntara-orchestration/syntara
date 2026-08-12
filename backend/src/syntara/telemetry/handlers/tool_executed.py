"""Telemetry handler for ToolExecutedEvent.

Emits a Segment ``tool_execution`` event when a tool execution
reaches a terminal state (success, error, timeout).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from syntara.audit.handler import AuditEventHandler
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.tool_execution import ToolExecutedEvent, ToolExecutionEvent

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent

logger = structlog.stdlib.get_logger(__name__)


class ToolExecutedTelemetryHandler(AuditEventHandler[ToolExecutedEvent]):
    """Emits a Segment ``tool_execution`` event (side-effect only)."""

    def handle(self, event: ToolExecutedEvent) -> AuditEvent | None:
        """Emit telemetry (side-effect only, no AuditEvent produced)."""
        try:
            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return None

            registry.send_event(
                ToolExecutionEvent(
                    namespaced_name=event.namespaced_name,
                    status=event.status,
                    duration_ms=event.duration_ms,
                    workflow_execution_id=event.execution_id,
                    entitlement_id=registry.entitlement_id,
                )
            )
            logger.debug(
                "Emitted tool_execution telemetry",
                namespaced_name=event.namespaced_name,
                status=event.status.value,
                duration_ms=event.duration_ms,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to emit tool_execution telemetry (non-fatal)", exc_info=True)

        return None
