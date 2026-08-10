"""Telemetry handler for WorkflowCompletedEvent.

Emits a Segment ``workflow_execution_completed`` event when a workflow
execution reaches a terminal state.

Requirement: AAP-74303
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from syntara.audit.handler import AuditEventHandler
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.workflow_execution import WorkflowExecutionCompletedEvent
from syntara.workflows.audit.execution_completed import WorkflowCompletedEvent

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent

logger = structlog.stdlib.get_logger(__name__)


class WorkflowCompletedTelemetryHandler(AuditEventHandler[WorkflowCompletedEvent]):
    """Emits a Segment telemetry event (side-effect only)."""

    def handle(self, event: WorkflowCompletedEvent) -> AuditEvent | None:
        """Emit telemetry (side-effect only, no AuditEvent produced)."""
        try:
            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return None

            registry.send_event(
                WorkflowExecutionCompletedEvent(
                    workflow_execution_id=str(event.execution_id),
                    status=event.status,
                    duration_ms=event.duration_ms,
                    node_count=event.node_count,
                    error_count=event.error_count,
                    error_type=event.error_type,
                    trigger_type=event.trigger_type,
                    interface=event.interface,
                    entitlement_id=registry.entitlement_id,
                    request_id=event.request_id,
                )
            )
            logger.debug(
                "Emitted workflow_execution_completed telemetry",
                execution_id=str(event.execution_id),
                status=event.status.value,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to emit workflow_execution_completed telemetry (non-fatal)",
                exc_info=True,
            )

        return None
