"""Retry output resolution activity for retry-from-failure.

When an execution is retried from a failure point, the nodes upstream of that
point are skipped and the workflow needs their stored ``output_data`` injected
into the execution namespace so downstream nodes read them as if those nodes had
just run.

Outputs are fetched per node to bound activity-result payloads. Temporal records
activity results in history; restoring them through an activity does not remove
that history cost. Namespace publication uses the ordinary completion path.
"""

import json
import time
from typing import TYPE_CHECKING, Any

import structlog
from sqlmodel import col, select
from temporalio import activity, workflow

with workflow.unsafe.imports_passed_through():
    from syntara.core.constants import JsonbLimits
    from syntara.core.database.session import get_db
    from syntara.core.exceptions import SafeValueError
    from syntara.metrics.dependencies import get_metrics_recorder
    from syntara.metrics.types import MetricType
    from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
    from syntara.workflows.utils.loop_iteration_names import strip_iteration_suffix

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = structlog.stdlib.get_logger(__name__)


@activity.defn(name="fetch_retry_outputs")
async def fetch_retry_outputs_activity(
    source_execution_id: str,
    node_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Fetch stored outputs for nodes a retry will skip.

    Args:
        source_execution_id: Execution whose ``ActivityExecution`` rows hold the
            outputs to restore.
        node_ids: Canvas node ids to fetch. Loop-iteration-suffixed ids are
            accepted and resolved to their base node.

    Returns:
        Map of node id to the output of its most recent ``COMPLETED`` activity
        in the source run. Nodes with no completed activity are absent from the
        map rather than mapped to an empty output, so the caller can tell
        "nothing ran" apart from "ran and produced nothing".

    Raises:
        SafeValueError: If the combined serialized size would exceed
            ``JsonbLimits.MAX_FIELD_BYTES``, which would overflow the activity
            result blob. Raised rather than truncated because a silently
            truncated output is worse than a refused retry.

    """
    started = time.monotonic()
    if not node_ids:
        return {}

    wanted = {strip_iteration_suffix(node_id.strip()) for node_id in node_ids if node_id and node_id.strip()}
    if not wanted:
        return {}

    outputs: dict[str, dict[str, Any]] = {}
    async for session in get_db():
        activities = (
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
        # Ids are matched on the base node id, so a loop node resolves to the
        # most recent completed iteration. Per-iteration granularity is
        # classification's concern, not the transport's.
        for activity_row in activities:
            base_id = strip_iteration_suffix(activity_row.activity_name)
            if base_id in wanted:
                outputs[base_id] = activity_row.output_data or {}

    # Measure the JSON that will actually cross the result blob. ``len(str(...))``
    # would measure Python's repr, which is a different and only accidentally
    # similar number.
    serialized_bytes = len(json.dumps(outputs, default=str).encode("utf-8"))
    if serialized_bytes > JsonbLimits.MAX_FIELD_BYTES:
        msg = (
            f"restored retry outputs total {serialized_bytes} bytes across {len(outputs)} node(s), "
            f"over the {JsonbLimits.MAX_FIELD_BYTES} byte maximum. This retry cannot restore the "
            "upstream outputs it needs in order to skip those nodes."
        )
        raise SafeValueError(msg)

    logger.info(
        "Fetched retry outputs",
        source_execution_id=source_execution_id,
        node_count=len(outputs),
        serialized_bytes=serialized_bytes,
    )
    try:
        get_metrics_recorder().record(
            MetricType.RETRY_RESTORATION_DURATION,
            (time.monotonic() - started) * 1000,
            unit="ms",
            labels={
                "component": "execution_service",
                "execution_mode": "retry",
                "node_count": str(len(wanted)),
                "restored_node_count": str(len(outputs)),
            },
        )
    except Exception:  # noqa: BLE001 -- telemetry must never prevent restoration
        logger.warning("Unable to record retry restoration metrics", exc_info=True)
    return outputs


@activity.defn(name="fetch_retry_loop_state")
async def fetch_retry_loop_state_activity(
    source_execution_id: str,
    loops: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    """Fetch the per-iteration state a retry needs to resume a loop mid-run.

    The control plane selects failure points by base node id, so the iteration a
    loop stopped on is not in the payload. It is recovered here from the
    ``ActivityExecution`` rows the source run already wrote: the sync service
    creates one row per iteration (``iteration`` column, ``#iter-<n>`` suffix),
    including the failed one because FAILED is a terminal status.

    Args:
        source_execution_id: Execution whose rows hold the loop's iteration state.
        loops: Map of loop node id to the body node ids inside it. Only these
            nodes are considered, so an identically-named node elsewhere in the
            workflow cannot contribute to the resume point.

    Returns:
        Map of loop node id to its resume state::

            {"loop_1": {"resume_iteration": 2,
                        "iteration_results": {"body_a.receipt": ["r0"], ...}}}

        ``resume_iteration`` is the iteration the retry restarts *at*, so
        iterations below it are treated as already done. ``iteration_results``
        mirrors the engine's own ``loop_iteration_results`` accumulation for
        those skipped iterations, and is absent when the loop needs no resume.

    """
    if not loops:
        return {}

    body_to_loop: dict[str, str] = {}
    for loop_id, body_ids in loops.items():
        for body_id in body_ids:
            body_to_loop[body_id] = loop_id

    rows: Sequence[ActivityExecution] = ()
    async for session in get_db():
        rows = (
            await session.exec(
                select(ActivityExecution).where(
                    ActivityExecution.execution_id == source_execution_id,
                    col(ActivityExecution.status).in_([ActivityStatus.COMPLETED, ActivityStatus.FAILED]),
                )
            )
        ).all()

    # Per loop: the failed iterations and the completed ones, each as
    # (iteration, base node id, output).
    per_loop: dict[str, dict[str, list[tuple[int, str, dict[str, Any]]]]] = {}
    for row in rows:
        # activity_name is nullable in the schema, though never null in practice
        # for a row this query selects.
        if not row.activity_name:
            continue
        base_id = strip_iteration_suffix(row.activity_name)
        owner = body_to_loop.get(base_id)
        if owner is None:
            continue
        # ``iteration`` is set to 0 on the original row and N on each per-iteration
        # row, so it is the authoritative index rather than the name suffix.
        index = row.iteration if row.iteration is not None else 0
        bucket = "failed" if row.status == ActivityStatus.FAILED else "completed"
        per_loop.setdefault(owner, {"failed": [], "completed": []})[bucket].append(
            (index, base_id, row.output_data or {})
        )

    result: dict[str, dict[str, Any]] = {}
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
        result[loop_id] = {
            "restored_activity_names": [
                row.activity_name
                for row in rows
                if row.activity_name
                and body_to_loop.get(strip_iteration_suffix(row.activity_name)) == loop_id
                and row.status == ActivityStatus.COMPLETED
                and (row.iteration or 0) < resume_iteration
            ],
            "resume_iteration": resume_iteration,
            "iteration_results": _rebuild_iteration_results(buckets["completed"], resume_iteration),
        }

    logger.info(
        "Fetched retry loop state",
        source_execution_id=source_execution_id,
        loop_count=len(result),
        resume_points={loop_id: state["resume_iteration"] for loop_id, state in result.items()},
    )
    return result


def _rebuild_iteration_results(
    completed: list[tuple[int, str, dict[str, Any]]],
    resume_iteration: int,
) -> dict[str, list[Any]]:
    """Rebuild ``loop_iteration_results`` for the iterations a retry skips.

    Mirrors ``DynamicWorkflow._clear_loop_body``, which appends each field of a
    body node's resolver namespace under ``"{node}.{field}"`` as the iteration
    finishes. Two details matter for fidelity:

    * The engine's namespace entry is ``{**output, "status": "completed"}``, but
      ``output_data`` in the database is the bare activity output and never
      carries that synthetic key. It is re-added here, or the rebuilt aggregation
      silently lacks ``"{node}.status"`` compared with the original run.
    * Fields are appended only when the iteration actually produced them, so the
      lists are ragged and are built per node in iteration order rather than
      zipped against a fixed range. A node that returns different fields on
      different iterations stays aligned with the original run's ragged shape.
    """
    results: dict[str, list[Any]] = {}
    for index, base_id, output in sorted(completed, key=lambda item: (item[1], item[0])):
        if index >= resume_iteration:
            continue
        for field, value in {**output, "status": "completed"}.items():
            results.setdefault(f"{base_id}.{field}", []).append(value)
    return results


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
