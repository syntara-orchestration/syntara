"""Telemetry handler for WorkflowVersionCreatedEvent.

Emits a Segment ``workflow_version_created`` event when a new workflow
version is created (initial or subsequent).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from syntara.audit.handler import AuditEventHandler
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.workflow_version import (
    WorkflowVersionCreatedEvent as WorkflowVersionCreatedTelemetryEvent,
)
from syntara.workflows.audit.workflow_version import WorkflowVersionCreatedEvent

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent

logger = structlog.stdlib.get_logger(__name__)


class WorkflowVersionCreatedTelemetryHandler(AuditEventHandler[WorkflowVersionCreatedEvent]):
    """Emits a Segment telemetry event (side-effect only)."""

    def handle(self, event: WorkflowVersionCreatedEvent) -> AuditEvent | None:
        """Emit telemetry (side-effect only, no AuditEvent produced)."""
        try:
            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return None

            registry.send_event(
                WorkflowVersionCreatedTelemetryEvent(
                    workflow_id=str(event.workflow_id),
                    version=event.version,
                    entitlement_id=registry.entitlement_id,
                )
            )
            logger.debug(
                "Emitted workflow_version_created telemetry",
                workflow_id=str(event.workflow_id),
                version=event.version,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to emit workflow_version_created telemetry (non-fatal)", exc_info=True)

        return None
