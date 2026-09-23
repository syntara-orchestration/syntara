"""Node execute denial — domain event and audit handler (ANSTRAT-1750, AD-15).

Fired once per node that the workflow engine refused to run because a deny
policy withheld ``workflow_node:execute`` from the run principal.  The engine
cannot reach the database, so the event is dispatched from an activity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData

if TYPE_CHECKING:
    from uuid import UUID

NODE_EXECUTE_DENIED_EVENT_ACTION = "workflow.node_execute_denied"
"""Stable audit ``event_action`` for a node skipped by an execute denial."""


@dataclass
class NodeExecuteDeniedEvent:
    """Domain event fired when a node is not executed because of a deny policy."""

    execution_id: UUID
    node_id: str
    kind: str
    labels: dict[str, str]
    denied_by: str
    principal_id: UUID | None = field(default=None)
    workflow_id: UUID | None = field(default=None)


class NodeExecuteDeniedHandler(AuditEventHandler[NodeExecuteDeniedEvent]):
    """Maps a NodeExecuteDeniedEvent to an AuditEvent."""

    def handle(self, event: NodeExecuteDeniedEvent) -> AuditEvent:
        """Map a NodeExecuteDeniedEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="node-execute-denied",
            node_id=event.node_id,
            node_kind=event.kind,
            node_labels=event.labels,
            denied_by=event.denied_by,
            principal_id=str(event.principal_id) if event.principal_id else None,
        )
        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.ERROR,
            event_action=NODE_EXECUTE_DENIED_EVENT_ACTION,
            event_message=(
                f"Node '{event.node_id}' of kind '{event.kind}' was not executed: "
                f"execute denied by policy '{event.denied_by}'"
            ),
            source_component="syntara.workflows",
            structured_data=data,
            actor_id=event.principal_id,
            workflow_id=event.workflow_id,
            execution_id=event.execution_id,
            activity_id=event.node_id,
        )
