"""Telemetry handler for WorkflowVersionExportedEvent.

Emits a Segment ``workflow_version_exported`` event when a workflow
version is exported.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from syntara.audit.handler import AuditEventHandler
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.workflow_version import (
    WorkflowVersionExportedEvent as WorkflowVersionExportedTelemetryEvent,
)
from syntara.workflows.audit.workflow_version import WorkflowVersionExportedEvent

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent

logger = structlog.stdlib.get_logger(__name__)


class WorkflowVersionExportedTelemetryHandler(AuditEventHandler[WorkflowVersionExportedEvent]):
    """Emits a Segment telemetry event (side-effect only)."""

    def handle(self, event: WorkflowVersionExportedEvent) -> AuditEvent | None:
        """Emit telemetry (side-effect only, no AuditEvent produced)."""
        try:
            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return None

            registry.send_event(
                WorkflowVersionExportedTelemetryEvent(
                    workflow_id=str(event.workflow_id),
                    version=event.version,
                    workflow_name=event.workflow_name,
                    entitlement_id=registry.entitlement_id,
                )
            )
            logger.debug(
                "Emitted workflow_version_exported telemetry",
                workflow_id=str(event.workflow_id),
                version=event.version,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to emit workflow_version_exported telemetry (non-fatal)",
                workflow_id=str(event.workflow_id),
                version=event.version,
                exc_info=True,
            )

        return None
