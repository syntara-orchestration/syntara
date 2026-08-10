"""Telemetry handler for WorkflowStartEvent.

Emits a Segment ``workflow_execution_start`` event when a workflow
execution begins.

Requirement: AAP-74302
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from syntara.audit.handler import AuditEventHandler
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.workflow_execution import WorkflowExecutionStartEvent
from syntara.workflows.audit.execution_started import WorkflowStartEvent

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent

logger = structlog.stdlib.get_logger(__name__)


class WorkflowStartTelemetryHandler(AuditEventHandler[WorkflowStartEvent]):
    """Emits a Segment telemetry event (side-effect only)."""

    def handle(self, event: WorkflowStartEvent) -> AuditEvent | None:
        """Emit telemetry (side-effect only, no AuditEvent produced)."""
        try:
            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return None

            registry.send_event(
                WorkflowExecutionStartEvent(
                    workflow_execution_id=str(event.execution_id),
                    trigger_type=event.trigger_type,
                    interface=event.interface,
                    entitlement_id=registry.entitlement_id,
                    request_id=event.request_id,
                )
            )
            logger.debug(
                "Emitted workflow_execution_start telemetry",
                execution_id=str(event.execution_id),
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to emit workflow_execution_start telemetry (non-fatal)",
                exc_info=True,
            )

        return None
