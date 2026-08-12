"""Telemetry handler for WorkflowVersionUnpublishedEvent.

Emits a Segment ``workflow_version_unpublished`` event when a workflow
is unpublished.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from syntara.audit.handler import AuditEventHandler
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.workflow_version import (
    WorkflowVersionUnpublishedEvent as WorkflowVersionUnpublishedTelemetryEvent,
)
from syntara.workflows.audit.workflow_version import WorkflowVersionUnpublishedEvent

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent

logger = structlog.stdlib.get_logger(__name__)


class WorkflowVersionUnpublishedTelemetryHandler(AuditEventHandler[WorkflowVersionUnpublishedEvent]):
    """Emits a Segment telemetry event (side-effect only)."""

    def handle(self, event: WorkflowVersionUnpublishedEvent) -> AuditEvent | None:
        """Emit telemetry (side-effect only, no AuditEvent produced)."""
        try:
            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return None

            registry.send_event(
                WorkflowVersionUnpublishedTelemetryEvent(
                    workflow_id=str(event.workflow_id),
                    version=event.version,
                    workflow_name=event.workflow_name,
                    project_id=str(event.project_id) if event.project_id else None,
                    error_type=event.error_type,
                    entitlement_id=registry.entitlement_id,
                )
            )
            logger.debug(
                "Emitted workflow_version_unpublished telemetry",
                workflow_id=str(event.workflow_id),
                version=event.version,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to emit workflow_version_unpublished telemetry (non-fatal)",
                workflow_id=str(event.workflow_id),
                version=event.version,
                exc_info=True,
            )

        return None
