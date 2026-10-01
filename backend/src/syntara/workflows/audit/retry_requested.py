"""Audit event for a successfully dispatched retry-from-failure request."""

from dataclasses import dataclass
from uuid import UUID

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData


@dataclass
class RetryRequestedEvent:
    """Retry provenance for audit; telemetry excludes identifying fields."""

    execution_id: UUID
    source_execution_id: UUID
    workflow_id: UUID
    triggered_by: UUID
    selected_point_ids: list[str]
    node_count: int
    failed_step_types: list[str]


class RetryRequestedHandler(AuditEventHandler[RetryRequestedEvent]):
    """Record the selected retry points and source run with the triggering user."""

    def handle(self, event: RetryRequestedEvent) -> AuditEvent:
        """Handle the retry event without including inputs or outputs."""
        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="execution_retry_requested",
            event_message="Workflow retry from failure requested",
            source_component="syntara.workflows",
            workflow_id=event.workflow_id,
            execution_id=event.execution_id,
            structured_data=AuditContextData(
                data_type="execution-retry",
                source_execution_id=str(event.source_execution_id),
                triggered_by=str(event.triggered_by),
                selected_point_ids=event.selected_point_ids,
                first_failed_node_id=event.selected_point_ids[0] if event.selected_point_ids else None,
                execution_mode="retry",
                node_count=event.node_count,
            ),
        )
