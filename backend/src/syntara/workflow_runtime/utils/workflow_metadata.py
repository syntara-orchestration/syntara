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
    retry_from_execution_id: str | None = None,
    eligible_point_ids: list[str] | None = None,
    input_parameter_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the ``workflow_metadata`` dict consumed by ``DynamicWorkflow``.

    Returns the nested structure that the workflow engine unpacks in
    ``_init_state()`` to populate ``_project_id``, the expression
    resolver's ``workflow_context`` namespace, and audit fields.

    When retrying from failure (AAP-92820), a ``retry`` block carries the
    source execution id (``retry_from_execution_id``), the retry points that
    will actually run (``eligible_point_ids``), and any validated input
    parameter overrides keyed by starting node id (``input_parameter_overrides``,
    SDP AC-14/R10c). The engine (AAP-92821) uses them for node classification,
    output injection, and parameter application. The block is absent for
    normal runs and for plain ``/retry`` reruns, which share only
    ``retried_from_execution_id`` lineage.

    ``eligible_point_ids`` matches the preview response field of the same
    name. It is the post-validation set, not the caller's original selection:
    sanitized nodes may be auto-included and superseded failure points
    dropped, so it is not always a verbatim echo of the requested
    ``retry_point_ids``.
    """
    metadata: dict[str, Any] = {
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
    if retry_from_execution_id is not None:
        metadata["retry"] = {
            "retry_from_execution_id": retry_from_execution_id,
            "eligible_point_ids": list(eligible_point_ids or []),
            "input_parameter_overrides": dict(input_parameter_overrides or {}),
        }
    return metadata


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
