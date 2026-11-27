"""Shared Execution Plane utilities."""

from collections.abc import Mapping
from uuid import UUID, uuid5

from syntara.workflow_core.models import NodeType


def execution_plane_work_item_id(execution_id: UUID, activity_id: str) -> UUID:
    """Build the stable work-item identity shared by dispatch and cancellation."""
    return uuid5(execution_id, activity_id)


def runtime_context_activity_identity(
    work_item_id: UUID, runtime_context: Mapping[str, object] | None
) -> tuple[UUID, str] | None:
    """Return a callback's execution and Temporal activity identity when correlated."""
    if runtime_context is None:
        return None
    execution_id = runtime_context.get("execution_id")
    temporal_activity_id = runtime_context.get("temporal_activity_id")
    if not isinstance(execution_id, str) or not isinstance(temporal_activity_id, str):
        return None
    try:
        execution_uuid = UUID(execution_id)
    except ValueError:
        return None
    if work_item_id != execution_plane_work_item_id(execution_uuid, temporal_activity_id):
        return None
    return execution_uuid, temporal_activity_id


def execution_plane_supported_node_types() -> frozenset[str]:
    """Return node types that can be dispatched to the Execution Plane."""
    return frozenset({NodeType.SCRIPT_PYTHON, NodeType.SCRIPT_BASH})
