"""Shared Execution Plane utilities."""

from uuid import UUID, uuid5

from syntara.core.config.base import get_settings


def execution_plane_work_item_id(execution_id: UUID, activity_id: str) -> UUID:
    """Build the stable work-item identity shared by dispatch and cancellation."""
    return uuid5(execution_id, activity_id)


def execution_plane_container_image(node_type: str) -> str | None:
    """Return the configured Execution Plane image for a node type."""
    return get_settings().node_container_images.get(node_type) or None


def execution_plane_supported_node_types() -> frozenset[str]:
    """Return node types that can be dispatched to the Execution Plane."""
    return frozenset(node_type for node_type, image in get_settings().node_container_images.items() if image)
