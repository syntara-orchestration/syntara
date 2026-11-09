"""Shared Execution Plane utilities."""

from uuid import UUID, uuid5


def execution_plane_work_item_id(execution_id: UUID, activity_id: str) -> UUID:
    """Build the stable work-item identity shared by dispatch and cancellation."""
    return uuid5(execution_id, activity_id)
