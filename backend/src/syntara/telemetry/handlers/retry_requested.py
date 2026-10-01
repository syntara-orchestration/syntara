"""Anonymized retry-from-failure telemetry."""

from syntara.audit.handler import AuditEventHandler
from syntara.telemetry.client import get_telemetry_registry
from syntara.telemetry.events.workflow_execution import WorkflowRetryRequestedEvent
from syntara.workflows.audit.retry_requested import RetryRequestedEvent


class RetryRequestedTelemetryHandler(AuditEventHandler[RetryRequestedEvent]):
    """The dispatcher isolates telemetry failures from retry execution."""

    def handle(self, event: RetryRequestedEvent) -> None:
        """Handle the retry event without including inputs or outputs."""
        registry = get_telemetry_registry()
        if registry.is_initialized():
            registry.send_event(
                WorkflowRetryRequestedEvent(
                    entitlement_id=registry.entitlement_id,
                    node_count=event.node_count,
                    failed_step_types=event.failed_step_types,
                )
            )
