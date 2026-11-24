"""Domain event emitted when a referenced sub-workflow invocation completes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from syntara.workflows.workflow_engine.models.workflow_definition import WorkflowTerminalStatus


@dataclass(frozen=True)
class SubWorkflowInvocationCompletedEvent:
    """Telemetry context for one completed Reference-mode invocation."""

    parent_execution_id: UUID
    parent_workflow_id: UUID
    parent_workflow_name: str
    parent_node_id: str
    child_execution_id: UUID
    child_workflow_id: UUID
    child_workflow_name: str
    status: WorkflowTerminalStatus
    invocation_duration_ms: int | None
    child_execution_duration_ms: int | None
    occurred_at: datetime
    request_id: UUID | None = None
