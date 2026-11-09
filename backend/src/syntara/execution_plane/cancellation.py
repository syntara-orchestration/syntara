"""Best-effort cancellation of Execution Plane work owned by AO."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

import structlog
from sqlmodel import col, select

from syntara.execution_plane.client import ExecutionPlaneHttpClient, ExecutionPlaneRejectedError
from syntara.execution_plane.utils import execution_plane_supported_node_types, execution_plane_work_item_id
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)

_ACTIVE_ACTIVITY_STATUSES = (
    ActivityStatus.PENDING,
    ActivityStatus.RUNNING,
    ActivityStatus.WAITING,
    ActivityStatus.RETRYING,
)
_ITERATION_RECORD_SEPARATOR = "#iter-"


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


async def _active_execution_plane_activity_ids(session: AsyncSession, execution_id: UUID) -> list[str]:
    """Return base activity IDs for non-terminal Execution Plane activities."""
    supported_node_types = execution_plane_supported_node_types()
    if not supported_node_types:
        return []

    result = await session.exec(
        select(ActivityExecution.activity_name).where(
            ActivityExecution.execution_id == execution_id,
            col(ActivityExecution.node_type).in_(supported_node_types),
            col(ActivityExecution.status).in_(_ACTIVE_ACTIVITY_STATUSES),
        )
    )
    activity_ids = {row.split(_ITERATION_RECORD_SEPARATOR, 1)[0] for row in result.all()}
    return sorted(activity_ids)


async def cancel_execution_plane_work_for_execution(
    session: AsyncSession,
    execution_id: UUID,
) -> list[UUID]:
    """Cancel all active Execution Plane work belonging to an execution."""
    activity_ids = await _active_execution_plane_activity_ids(session, execution_id)
    if not activity_ids:
        logger.debug("No active Execution Plane work to cancel", execution_id=execution_id)
        return []

    logger.info(
        "Cancelling Execution Plane work for execution",
        execution_id=execution_id,
        count=len(activity_ids),
    )
    return await cancel_execution_plane_work_items(execution_id, activity_ids)
