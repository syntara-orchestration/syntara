"""Telemetry handler for WorkflowVersionRestoredEvent.

Emits a Segment ``workflow_version_restored`` event when a workflow
version is restored from a previous version.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from syntara.audit.handler import AuditEventHandler
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.workflow_version import (
    WorkflowVersionRestoredEvent as WorkflowVersionRestoredTelemetryEvent,
)
from syntara.workflows.audit.workflow_version import WorkflowVersionRestoredEvent

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent

logger = structlog.stdlib.get_logger(__name__)


class WorkflowVersionRestoredTelemetryHandler(AuditEventHandler[WorkflowVersionRestoredEvent]):
    """Emits a Segment telemetry event (side-effect only)."""

    def handle(self, event: WorkflowVersionRestoredEvent) -> AuditEvent | None:
        """Emit telemetry (side-effect only, no AuditEvent produced)."""
        try:
            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return None

            registry.send_event(
                WorkflowVersionRestoredTelemetryEvent(
                    workflow_id=str(event.workflow_id),
                    restored_from_version=event.restored_from_version,
                    new_version=event.new_version,
                    entitlement_id=registry.entitlement_id,
                )
            )
            logger.debug(
                "Emitted workflow_version_restored telemetry",
                workflow_id=str(event.workflow_id),
                restored_from_version=event.restored_from_version,
                new_version=event.new_version,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to emit workflow_version_restored telemetry (non-fatal)", exc_info=True)

        return None
