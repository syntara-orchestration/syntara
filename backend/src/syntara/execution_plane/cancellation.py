"""Best-effort bulk cancellation of Execution Plane work owned by AO."""

from uuid import UUID

import structlog
from execution_plane_client.commands.bulk_work import WorkItemSelector

from syntara.execution_plane.client import ExecutionPlaneHttpClient
from syntara.execution_plane.utils import execution_plane_work_item_id

logger = structlog.stdlib.get_logger(__name__)
_BATCH_SIZE = 100


async def cancel_execution_plane_work_items(execution_id: UUID, activity_ids: list[str]) -> list[UUID]:
    """Request cancellation in bounded batches, returning IDs whose intent was acknowledged.

    Failure of a batch does not prevent subsequent batches. Acknowledgment does
    not mean Kubernetes cleanup has finished, and absent IDs are successful no-ops.
    """
    ids = [execution_plane_work_item_id(execution_id, activity_id) for activity_id in activity_ids]
    if not ids:
        return []
    accepted: list[UUID] = []
    async with ExecutionPlaneHttpClient() as client:
        for start in range(0, len(ids), _BATCH_SIZE):
            batch = ids[start : start + _BATCH_SIZE]
            try:
                await client.cancel_work_items(selector=WorkItemSelector(work_item_ids=batch))
            except Exception:
                logger.exception("Execution Plane bulk cancellation failed", execution_id=execution_id)
            else:
                accepted.extend(batch)
    return accepted


async def cancel_execution_plane_work_for_execution(execution_id: UUID) -> None:
    """Record cancellation intent for all EP work belonging to this execution."""
    async with ExecutionPlaneHttpClient() as client:
        await client.cancel_work_items(selector=WorkItemSelector(runtime_context={"execution_id": str(execution_id)}))
