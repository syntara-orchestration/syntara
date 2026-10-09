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
    """Return source statuses, projected so no payload is read.

    Only the three columns this needs are selected. ``input_data`` and
    ``output_data`` are unbounded JSONB, and selecting the whole row deserializes
    both for every activity in the source execution — on the workflow's critical
    path, before any node has dispatched. The sibling replay activity projects its
    own query for the same reason.
    """
    states: dict[str, str] = {}
    async for session in get_db():
        rows = (
            await session.exec(
                select(ActivityExecution.activity_name, ActivityExecution.status)
                .where(ActivityExecution.execution_id == source_execution_id)
                .order_by(
                    col(ActivityExecution.iteration), col(ActivityExecution.created_at), col(ActivityExecution.id)
                )
            )
        ).all()
        for activity_name, status in rows:
            if activity_name:
                states[strip_iteration_suffix(activity_name)] = ActivityStatus(status).value
    return states


#: Statuses a loop's per-iteration rows can carry. FAILED is included because it is
#: the terminal status that decides where a retry resumes, so the iteration that
#: stopped the run is in the source data.
_LOOP_ITERATION_STATUSES = (
    ActivityStatus.COMPLETED,
    ActivityStatus.FAILED,
)


@activity.defn(name="fetch_retry_loop_state")
async def fetch_retry_loop_state_activity(
    source_execution_id: str,
    loops: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    """Fetch the per-iteration state a retry needs to resume a loop mid-run.

    The control plane selects failure points by base node id, so the iteration a
    loop stopped on is not in the payload. It is recovered from the
    ``ActivityExecution`` rows the source run already wrote: the sync service creates
    one row per iteration (``iteration`` column, ``#iter-<n>`` suffix), including the
    failed one.

    Args:
        source_execution_id: Execution whose rows hold the loop's iteration state.
        loops: Map of loop node id to the body node ids inside it. Only these nodes
            are considered, so an identically-named node elsewhere in the workflow
            cannot contribute to the resume point.

    Returns:
        Map of loop node id to its resume state::

            {"loop_1": {"resume_iteration": 2,
                        "iteration_results": {"body_a.receipt": ["r0"], ...}}}

        ``resume_iteration`` is the iteration the retry restarts *at*, so iterations
        below it are treated as already done. ``iteration_results`` mirrors the
        engine's own ``loop_iteration_results`` accumulation for those skipped
        iterations, and is absent when the loop needs no resume.

    Raises:
        SafeValueError: If a loop's aggregate serialized size would exceed
            ``JsonbLimits.MAX_FIELD_BYTES``. Measured across the whole per-loop
            payload rather than one iteration: the cost is in the aggregate, and
            iterating a large loop is precisely the case that produces it. Refused
            rather than truncated, because a truncated iteration list would silently
            drop results the loop body depends on.

    """
    if not loops:
        return {}

    body_to_loop = {body_id: loop_id for loop_id, body_ids in loops.items() for body_id in body_ids}
    result: dict[str, dict[str, Any]] = {}
    oversized: str | None = None

    async for session in get_db():
        rows = (
            await session.exec(
                select(ActivityExecution).where(
                    ActivityExecution.execution_id == source_execution_id,
                    col(ActivityExecution.status).in_(_LOOP_ITERATION_STATUSES),
                )
            )
        ).all()

        # Per loop: the failed iterations and the completed ones, each as
        # (iteration, base node id, output).
        per_loop: dict[str, dict[str, list[tuple[int, str, dict[str, Any]]]]] = {}
        for row in rows:
            if not row.activity_name:
                continue
            base_id = strip_iteration_suffix(row.activity_name)
            owner = body_to_loop.get(base_id)
            if owner is None:
                continue
            # ``iteration`` is set to 0 on the original row and N on each
            # per-iteration row, so it is the authoritative index rather than the
            # name suffix.
            index = row.iteration if row.iteration is not None else 0
            bucket = "failed" if row.status == ActivityStatus.FAILED else "completed"
            per_loop.setdefault(owner, {"failed": [], "completed": []})[bucket].append(
                (index, base_id, row.output_data or {})
            )

        for loop_id, buckets in per_loop.items():
            failed_rows = buckets["failed"]
            if not failed_rows:
                continue
            # Resume at the *last* failed iteration, not the first.
            #
            # A loop body node with continue_on_failure may fail on an early
            # iteration and the loop carries on to later ones, so the source run can
            # hold several FAILED rows for one loop. Only the last one stopped the
            # workflow; every earlier failure was tolerated and its side effects
            # already happened. Resuming from the earliest of them would re-run those
            # iterations and repeat their side effects. Resuming from the last one
            # cannot skip it, because that is the iteration being retried.
            resume_iteration = max(index for index, _base, _output in failed_rows)
            iteration_results = _rebuild_iteration_results(buckets["completed"], resume_iteration)
            if oversized is None and _exceeds_size_limit(iteration_results):
                oversized = loop_id
                continue
            result[loop_id] = {
                "resume_iteration": resume_iteration,
                "iteration_results": iteration_results,
            }

    if oversized is not None:
        msg = (
            f"restored loop state for {oversized} exceeds the "
            f"{JsonbLimits.MAX_FIELD_BYTES} byte maximum. This retry cannot restore the "
            "iteration results its loop body needs in order to resume."
        )
        raise SafeValueError(msg)

    logger.info(
        "Fetched retry loop state",
        source_execution_id=source_execution_id,
        loop_count=len(result),
        resume_points={loop_id: state["resume_iteration"] for loop_id, state in result.items()},
    )
    return result


def _exceeds_size_limit(iteration_results: dict[str, list[Any]]) -> bool:
    """Whether a loop's rebuilt iteration results cross the JSONB field ceiling."""
    serialized_bytes = len(json.dumps(iteration_results, default=str).encode("utf-8"))
    return serialized_bytes > JsonbLimits.MAX_FIELD_BYTES


def _rebuild_iteration_results(
    completed: list[tuple[int, str, dict[str, Any]]],
    resume_iteration: int,
) -> dict[str, list[Any]]:
    """Rebuild ``loop_iteration_results`` for the iterations a retry skips.

    Mirrors the engine's own per-iteration accumulation, which appends each field of
    a body node's namespace entry under ``"{node}.{field}"`` as the iteration
    finishes. Two details matter for fidelity:

    * The engine's namespace entry is ``{**output, "status": "completed"}``, but
      ``output_data`` in the database is the bare activity output and never carries
      that synthetic key. It is re-added here, or the rebuilt aggregation silently
      lacks ``"{node}.status"`` compared with the original run.
    * Fields are appended only when the iteration actually produced them, so the
      lists are ragged and are built per node in iteration order rather than zipped
      against a fixed range. A node that returns different fields on different
      iterations stays aligned with the original run's ragged shape.
    """
    results: dict[str, list[Any]] = {}
    for index, base_id, output in sorted(completed, key=lambda item: (item[1], item[0])):
        if index >= resume_iteration:
            continue
        for field, value in {**output, "status": "completed"}.items():
            results.setdefault(f"{base_id}.{field}", []).append(value)
    return results
