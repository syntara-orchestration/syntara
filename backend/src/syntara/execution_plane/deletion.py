"""Require committed EP deletion intent before deleting the corresponding AO owner."""

from typing import Literal
from uuid import UUID

from execution_plane_client.commands.bulk_work import WorkItemSelector

from syntara.execution_plane.client import ExecutionPlaneError, ExecutionPlaneHttpClient
from syntara.execution_plane.exceptions import ExecutionPlaneDeletionError


async def delete_execution_plane_work_items(
    *, owner_field: Literal["project_id", "workflow_id", "execution_id"], owner_id: UUID
) -> None:
    """Block AO deletion unless EP acknowledges durable intent for all matching work.

    EP performs resource cleanup asynchronously. No matches is a successful no-op.
    An uncertain outcome (including a timeout after EP commits) fails AO deletion;
    retrying the same selector is safe.
    """
    try:
        async with ExecutionPlaneHttpClient() as client:
            await client.delete_work_items(selector=WorkItemSelector(runtime_context={owner_field: str(owner_id)}))
    except ExecutionPlaneError as exc:
        raise ExecutionPlaneDeletionError from exc
