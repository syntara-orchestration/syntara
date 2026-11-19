"""Best-effort EP cleanup following explicit AO project or workflow deletion."""

from __future__ import annotations

import asyncio
from typing import Literal
from uuid import UUID

import structlog

from syntara.execution_plane.client import ExecutionPlaneHttpClient

logger = structlog.stdlib.get_logger(__name__)
_pending_deletions: set[asyncio.Task[None]] = set()
_PAGE_SIZE = 100


async def delete_execution_plane_work_items(
    *, owner_field: Literal["project_id", "workflow_id"], owner_id: UUID
) -> None:
    """Page through the deleted owner's EP work and request cleanup after AO commits."""
    cursor: str | None = None
    async with ExecutionPlaneHttpClient() as client:
        while True:
            page = await client.list_work_items(
                limit=_PAGE_SIZE,
                cursor=cursor,
                sort="id",
                filters={f"runtime_context[{owner_field}]": str(owner_id)},
            )
            for item in page["resources"]:
                item_id = UUID(item["id"])
                try:
                    await client.delete_work_item(work_item_id=item_id)
                except Exception:
                    # Broader execution cleanup in Syntara is planned separately.
                    # Until then, failed EP cleanup is logged without undoing AO deletion.
                    logger.exception("Execution Plane work-item deletion failed", work_item_id=item_id)
            next_cursor = page.get("next")
            if next_cursor is None:
                return
            if next_cursor == cursor:
                msg = "Execution Plane returned a repeated work-item cursor"
                raise ValueError(msg)
            cursor = next_cursor


def _deletion_finished(task: asyncio.Task[None]) -> None:
    """Release the task reference and observe background cleanup failures."""
    _pending_deletions.discard(task)
    if task.cancelled():
        logger.warning("Execution Plane deletion task was interrupted")
    elif (error := task.exception()) is not None:
        logger.error("Execution Plane deletion task failed", error_type=type(error).__name__)


def schedule_work_item_deletion(*, owner_field: Literal["project_id", "workflow_id"], owner_id: UUID) -> None:
    """Start EP lookup and cleanup after the owner's deletion transaction commits."""
    task = asyncio.create_task(
        delete_execution_plane_work_items(owner_field=owner_field, owner_id=owner_id), name="ep-work-item-deletion"
    )
    _pending_deletions.add(task)
    task.add_done_callback(_deletion_finished)
