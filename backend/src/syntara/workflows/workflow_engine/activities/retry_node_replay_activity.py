"""Source-node replay activity for retry-from-failure.

When an execution is retried from a failure point, the nodes upstream of that
point are skipped and the workflow needs their stored state injected so
downstream nodes read them as if those nodes had just run. This activity returns
the whole node state that was recorded — its input, its output, and the times it
ran — for exactly one node.

One node per call, rather than a batch, keeps each activity result small: Temporal
records activity results in history, so restoring them through an activity does
not remove that history cost. Namespace publication uses the ordinary completion
path, which is what makes a replayed node indistinguishable from an executed one.
"""

import json
from typing import Any

import structlog
from sqlmodel import col, select
from temporalio import activity, workflow

with workflow.unsafe.imports_passed_through():
    from syntara.core.constants import JsonbLimits
    from syntara.core.database.session import get_db
    from syntara.core.exceptions import SafeValueError
    from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
    from syntara.workflows.utils.loop_iteration_names import strip_iteration_suffix

logger = structlog.stdlib.get_logger(__name__)

#: Source statuses a retry can restore.
#:
#: Excludes the in-flight ones — PENDING, RUNNING, WAITING — because the source run
#: reached a terminal state, so those rows are work that never finished.
#:
#: CANCELLED is excluded too, though it is terminal. Cancellation only rewrites
#: *unfinished* rows: a node that had already completed keeps its real status and
#: output, and only in-flight ones are marked CANCELLED, with a synthetic
#: "Workflow was cancelled" error and no output. So there is no recorded state to
#: replay, and restoring one would report an interrupted node as a failure — which
#: would set the run's unhandled-failure flag for a node that merely stopped.
RESTORABLE_SOURCE_STATUSES = (
    ActivityStatus.COMPLETED,
    ActivityStatus.SKIPPED,
    ActivityStatus.FAILED,
)


@activity.defn(name="replay_retry_node")
async def replay_retry_node_activity(
    source_execution_id: str,
    node_id: str,
) -> dict[str, Any] | None:
    """Fetch the recorded state of one node a retry will skip.

    Args:
        source_execution_id: Execution whose ``ActivityExecution`` rows hold the
            state to restore.
        node_id: Canvas node id to fetch, matched exactly against
            ``ActivityExecution.activity_name``.

    Returns:
        The node's ``status``, ``input_data``, ``output_data``, ``error_details``,
        ``started_at`` and ``completed_at`` from the source run, or None when the
        source run has no restorable record for it. All six travel together: the
        caller republishes the input into ``node_inputs``, the output into the
        execution namespace, and restores the recorded status so a skipped node
        stays skipped and an unselected failure stays failed. The sync service
        applies the source timestamps and status, so a restored node reports what
        happened in the source run rather than what happened to the replay.

        Returning None rather than an empty record keeps "nothing ran" distinct
        from "ran and produced nothing" — the caller then executes the node for
        real instead of injecting an empty result.

    Raises:
        SafeValueError: If the serialized size would exceed
            ``JsonbLimits.MAX_FIELD_BYTES``, which would overflow the activity
            result blob. Raised rather than truncated because a silently truncated
            output is worse than a refused retry.

    """
    if not node_id or not node_id.strip():
        return None
    wanted = node_id.strip()

    stored: dict[str, Any] | None = None
    async for session in get_db():
        # Matched by name in the query rather than by scanning the run's rows in
        # Python: this is called once per restored node, so loading every row of
        # the run made each call cost the whole execution. Matching the indexed
        # name returns the one row, and its payload with it.
        #
        # Every restorable status is returned, not just COMPLETED. A retry has to
        # reproduce what the source run did: a node that was skipped stays skipped,
        # and a failure the caller did not select stays failed rather than being
        # quietly reported as a clean skip. The status travels with the payload so
        # the workflow can restore the right one.
        #
        # See RESTORABLE_SOURCE_STATUSES for why the in-flight and cancelled statuses
        # are excluded. A node this does not return has no restorable record, so the
        # caller runs it for real — which is the correct outcome for work that never
        # finished.
        #
        # The name is matched exactly, with no iteration-suffix stripping. Loop
        # replay is out of scope, and classification already excludes loop nodes
        # and loop bodies, so nothing sends a suffixed id on this path. Restoring
        # per-iteration loop state needs more than one record per node — the
        # results are a list keyed by iteration — so that work reworks this
        # transport rather than extending it.
        activity_row = (
            await session.exec(
                select(ActivityExecution)
                .where(
                    ActivityExecution.execution_id == source_execution_id,
                    ActivityExecution.activity_name == wanted,
                    col(ActivityExecution.status).in_(RESTORABLE_SOURCE_STATUSES),
                )
                .limit(1)
            )
        ).first()
        if activity_row is not None:
            stored = {
                # The status the source run ended in, so the restored node reports
                # the same outcome instead of defaulting to a successful replay.
                "status": activity_row.status.value,
                "input_data": activity_row.input_data or {},
                "output_data": activity_row.output_data or {},
                # Carried so a restored failure keeps the reason it failed, rather
                # than surfacing as a skip with no explanation.
                "error_details": activity_row.error_details,
                # The source row's own timestamps, carried so the replayed
                # node's row reports when the work ran, not the replay time.
                "started_at": activity_row.started_at.isoformat() if activity_row.started_at else None,
                "completed_at": activity_row.completed_at.isoformat() if activity_row.completed_at else None,
            }

    if stored is None:
        logger.info(
            "No source record to replay",
            source_execution_id=source_execution_id,
            node_id=node_id,
        )
        return None

    # Measure the JSON that will actually cross the result blob. ``len(str(...))``
    # would measure Python's repr, which is a different and only accidentally
    # similar number.
    serialized_bytes = len(json.dumps(stored, default=str).encode("utf-8"))
    if serialized_bytes > JsonbLimits.MAX_FIELD_BYTES:
        msg = (
            f"restored retry data totals {serialized_bytes} bytes for node {node_id}, "
            f"over the {JsonbLimits.MAX_FIELD_BYTES} byte maximum. This retry cannot restore the "
            "upstream output it needs in order to skip that node."
        )
        raise SafeValueError(msg)

    logger.info(
        "Fetched source node state to replay",
        source_execution_id=source_execution_id,
        node_id=node_id,
        serialized_bytes=serialized_bytes,
    )
    return stored


@activity.defn(name="fetch_retry_source_state")
async def fetch_retry_source_state_activity(source_execution_id: str) -> dict[str, str]:
    """Return source statuses without carrying output payloads into the plan."""
    states: dict[str, str] = {}
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
            if row.activity_name:
                states[strip_iteration_suffix(row.activity_name)] = row.status.value
    return states
