"""Reconcile cancellation using existing AO execution state and EP work items."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlmodel import col, or_, select

from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.workers.periodic import PeriodicWorker
from syntara.execution_plane.client import ExecutionPlaneHttpClient
from syntara.execution_plane.utils import execution_plane_work_item_id
from syntara.workflows.models.activity_execution import ActivityExecution
from syntara.workflows.models.execution import Execution, ExecutionStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)
_CANCELLABLE_STATUSES = "pending,claimed,dispatched,running"
_PAGE_SIZE = 100


async def reconcile_work_item_cancellations(session: AsyncSession, client: ExecutionPlaneHttpClient) -> int:
    """Retry cancellation for live EP work whose AO execution is cancelled.

    No retry records are needed: each pass compares the existing models again.
    Missing AO activity rows are ignored, including rows the monitor has not
    created yet. This function does not delete orphaned work or schedule itself.
    """
    cursor: str | None = None
    accepted = 0
    while True:
        page = await client.list_work_items(
            limit=_PAGE_SIZE, cursor=cursor, sort="id", filters={"status": _CANCELLABLE_STATUSES}
        )
        item_ids = [UUID(item["id"]) for item in page["resources"]]
        if item_ids:
            rows = await session.exec(
                select(ActivityExecution.id, ActivityExecution.execution_id, ActivityExecution.activity_name)
                .join(Execution, col(Execution.id) == col(ActivityExecution.execution_id))
                .where(
                    col(ActivityExecution.id).in_(item_ids),
                    Execution.status == ExecutionStatus.CANCELLED,
                    or_(col(ActivityExecution.iteration).is_(None), col(ActivityExecution.iteration) == 0),
                )
            )
            for item_id, execution_id, activity_name in rows.all():
                if item_id != execution_plane_work_item_id(execution_id, activity_name):
                    continue
                try:
                    await client.cancel_work_item(work_item_id=item_id)
                except Exception:
                    logger.exception(
                        "Execution Plane cancellation reconciliation failed; a later pass can retry",
                        execution_id=execution_id,
                        work_item_id=item_id,
                    )
                else:
                    accepted += 1
        next_cursor = page.get("next")
        if next_cursor is None:
            return accepted
        if next_cursor == cursor:
            msg = "Execution Plane returned a repeated work-item cursor"
            raise ValueError(msg)
        cursor = next_cursor


async def _reconcile_cancellations(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Open resources for one coordinated reconciliation pass."""
    async with session_factory() as session, ExecutionPlaneHttpClient() as client:
        accepted = await reconcile_work_item_cancellations(session, client)
    logger.info("Execution Plane cancellation reconciliation completed", accepted=accepted)


def get_cancellation_reconciliation_worker() -> PeriodicWorker:
    """Retry from existing execution state, coordinating replicas with an advisory lock."""
    return PeriodicWorker(
        name="execution-plane-cancellation-reconciliation",
        interval_seconds=get_settings().ep_cancellation_reconciliation_interval_seconds,
        session_factory=AsyncSessionLocal,
        callback=_reconcile_cancellations,
    )
