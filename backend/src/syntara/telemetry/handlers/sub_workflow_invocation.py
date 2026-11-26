"""Segment telemetry handler for completed sub-workflow invocations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from syntara.audit.handler import AuditEventHandler
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.sub_workflow_invocation import (
    SubWorkflowInvocationEvent,
    SubWorkflowInvocationMode,
)
from syntara.workflows.audit.sub_workflow_invocation import SubWorkflowInvocationCompletedEvent

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent

logger = structlog.stdlib.get_logger(__name__)


class SubWorkflowInvocationTelemetryHandler(AuditEventHandler[SubWorkflowInvocationCompletedEvent]):
    """Send completed Reference-mode invocations to Segment as a side effect."""

    def handle(self, event: SubWorkflowInvocationCompletedEvent) -> AuditEvent | None:
        """Emit invocation identifiers, outcome, and duration samples without payloads."""
        try:
            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return None

            registry.send_event(
                SubWorkflowInvocationEvent(
                    parent_execution_id=event.parent_execution_id,
                    parent_workflow_id=event.parent_workflow_id,
                    parent_workflow_name=event.parent_workflow_name,
                    parent_node_id=event.parent_node_id,
                    child_execution_id=event.child_execution_id,
                    child_workflow_id=event.child_workflow_id,
                    child_workflow_name=event.child_workflow_name,
                    invocation_mode=SubWorkflowInvocationMode.REFERENCE,
                    status=event.status,
                    invocation_duration_ms=event.invocation_duration_ms,
                    child_execution_duration_ms=event.child_execution_duration_ms,
                    installation_anon_id=registry.anonymous_id,
                    occurred_at=event.occurred_at,
                    entitlement_id=registry.entitlement_id,
                    request_id=event.request_id,
                )
            )
            logger.debug(
                "Emitted sub_workflow_invocation telemetry",
                parent_execution_id=str(event.parent_execution_id),
                child_execution_id=str(event.child_execution_id),
                status=event.status.value,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to emit sub_workflow_invocation telemetry (non-fatal)", exc_info=True)

        return None
