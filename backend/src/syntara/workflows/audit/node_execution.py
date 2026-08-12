"""NodeExecutedEvent domain event.

Fired when a workflow node reaches a terminal execution state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from uuid import UUID

    from syntara.workflows.workflow_engine.models.workflow_definition import (
        ActivityTerminalStatus,
        NodeType,
    )


@dataclass
class NodeExecutedEvent:
    """Domain event fired when a workflow node completes execution."""

    execution_id: UUID
    node_type: NodeType
    node_def: dict[str, Any]
    status: ActivityTerminalStatus
    duration_ms: int | None = None
    error_type: str | None = None
    request_id: UUID | None = field(default=None, repr=False)
