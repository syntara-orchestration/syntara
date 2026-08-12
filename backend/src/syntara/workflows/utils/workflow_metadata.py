"""Builder for the workflow_metadata dict passed to Temporal workflows.

Centralizes the structure so every execution path (manual, test, scheduled)
produces an identical shape.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from sqlmodel import select

from syntara.core.models import User

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)


def build_workflow_metadata(
    *,
    workflow_name: str,
    workflow_id: UUID,
    workflow_version: int,
    workflow_published: bool,
    workflow_author: str,
    project_id: UUID,
    execution_id: str,
    execution_mode: str,
    created_by: str,
    created_by_user_id: str,
    created_at: str,
    workflow_version_id: UUID,
) -> dict[str, Any]:
    """Build the ``workflow_metadata`` dict consumed by ``DynamicWorkflow``.

    Returns the nested structure that the workflow engine unpacks in
    ``_init_state()`` to populate ``_project_id``, the expression
    resolver's ``workflow_context`` namespace, and audit fields.
    """
    return {
        "workflow_context": {
            "workflow": {
                "name": workflow_name,
                "id": str(workflow_id),
                "version": workflow_version,
                "published": workflow_published,
                "author": workflow_author,
                "project_id": str(project_id),
            },
            "execution": {
                "id": execution_id,
                "mode": execution_mode,
                "created_by": created_by,
                "created_by_user_id": created_by_user_id,
                "created_at": created_at,
                "workflow_version_id": str(workflow_version_id),
            },
        },
    }


async def resolve_user_display_name(session: AsyncSession, user_id: UUID) -> str:
    """Resolve a user ID to a display name, falling back to UUID string."""
    try:
        result = await session.exec(select(User).where(User.id == user_id))
        user = result.first()
        if user and hasattr(user, "display_name"):
            return user.display_name
    except Exception:  # noqa: BLE001
        logger.debug("Could not resolve user display name", user_id=str(user_id))
    return str(user_id)
