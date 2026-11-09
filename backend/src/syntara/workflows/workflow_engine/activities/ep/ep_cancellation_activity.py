"""Cancel Execution Plane work from a workflow cleanup path."""

from __future__ import annotations

from uuid import UUID

import structlog
from temporalio import activity

from syntara.execution_plane.cancellation import cancel_execution_plane_work_items
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

logger = structlog.stdlib.get_logger(__name__)

__all__ = ["cancel_execution_plane_work_activity"]


@activity.defn(name=ActivityName.CANCEL_EXECUTION_PLANE)
async def cancel_execution_plane_work_activity(
    execution_id: str,
    activity_ids: list[str],
    reason: str = "Workflow activity cancelled",
) -> dict[str, int | str]:
    """Best-effort cancel Execution Plane work for workflow activity IDs."""
    execution_uuid = UUID(execution_id)
    cancelled_ids = await cancel_execution_plane_work_items(execution_uuid, activity_ids)
    logger.info(
        "Execution Plane work cancellation complete",
        execution_id=execution_id,
        attempted_count=len(activity_ids),
        cancelled_count=len(cancelled_ids),
        reason=reason,
    )
    return {
        "attempted_count": len(activity_ids),
        "cancelled_count": len(cancelled_ids),
        "reason": reason,
    }
