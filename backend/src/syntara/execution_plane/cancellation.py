"""Best-effort cancellation of Execution Plane work owned by AO."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Protocol, Self
from uuid import UUID, uuid5

import structlog
from sqlmodel import col, select

from syntara.execution_plane.client import ExecutionPlaneHttpClient, ExecutionPlaneRejectedError
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)

_ACTIVE_ACTIVITY_STATUSES = (
    ActivityStatus.PENDING,
    ActivityStatus.RUNNING,
    ActivityStatus.WAITING,
    ActivityStatus.RETRYING,
)
_ITERATION_RECORD_SEPARATOR = "#iter-"


class WorkItemCancellationClient(Protocol):
    """Client operations required to cancel Execution Plane work."""

    async def __aenter__(self) -> Self:
        """Return the client."""

    async def __aexit__(self, *_: object) -> bool | None:
        """Close the client."""

    async def cancel_work_item(self, *, work_item_id: UUID) -> object:
        """Request cancellation for one work item."""


def execution_plane_work_item_id(execution_id: UUID, activity_id: str) -> UUID:
    """Build the stable work-item identity shared by dispatch and cancellation."""
    return uuid5(execution_id, activity_id)


async def cancel_execution_plane_work_items(
    execution_id: UUID,
    activity_ids: list[str],
    *,
    client_factory: Callable[[], WorkItemCancellationClient] = ExecutionPlaneHttpClient,
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
    async with client_factory() as client:
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


async def active_execution_plane_activity_ids(session: AsyncSession, execution_id: UUID) -> list[str]:
    """Return base activity IDs for non-terminal script activities."""
    result = await session.exec(
        select(ActivityExecution.activity_name).where(
            ActivityExecution.execution_id == execution_id,
            ActivityExecution.node_type == NodeType.SCRIPT,
            col(ActivityExecution.status).in_(_ACTIVE_ACTIVITY_STATUSES),
        )
    )
    activity_ids = {row.split(_ITERATION_RECORD_SEPARATOR, 1)[0] for row in result.all()}
    return sorted(activity_ids)


async def cancel_execution_plane_work_for_execution(
    session: AsyncSession,
    execution_id: UUID,
    *,
    client_factory: Callable[[], WorkItemCancellationClient] = ExecutionPlaneHttpClient,
) -> list[UUID]:
    """Cancel all active Execution Plane work belonging to an execution."""
    activity_ids = await active_execution_plane_activity_ids(session, execution_id)
    if not activity_ids:
        logger.debug("No active Execution Plane work to cancel", execution_id=execution_id)
        return []

    logger.info(
        "Cancelling Execution Plane work for execution",
        execution_id=execution_id,
        count=len(activity_ids),
    )
    return await cancel_execution_plane_work_items(
        execution_id,
        activity_ids,
        client_factory=client_factory,
    )
