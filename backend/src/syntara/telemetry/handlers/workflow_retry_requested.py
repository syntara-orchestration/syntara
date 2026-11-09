"""Telemetry handler for WorkflowRetryRequestedEvent.

Emits a Segment ``workflow_retry_requested`` event when a retry request
is accepted and the new retry execution is successfully persisted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from syntara.audit.handler import AuditEventHandler
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.workflow_execution import (
    WorkflowRetryRequestedEvent as TelemetryRetryRequestedEvent,
)
from syntara.workflows.audit.retry_requested import WorkflowRetryRequestedEvent as DomainRetryRequestedEvent

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent

logger = structlog.stdlib.get_logger(__name__)


class WorkflowRetryRequestedTelemetryHandler(AuditEventHandler[DomainRetryRequestedEvent]):
    """Emits a Segment telemetry event for accepted retry requests (side-effect only)."""

    def handle(self, event: DomainRetryRequestedEvent) -> AuditEvent | None:
        """Emit telemetry (side-effect only, no AuditEvent produced)."""
        try:
            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return None

            # Enforce 50-entry bound on failed_step_types before emission
            failed_step_types = event.failed_step_types[:50] if event.failed_step_types else []

            registry.send_event(
                TelemetryRetryRequestedEvent(
                    execution_id=event.execution_id,
                    source_execution_id=event.source_execution_id,
                    retry_kind=event.retry_kind,
                    node_count=event.node_count,
                    failed_step_types=failed_step_types,
                    entitlement_id=registry.entitlement_id,
                    request_id=event.request_id,
                )
            )
            logger.debug(
                "Emitted workflow_retry_requested telemetry",
                execution_id=str(event.execution_id),
                retry_kind=event.retry_kind,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to emit workflow_retry_requested telemetry (non-fatal)",
                exc_info=True,
            )

        return None
