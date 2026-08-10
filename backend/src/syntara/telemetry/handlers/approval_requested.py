"""Telemetry handler for ApprovalRequestedEvent.

Emits a Segment ``approval_requested`` event when a HitL approval
request is created during a workflow execution.

Requirement: AAP-72358
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from syntara.approvals.audit.approval import ApprovalRequestedEvent
from syntara.audit.handler import AuditEventHandler
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.approval import ApprovalRequestedEvent as ApprovalRequestedTelemetryEvent

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent

logger = structlog.stdlib.get_logger(__name__)


class ApprovalRequestedTelemetryHandler(AuditEventHandler[ApprovalRequestedEvent]):
    """Emits a Segment telemetry event (side-effect only)."""

    def handle(self, event: ApprovalRequestedEvent) -> AuditEvent | None:
        """Emit telemetry (side-effect only, no AuditEvent produced)."""
        try:
            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return None

            registry.send_event(
                ApprovalRequestedTelemetryEvent(
                    workflow_execution_id=str(event.execution_id),
                    approval_node_id=event.approval_node_id,
                    entitlement_id=registry.entitlement_id,
                )
            )
            logger.debug(
                "Emitted approval_requested telemetry",
                execution_id=str(event.execution_id),
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to emit approval_requested telemetry (non-fatal)", exc_info=True)

        return None
