"""Telemetry handler for FormPromptSubmittedEvent.

Emits a Segment ``form_prompt_submitted`` event when a form prompt
submission is made.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from syntara.audit.handler import AuditEventHandler
from syntara.forms.audit.form_prompt import FormPromptSubmittedEvent
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.form_prompt import FormPromptSubmittedEvent as FormPromptSubmittedTelemetryEvent

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent

logger = structlog.stdlib.get_logger(__name__)


class FormPromptSubmittedTelemetryHandler(AuditEventHandler[FormPromptSubmittedEvent]):
    """Emits a Segment telemetry event (side-effect only)."""

    def handle(self, event: FormPromptSubmittedEvent) -> AuditEvent | None:
        """Emit telemetry (side-effect only, no AuditEvent produced)."""
        try:
            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return None

            registry.send_event(
                FormPromptSubmittedTelemetryEvent(
                    workflow_execution_id=str(event.execution_id),
                    prompt_node_id=event.prompt_node_id,
                    wait_time_ms=event.wait_time_ms,
                    field_count=event.field_count,
                    outcome=event.outcome,
                    entitlement_id=registry.entitlement_id,
                )
            )
            logger.debug(
                "Emitted form_prompt_submitted telemetry",
                execution_id=str(event.execution_id),
                prompt_node_id=event.prompt_node_id,
                wait_time_ms=event.wait_time_ms,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to emit form_prompt_submitted telemetry (non-fatal)", exc_info=True)

        return None
