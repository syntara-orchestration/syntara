"""Activity stalled — domain event and audit handler.

Fired by the stall detection PeriodicWorker when a running activity exceeds
its expected duration. Each stall is detected exactly once via the
``stall_alert_at`` deduplication marker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType  # noqa: TC001

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID


@dataclass
class NodeStalledEvent:
    """Domain event fired when an activity is detected as stalled."""

    activity_execution_id: UUID
    execution_id: UUID
    activity_name: str
    node_type: NodeType
    expected_duration: int  # seconds
    started_at: datetime
    stall_alert_at: datetime


class NodeStalledHandler(AuditEventHandler[NodeStalledEvent]):
    """Maps a NodeStalledEvent to an AuditEvent."""

    def handle(self, event: NodeStalledEvent) -> AuditEvent:
        """Map a NodeStalledEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="activity-stalled",
            activity_name=event.activity_name,
            node_type=event.node_type.value,
            expected_duration=event.expected_duration,
            started_at=event.started_at.isoformat(),
            stall_alert_at=event.stall_alert_at.isoformat(),
        )

        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.SUCCESS,
            event_action="activity_stalled",
            event_message=(
                f"Activity '{event.activity_name}' stalled (exceeded expected duration of {event.expected_duration}s)"
            ),
            source_component="syntara.workflows.workers.stall_detection",
            structured_data=data,
            execution_id=event.execution_id,
            resource_urn=f"urn:syntara:activity:{event.activity_execution_id}",
            resource_name=event.activity_name,
        )
