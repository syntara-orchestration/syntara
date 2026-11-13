"""Best-effort EP cleanup following explicit AO project or workflow deletion."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog
from sqlmodel import col, or_, select

from syntara.execution_plane.client import ExecutionPlaneHttpClient
from syntara.execution_plane.utils import execution_plane_work_item_id
from syntara.workflows.models.activity_execution import ActivityExecution
from syntara.workflows.models.execution import Execution

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)
_pending_deletions: set[asyncio.Task[None]] = set()


async def collect_execution_plane_work_items(
    session: AsyncSession, *, project_id: UUID | None = None, workflow_id: UUID | None = None
) -> list[UUID]:
    """Capture work identities before the owner's execution/activity cascade.

    Include historical node types even if their EP image is no longer configured.
    Derived IDs for native activities are harmless: EP accepts absent-ID deletion.
    """
    if (project_id is None) == (workflow_id is None):
        msg = "Exactly one project or workflow deletion scope is required"
        raise ValueError(msg)
    scope = Execution.project_id == project_id if project_id is not None else Execution.workflow_id == workflow_id
    rows = await session.exec(
        select(ActivityExecution.id, ActivityExecution.execution_id, ActivityExecution.activity_name)
        .join(Execution, col(Execution.id) == col(ActivityExecution.execution_id))
        .where(
            scope,
            or_(col(ActivityExecution.iteration).is_(None), col(ActivityExecution.iteration) == 0),
        )
    )
    return sorted(
        {
            item_id
            for item_id, execution_id, activity_name in rows.all()
            if item_id == execution_plane_work_item_id(execution_id, activity_name)
        }
    )


async def delete_execution_plane_work_items(work_item_ids: list[UUID]) -> None:
    """Send independent deletion requests after AO has committed its cascade."""
    if not work_item_ids:
        return
    async with ExecutionPlaneHttpClient() as client:
        for item_id in work_item_ids:
            try:
                await client.delete_work_item(work_item_id=item_id)
            except Exception:
                # Broader execution cleanup in Syntara is planned separately.
                # Until then, failed EP cleanup is logged without undoing AO deletion.
                logger.exception("Execution Plane work-item deletion failed", work_item_id=item_id)


def _deletion_finished(task: asyncio.Task[None]) -> None:
    """Release the task reference and observe setup failures."""
    _pending_deletions.discard(task)
    if task.cancelled():
        logger.warning("Execution Plane deletion task was interrupted")
    elif (error := task.exception()) is not None:
        logger.error("Execution Plane deletion task failed", error_type=type(error).__name__)


def schedule_work_item_deletion(work_item_ids: list[UUID]) -> None:
    """Start cleanup only after the owning deletion transaction has committed."""
    if not work_item_ids:
        return
    task = asyncio.create_task(delete_execution_plane_work_items(work_item_ids), name="ep-work-item-deletion")
    _pending_deletions.add(task)
    task.add_done_callback(_deletion_finished)
