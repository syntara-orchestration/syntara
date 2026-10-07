"""Source-run state for retry-from-failure.

When an execution is retried from a failure point, the nodes upstream of that
point are skipped and the workflow needs their stored state so downstream nodes
read them as if those nodes had just run. This module reads that state from the
source execution: statuses for classification, and — only when asked — the
records themselves for the nodes that will be restored.

Statuses and records are separate reads on purpose. Classification only needs to
know which nodes ran, and it runs before anything is dispatched, so it stays a
narrow read with no payloads. The records are fetched later, and only when a node
actually needs restoring, so a retry whose rerunning steps read no upstream output
never fetches them at all.
"""

from typing import Any

import structlog
from sqlmodel import col, select
from temporalio import activity, workflow

with workflow.unsafe.imports_passed_through():
    from syntara.core.database.session import get_db
    from syntara.workflows.models.activity_execution import ActivityExecution
    from syntara.workflows.utils.loop_iteration_names import strip_iteration_suffix

logger = structlog.stdlib.get_logger(__name__)


@activity.defn(name="fetch_retry_source_state")
async def fetch_retry_source_state_activity(
    source_execution_id: str,
    include_records: bool = False,  # noqa: FBT002, FBT001 — activity arg, called by position
) -> dict[str, Any]:
    """Return the source run's state, optionally including restorable records.

    Args:
        source_execution_id: Execution whose ``ActivityExecution`` rows are read.
        include_records: When False, return only each base node's status, keyed by
            node id. When True, return the same mapping with the node's stored
            ``input_data`` and ``output_data`` alongside its status, so one call
            serves both classification and restoration.

    Returns:
        Base node id to status string, or — when ``include_records`` is set —
        base node id to a record of status, input and output. Ids are matched on
        the base node id, so a loop node resolves to its most recent completed
        iteration. Per-iteration granularity is classification's concern, not the
        transport's.

    """
    states: dict[str, Any] = {}
    async for session in get_db():
        rows = (
            await session.exec(
                select(ActivityExecution)
                .where(ActivityExecution.execution_id == source_execution_id)
                .order_by(
                    col(ActivityExecution.iteration), col(ActivityExecution.created_at), col(ActivityExecution.id)
                )
            )
        ).all()
        for row in rows:
            if not row.activity_name:
                continue
            base_id = strip_iteration_suffix(row.activity_name)
            status = row.status.value
            if not include_records:
                states[base_id] = status
                continue
            states[base_id] = {
                "status": status,
                "input_data": row.input_data or {},
                "output_data": row.output_data or {},
                # The source row's own timestamps, so a restored node reports when
                # the work ran rather than when it was replayed. The copied rows
                # already carry these; they travel here so the namespace entry and
                # the stored row agree.
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            }

    if include_records:
        logger.info(
            "Read source node records for retry",
            source_execution_id=source_execution_id,
            node_count=len(states),
        )
    return states
