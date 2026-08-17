"""Telemetry handler for WorkflowExecutionErrorEvent.

Emits a Segment ``workflow_error`` event when an engine-level
workflow or activity timeout/retry occurs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from syntara.audit.handler import AuditEventHandler
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.workflow_error import WorkflowErrorEvent
from syntara.workflows.audit.execution_error import WorkflowExecutionErrorEvent

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent

logger = structlog.stdlib.get_logger(__name__)


class WorkflowExecutionErrorTelemetryHandler(AuditEventHandler[WorkflowExecutionErrorEvent]):
    """Emits a Segment telemetry event (side-effect only)."""

    def handle(self, event: WorkflowExecutionErrorEvent) -> AuditEvent | None:
        """Emit telemetry (side-effect only, no AuditEvent produced)."""
        try:
            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return None

            registry.send_event(
                WorkflowErrorEvent(
                    workflow_execution_id=str(event.execution_id),
                    timed_out_component=event.timed_out_component,
                    configured_timeout_seconds=event.configured_timeout_seconds,
                    elapsed_time_ms=event.elapsed_time_ms,
                    activity_id=event.activity_id,
                    entitlement_id=registry.entitlement_id,
                    request_id=event.request_id,
                    retry_count=event.retry_count,
                    error_type=event.error_type,
                    retry_reason=event.retry_reason,
                )
            )
            logger.debug(
                "Emitted workflow_error telemetry",
                execution_id=str(event.execution_id),
                timed_out_component=str(event.timed_out_component),
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to emit workflow_error telemetry (non-fatal)", exc_info=True)

        return None
