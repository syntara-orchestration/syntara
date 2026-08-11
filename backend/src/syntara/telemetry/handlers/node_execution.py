"""Telemetry handler for NodeExecutedEvent.

Emits a Segment ``node_execution`` event when a workflow node
reaches a terminal execution state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from syntara.audit.handler import AuditEventHandler
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.node_execution import NodeExecutionEventBuilder
from syntara.workflows.audit.node_execution import NodeExecutedEvent

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent

logger = structlog.stdlib.get_logger(__name__)

_builder = NodeExecutionEventBuilder()


class NodeExecutedTelemetryHandler(AuditEventHandler[NodeExecutedEvent]):
    """Emits a Segment telemetry event (side-effect only)."""

    def handle(self, event: NodeExecutedEvent) -> AuditEvent | None:
        """Emit telemetry (side-effect only, no AuditEvent produced)."""
        try:
            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return None

            registry.send_event(
                _builder.build_event(
                    execution_id=str(event.execution_id),
                    node_type=event.node_type,
                    node_def=event.node_def,
                    status=event.status,
                    duration_ms=event.duration_ms,
                    error_type=event.error_type,
                    entitlement_id=registry.entitlement_id,
                    request_id=event.request_id,
                )
            )
            logger.debug(
                "Emitted node_execution telemetry",
                execution_id=str(event.execution_id),
                node_type=event.node_type,
                status=event.status,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to emit node_execution telemetry (non-fatal)", exc_info=True)

        return None
