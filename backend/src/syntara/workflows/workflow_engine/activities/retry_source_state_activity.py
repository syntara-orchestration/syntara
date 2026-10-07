"""Source-run state for retry-from-failure.

When an execution is retried from a failure point, the nodes upstream of that
point are skipped and the workflow needs their stored state so downstream nodes
read them as if those nodes had just run. This module reads that state from the
source execution.

One read serves both purposes. The caller passes the node ids it may restore —
already classified, because only the workflow knows the graph that actually ran —
and gets back each node's status alongside its stored input and output. Reading
the whole run instead would return payloads for nodes the retry is about to
re-execute, which is both wasteful and misleading: a node that is going to run
again must not be seeded with the previous run's row.
"""

from typing import Any

import structlog
from sqlmodel import col, select
from temporalio import activity, workflow

with workflow.unsafe.imports_passed_through():
    from syntara.core.database.session import get_db
    from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
    from syntara.workflows.utils.loop_iteration_names import strip_iteration_suffix

logger = structlog.stdlib.get_logger(__name__)


@activity.defn(name="fetch_retry_source_state")
async def fetch_retry_source_state_activity(
    source_execution_id: str,
    node_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return the source run's state for the nodes a retry may restore.

    Args:
        source_execution_id: Execution whose ``ActivityExecution`` rows are read.
        node_ids: Node ids the caller may restore, already classified. When given,
            only these are returned, and only if the source run completed them.

    Returns:
        Base node id to a record of ``status``, ``input_data``, ``output_data`` and
        the source timestamps. Ids are matched on the base node id, so a loop node
        resolves to its most recent completed iteration. Per-iteration granularity
        is classification's concern, not the transport's.

        A node absent from the mapping had no completed record in the source run,
        which is different from one whose output was empty: the first cannot be
        skipped, the second can.

    """
    wanted = {strip_iteration_suffix(node_id) for node_id in node_ids} if node_ids is not None else None

    states: dict[str, Any] = {}
    async for session in get_db():
        rows = (
            await session.exec(
                select(ActivityExecution)
                .where(
                    ActivityExecution.execution_id == source_execution_id,
                    ActivityExecution.status == ActivityStatus.COMPLETED,
                )
                .order_by(
                    col(ActivityExecution.iteration), col(ActivityExecution.created_at), col(ActivityExecution.id)
                )
            )
        ).all()
        for row in rows:
            if not row.activity_name:
                continue
            base_id = strip_iteration_suffix(row.activity_name)
            if wanted is not None and base_id not in wanted:
                continue
            states[base_id] = {
                "status": row.status.value,
                "input_data": row.input_data or {},
                "output_data": row.output_data or {},
                # The source row's own times, so a restored node reports when the
                # work ran rather than when this retry started.
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            }

    logger.info(
        "Read source node records for retry",
        source_execution_id=source_execution_id,
        requested_node_count=len(wanted) if wanted is not None else None,
        returned_node_count=len(states),
    )
    return states
