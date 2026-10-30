"""Telemetry handler for form-trigger submissions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from syntara.audit.handler import AuditEventHandler
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.form_trigger import FormTriggerSubmittedEvent as FormTriggerSubmittedTelemetryEvent
from syntara.workflows.audit.form_trigger import FormTriggerSubmittedEvent

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent

logger = structlog.stdlib.get_logger(__name__)


class FormTriggerSubmittedTelemetryHandler(AuditEventHandler[FormTriggerSubmittedEvent]):
    """Emit a Segment telemetry event as a side effect only."""

    def handle(self, event: FormTriggerSubmittedEvent) -> AuditEvent | None:
        """Emit bounded form metadata and never produce an audit record."""
        try:
            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return None

            registry.send_event(
                FormTriggerSubmittedTelemetryEvent(
                    workflow_execution_id=str(event.execution_id),
                    trigger_node_id=event.trigger_node_id,
                    field_count=event.field_count,
                    field_types=event.field_types,
                    entitlement_id=registry.entitlement_id,
                )
            )
            logger.debug(
                "Emitted form_trigger_submitted telemetry",
                execution_id=str(event.execution_id),
                trigger_node_id=event.trigger_node_id,
                field_count=event.field_count,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to emit form_trigger_submitted telemetry (non-fatal)", exc_info=True)

        return None
