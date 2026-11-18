"""Shared Execution Plane utilities."""

from uuid import UUID, uuid5

from syntara.workflow_core.models import NodeType


def execution_plane_work_item_id(execution_id: UUID, activity_id: str) -> UUID:
    """Build the stable work-item identity shared by dispatch and cancellation."""
    return uuid5(execution_id, activity_id)


def execution_plane_supported_node_types() -> frozenset[str]:
    """Return node types that can be dispatched to the Execution Plane."""
    return frozenset({NodeType.SCRIPT_PYTHON, NodeType.SCRIPT_BASH})
