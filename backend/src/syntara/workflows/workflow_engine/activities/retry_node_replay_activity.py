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

import hashlib
import json
from typing import TYPE_CHECKING, Any

import structlog
from sqlmodel import col, or_, select
from temporalio import activity, workflow

from syntara.workflows.workflow_engine.constants import RESTORABLE_SOURCE_STATUSES

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement

with workflow.unsafe.imports_passed_through():
    from syntara.core.constants import JsonbLimits
    from syntara.core.database.session import get_db
    from syntara.core.exceptions import SafeValueError
    from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
    from syntara.workflows.workflow_engine.models.workflow_definition import NodeType
    from syntara.workflows.workflow_engine.utils.loop_iteration_ids import (
        join_loop_iteration_id,
        strip_loop_iteration_suffixes,
    )

logger = structlog.stdlib.get_logger(__name__)


def _result_digest(value: Any) -> str | None:  # noqa: ANN401
    """Return a stable digest for a stored branch result without returning the payload."""
    if value is None:
        return None
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@activity.defn(name="fetch_retry_converge_metadata")
async def fetch_retry_converge_metadata_activity(
    source_execution_id: str,
    converge_temporal_activity_id: str,
    predecessor_temporal_activity_ids: dict[str, str],
) -> dict[str, Any] | None:
    """Read the source converge and direct-predecessor states for retry comparison.

    Branch records are keyed by canvas predecessor ID, while every database lookup
    uses the full Temporal occurrence ID. Output payloads are reduced to a stable
    digest so this lookup does not copy arbitrarily large branch results into
    workflow history.
    """
    if not source_execution_id or not converge_temporal_activity_id:
        return None

    temporal_ids = {converge_temporal_activity_id, *predecessor_temporal_activity_ids.values()}
    rows_by_temporal_id: dict[str, tuple[Any, Any, Any, Any]] = {}
    async for session in get_db():
        rows = (
            await session.exec(
                select(  # type: ignore[call-overload]
                    ActivityExecution.temporal_activity_id,
                    ActivityExecution.status,
                    ActivityExecution.input_data,
                    ActivityExecution.output_data,
                    ActivityExecution.control_data,
                ).where(
                    ActivityExecution.execution_id == source_execution_id,
                    col(ActivityExecution.temporal_activity_id).in_(temporal_ids),
                )
            )
        ).all()
        rows_by_temporal_id = {
            temporal_id: (status, input_data, output_data, control_data)
            for temporal_id, status, input_data, output_data, control_data in rows
            if temporal_id
        }

    source_converge = rows_by_temporal_id.get(converge_temporal_activity_id)
    if source_converge is None:
        return None

    converge_status, input_data, output_data, control_data = source_converge
    input_data = input_data if isinstance(input_data, dict) else {}
    output_data = output_data if isinstance(output_data, dict) else {}
    control_data = control_data if isinstance(control_data, dict) else {}
    gate_metadata = control_data.get("retry_gate_metadata")
    gate_metadata = gate_metadata if isinstance(gate_metadata, dict) else {}

    predecessors: dict[str, dict[str, Any]] = {}
    for predecessor_id, temporal_id in predecessor_temporal_activity_ids.items():
        source = rows_by_temporal_id.get(temporal_id)
        if source is None:
            predecessors[predecessor_id] = {"status": None, "result_digest": None}
            continue
        status, _, branch_output, _ = source
        status_value = status.value if hasattr(status, "value") else str(status)
        predecessors[predecessor_id] = {
            "status": status_value,
            "result_digest": _result_digest(branch_output),
        }

    status_value = converge_status.value if hasattr(converge_status, "value") else str(converge_status)
    return {
        "converge": {
            "status": status_value,
            "input_data": {
                "strategy": input_data.get("strategy"),
                "n_required": input_data.get("n_required"),
            },
            "output_branch_count": output_data.get("branch_count"),
            "gate_metadata": gate_metadata,
        },
        "predecessors": predecessors,
    }


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
@activity.defn(name="replay_retry_node")
async def replay_retry_node_activity(
    source_execution_id: str,
    node_id: str,
    temporal_activity_id: str | None = None,
    require_record: bool = False,  # noqa: FBT001, FBT002
) -> dict[str, Any] | None:
    """Fetch the recorded state of one node a retry will skip.

    Args:
        source_execution_id: Execution whose ``ActivityExecution`` rows hold the
            state to restore.
        node_id: Canvas node ID, used for validation and logging.
        temporal_activity_id: Canonical Temporal activity ID and sole row identity.
            Omitted only when restoring a logical loop row, whose latest occurrence
            is selected by its canvas activity name.
        require_record: Raise when the exact requested occurrence disappeared after
            a prior metadata lookup, rather than emitting a synthetic success.

    Returns:
        The node's ``status``, ``input_data``, ``output_data``, ``error_details``,
        ``control_data``, ``started_at`` and ``completed_at`` from the source run,
        or None when the
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
    wanted_activity_id = temporal_activity_id.strip() if temporal_activity_id else None
    if temporal_activity_id is not None and not wanted_activity_id:
        return None

    stored: dict[str, Any] | None = None
    async for session in get_db():
        # The full Temporal activity ID uniquely selects this occurrence. The UI
        # activity name is intentionally not a retry identity and is never queried.
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
        query = select(ActivityExecution).where(ActivityExecution.execution_id == source_execution_id)
        if wanted_activity_id is not None:
            query = query.where(
                ActivityExecution.temporal_activity_id == wanted_activity_id,
                col(ActivityExecution.status).in_(RESTORABLE_SOURCE_STATUSES),
            )
        else:
            query = query.where(ActivityExecution.activity_name == node_id).order_by(
                col(ActivityExecution.iteration).desc(), col(ActivityExecution.created_at).desc()
            )
        activity_row = (await session.exec(query.limit(1))).first()
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
                # The routing decision the sync layer persisted. Without this the
                # retry cannot tell a recorded branch from one it would have to
                # re-derive, and falls back to inference for every node.
                "control_data": activity_row.control_data,
                # The source row's own timestamps, carried so the replayed
                # node's row reports when the work ran, not the replay time.
                "started_at": activity_row.started_at.isoformat() if activity_row.started_at else None,
                "completed_at": activity_row.completed_at.isoformat() if activity_row.completed_at else None,
            }

    if stored is None:
        if require_record:
            msg = f"Source record for retry converge {node_id} disappeared before it could be replayed"
            raise SafeValueError(msg)
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
async def fetch_retry_source_state_activity(source_execution_id: str) -> dict[str, dict[str, Any]]:
    """Return source statuses and trigger timestamps without loading payloads.

    Statuses are projected for every source activity so retry classification can
    happen before traversal. Timestamps are queried only for trigger rows because
    they are the one executed node whose source times are displayed on retry. The
    unbounded input and output JSONB columns are never selected.
    """
    states: dict[str, str] = {}
    temporal_states: dict[str, str] = {}
    temporal_timestamps: dict[str, dict[str, str | None]] = {}
    trigger_types = (
        NodeType.MANUAL_TRIGGER,
        NodeType.SCHEDULED_TRIGGER,
        NodeType.WEBHOOK_TRIGGER,
        NodeType.EDA_TRIGGER,
    )
    async for session in get_db():
        rows = (
            await session.exec(
                select(ActivityExecution.status, ActivityExecution.temporal_activity_id)
                .where(ActivityExecution.execution_id == source_execution_id)
                .order_by(
                    col(ActivityExecution.iteration), col(ActivityExecution.created_at), col(ActivityExecution.id)
                )
            )
        ).all()
        for status, temporal_activity_id in rows:
            if temporal_activity_id:
                status_value = ActivityStatus(status).value
                states[strip_loop_iteration_suffixes(temporal_activity_id)] = status_value
                temporal_states[temporal_activity_id] = status_value

        trigger_rows = (
            await session.exec(
                select(
                    ActivityExecution.temporal_activity_id,
                    ActivityExecution.started_at,
                    ActivityExecution.completed_at,
                ).where(
                    ActivityExecution.execution_id == source_execution_id,
                    col(ActivityExecution.node_type).in_(trigger_types),
                )
            )
        ).all()
        for temporal_activity_id, started_at, completed_at in trigger_rows:
            if temporal_activity_id:
                temporal_timestamps[temporal_activity_id] = {
                    "started_at": started_at.isoformat() if started_at else None,
                    "completed_at": completed_at.isoformat() if completed_at else None,
                }

    return {
        "activity_statuses": states,
        "temporal_activity_statuses": temporal_states,
        "temporal_activity_timestamps": temporal_timestamps,
    }


@activity.defn
async def retry_control_ports(source_execution_id: str) -> dict[str, str]:
    """Routing decision each control occurrence's source run recorded.

    Read in one pass during ``_prepare_retry`` because restorable-node selection
    and ``_should_restore_node`` are synchronous: they cannot dispatch an
    activity per node, and without this they would reject a control node before
    the branch its source run persisted was ever read.

    Only nodes that actually persisted a ``next_port`` appear. Anything absent —
    a run predating the column, a control node with no routing of its own — is
    left to the caller's inference fallback.

    Args:
        source_execution_id: Execution whose control nodes hold the routing state.

    Returns:
        Canonical Temporal activity ID to port, for control occurrences that recorded one.

    """
    ports: dict[str, str] = {}
    async for session in get_db():
        rows = (
            await session.exec(
                select(
                    ActivityExecution.temporal_activity_id,
                    ActivityExecution.control_data,
                ).where(
                    ActivityExecution.execution_id == source_execution_id,
                    col(ActivityExecution.control_data).isnot(None),
                )
            )
        ).all()
        for temporal_activity_id, control_data in rows:
            if not isinstance(control_data, dict):
                continue
            port = control_data.get("next_port")
            if port and temporal_activity_id:
                ports[temporal_activity_id] = str(port)
    return ports


@activity.defn
async def probe_retry_loop_iteration(
    source_execution_id: str,
    iterate_entry_node_ids: list[str],
    child_loop_entry_ids: list[str],
    iteration_path: list[int],
) -> bool:
    """Whether the source run reached the next loop iteration.

    The graph's ``iterate`` port successors are the entry points for the next
    iteration. Ordinary entries are checked for their exact canonical Temporal
    activity ID. A nested-loop entry appends its own iteration index, so its ID
    is checked under the current path prefix. Missing entry evidence means the
    next iteration was not reached.
    """
    if not iteration_path:
        return False
    if not iterate_entry_node_ids and not child_loop_entry_ids:
        return False

    exact_activity_ids = [join_loop_iteration_id(node_id, iteration_path) for node_id in iterate_entry_node_ids]
    child_loop_prefixes = [
        join_loop_iteration_id(node_id, iteration_path) + "_iter_" for node_id in child_loop_entry_ids
    ]
    async for session in get_db():
        direct_conditions: list[ColumnElement[bool]] = [
            col(ActivityExecution.temporal_activity_id).in_(exact_activity_ids)
        ]
        direct_conditions.extend(
            col(ActivityExecution.temporal_activity_id).startswith(prefix, autoescape=True)
            for prefix in child_loop_prefixes
        )
        found = await session.exec(
            select(ActivityExecution.id)
            .where(ActivityExecution.execution_id == source_execution_id, or_(*direct_conditions))
            .limit(1)
        )
        return found.first() is not None

    return False


@activity.defn(name="sync_retry_loop_record")
async def sync_retry_loop_record_activity() -> None:
    """Emit the one-shot activity event that persists a staged logical loop row."""
