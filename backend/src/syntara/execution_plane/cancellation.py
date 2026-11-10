"""Best-effort cancellation of Execution Plane work owned by AO."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

import structlog
from sqlmodel import col, or_, select

from syntara.execution_plane.client import ExecutionPlaneHttpClient, ExecutionPlaneRejectedError
from syntara.execution_plane.utils import execution_plane_supported_node_types, execution_plane_work_item_id
from syntara.workflows.models.activity_execution import ActivityExecution

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)


async def cancel_execution_plane_work_items(
    execution_id: UUID,
    activity_ids: list[str],
) -> list[UUID]:
    """Cancel Execution Plane work for the supplied activity IDs.

    Each work item is cancelled independently. Unknown work items are treated as
    idempotent no-ops; a failure for one item does not prevent cancellation of
    the others. The returned list contains IDs for which cancellation succeeded.
    """
    work_item_ids = [execution_plane_work_item_id(execution_id, activity_id) for activity_id in activity_ids]
    return await _cancel_execution_plane_work_item_ids(execution_id, work_item_ids)


async def _cancel_execution_plane_work_item_ids(execution_id: UUID, work_item_ids: list[UUID]) -> list[UUID]:
    """Cancel Execution Plane work for the supplied work-item IDs."""
    if not work_item_ids:
        return []

    cancelled: list[UUID] = []
    async with ExecutionPlaneHttpClient() as client:
        for work_item_id in work_item_ids:
            try:
                await client.cancel_work_item(work_item_id=work_item_id)
            except ExecutionPlaneRejectedError as exc:
                if exc.status_code == HTTPStatus.NOT_FOUND:
                    logger.info(
                        "Execution Plane work item already absent",
                        execution_id=execution_id,
                        work_item_id=work_item_id,
                    )
                    continue
                logger.exception(
                    "Execution Plane rejected work cancellation",
                    execution_id=execution_id,
                    work_item_id=work_item_id,
                )
            except Exception:
                logger.exception(
                    "Execution Plane work cancellation failed",
                    execution_id=execution_id,
                    work_item_id=work_item_id,
                )
            else:
                cancelled.append(work_item_id)

    return cancelled


async def _execution_plane_work_item_ids(session: AsyncSession, execution_id: UUID) -> list[UUID]:
    """Return stable work-item IDs for EP-capable base activity records.

    Dispatch creates work items from the derived identity
    ``uuid5(execution_id, activity_id)``. Upfront activity creation seeds the
    matching base ``ActivityExecution.id`` with that value, so selecting the ORM
    ID directly avoids reconstructing the identity from activity names.

    Loop nodes complicate that mapping: each iteration gets its own database
    row and composite activity name, while EP work continues to use the base
    node identity. The base row can also be terminal while a later iteration is
    still active, so the base row is selected independently of status.

    Not every ``ActivityExecution`` uses the derived ID as its primary key.
    Comparing each base row's ID with the identity derived from its activity
    name therefore excludes unrelated activity records while preserving the
    direct ORM-to-work-item mapping used by dispatch.
    """
    supported_node_types = execution_plane_supported_node_types()
    if not supported_node_types:
        return []

    result = await session.exec(
        select(ActivityExecution.id, ActivityExecution.activity_name).where(
            ActivityExecution.execution_id == execution_id,
            col(ActivityExecution.node_type).in_(supported_node_types),
            or_(col(ActivityExecution.iteration).is_(None), col(ActivityExecution.iteration) == 0),
        )
    )
    return sorted(
        {
            work_item_id
            for work_item_id, activity_name in result.all()
            if work_item_id == execution_plane_work_item_id(execution_id, activity_name)
        }
    )


async def cancel_execution_plane_work_for_execution(
    session: AsyncSession,
    execution_id: UUID,
) -> list[UUID]:
    """Cancel all active Execution Plane work belonging to an execution."""
    work_item_ids = await _execution_plane_work_item_ids(session, execution_id)
    if not work_item_ids:
        logger.debug("No active Execution Plane work to cancel", execution_id=execution_id)
        return []

    logger.info(
        "Cancelling Execution Plane work for execution",
        execution_id=execution_id,
        count=len(work_item_ids),
    )
    return await _cancel_execution_plane_work_item_ids(execution_id, work_item_ids)
