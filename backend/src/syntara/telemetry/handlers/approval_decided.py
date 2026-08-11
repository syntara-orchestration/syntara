"""Telemetry handler for ApprovalDecidedEvent.

Emits a Segment ``approval_decided`` event when a HitL approval
decision (approve/reject) is made.

Requirement: AAP-72359
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from syntara.approvals.audit.approval import ApprovalDecidedEvent
from syntara.audit.handler import AuditEventHandler
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.approval import ApprovalDecidedEvent as ApprovalDecidedTelemetryEvent

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent

logger = structlog.stdlib.get_logger(__name__)


class ApprovalDecidedTelemetryHandler(AuditEventHandler[ApprovalDecidedEvent]):
    """Emits a Segment telemetry event (side-effect only)."""

    def handle(self, event: ApprovalDecidedEvent) -> AuditEvent | None:
        """Emit telemetry (side-effect only, no AuditEvent produced)."""
        try:
            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return None

            registry.send_event(
                ApprovalDecidedTelemetryEvent(
                    workflow_execution_id=str(event.execution_id),
                    decision=event.decision,
                    wait_time_ms=event.wait_time_ms,
                    entitlement_id=registry.entitlement_id,
                )
            )
            logger.debug(
                "Emitted approval_decided telemetry",
                execution_id=str(event.execution_id),
                decision=event.decision,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to emit approval_decided telemetry (non-fatal)", exc_info=True)

        return None
