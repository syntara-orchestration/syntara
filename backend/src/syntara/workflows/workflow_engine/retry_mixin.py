"""Retry-from-failure orchestration, sharing the normal node completion path."""

import collections
from datetime import timedelta
from typing import Any, cast

from temporalio import workflow
from temporalio.exceptions import ApplicationError

from syntara.core.exceptions import SafeValueError
from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.utils.loop_body_nodes import collect_direct_loop_bodies, collect_loop_bodies
from syntara.workflows.utils.loop_iteration_names import LOOP_ITERATION_SEP, strip_iteration_suffix
from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.constants import (
    DEFAULT_ACTIVITY_TIMEOUT_SECONDS,
    RESTORABLE_SOURCE_STATUSES,
)
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, LoopState, NodeType
from syntara.workflows.workflow_engine.utils.loop_iteration_ids import (
    approval_temporal_activity_id,
    loop_body_temporal_activity_id,
    loop_index_chain,
    loop_iteration_path,
    retry_loop_record_activity_id,
    strip_loop_iteration_suffixes,
)

#: Node types a retry executes rather than restores from the source run.
#:
#: Not named simply ``_CONTROL_NODE_TYPES`` because "control node" means different
#: things for different purposes; this is the retry-specific reading. A node listed
#: here is one whose routing a restored output cannot stand in for, so the retry
#: runs it again instead of replaying a decision against a half-rebuilt namespace.
#:
#: WAIT and APPROVAL are deliberately absent. Re-running either is wrong: a wait's
#: duration is measured against the clock, so re-running restarts a wait the
#: source run already sat through, and an approval re-prompts a human for a
#: decision that was already made. Both are restored instead and route on what the
#: source run recorded — a wait has a single successor, and an approval routes on
#: its recorded decision.
#: The same set the replay activity filters its query by, as plain strings so it
#: can be tested against ``_retry_source_statuses`` without an enum conversion per
#: node. One definition: the workflow and the query must agree on what a retry can
#: restore, or the workflow skips a replay the activity would have performed.
_RESTORABLE_SOURCE_STATUS_VALUES = frozenset(status.value for status in RESTORABLE_SOURCE_STATUSES)

_CONTROL_NODE_TYPES_FOR_RETRY = frozenset(
    {
        NodeType.CONDITION,
        NodeType.SWITCH,
        # A converge decides whether it has enough predecessors to run, so restoring
        # one would release its successors without the gate ever being evaluated.
        NodeType.CONVERGE,
    }
)

#: A control node needs at least two output ports before a branch means anything.
_MIN_BRANCHES_FOR_INFERENCE = 2

#: Control nodes whose taken branch can be inferred from a source run's node
#: statuses, so replaying them is possible even when the run predates persisted
#: control state. LOOP and WAIT are absent: a loop's position is a per-iteration
#: question, and a wait node emits no control data at all.
_INFERABLE_CONTROL_NODE_TYPES = frozenset(
    {
        NodeType.CONDITION,
        NodeType.SWITCH,
    }
)


class WorkflowRetryMixin:
    """Retry policy and restoration; state is initialized by the workflow."""

    retry_context: dict[str, Any]
    _retry_restorable_cache: set[str] | None
    #: The upstream region, decided up front in ``_prepare_retry``. The sync service
    #: asks the workflow whether a completing activity is one of these before
    #: waiting on it, so it must be populated before any node runs. Nothing is
    #: pre-subtracted, not even a control node this retry cannot replay, because
    #: the set is expected to grow into replaying every control node. A node that
    #: is a candidate when it is scheduled but turns out to rerun is discarded
    #: then, before it completes, so the service never waits on it.
    _retry_replay_candidates: set[str]
    #: Source times/status keyed by canonical Temporal activity ID, with a base-ID
    #: alias retained for nodes and sync workers that do not carry iteration IDs.
    _restored_node_timestamps: dict[str, dict[str, str | None]]
    #: The source status of a node this retry restored, keyed by node id. Read by the
    #: completion path so a restored skip or failure is not republished as a success
    #: and does not have its successors scheduled.
    _restored_node_statuses: dict[str, str]
    #: The routing decision each restorable control node's source run recorded,
    #: keyed by node id. Read once during ``_prepare_retry`` so the synchronous
    #: classification paths can honour it without awaiting anything.
    _restored_control_ports: dict[str, str]
    #: The port each control node resolved to, keyed by node id. Memoised because
    #: the resolver is reached from candidate construction and again when the node
    #: is scheduled, and workflow code must reach the same answer both times.
    _resolved_control_port_cache: dict[str, str | None]
    #: The output a restored node produced before it failed in the source run,
    #: keyed by node id. Republished by the failure path, so a successor reading it
    #: sees what the source run produced rather than an empty output model.
    _restored_node_outputs: dict[str, dict[str, Any]]
    _runtime_settings: dict[str, Any]
    #: Published by the workflow: where a restored failure is recorded, so it reads
    #: the same as one that genuinely failed in this run.
    failed_nodes: dict[str, str]
    #: The namespace resolver the workflow holds. Typed by the workflow itself, so
    #: this only declares that the mixin needs one; a narrower type here would
    #: override the workflow's own annotation.
    resolver: NamespaceResolver
    loop_body_map: dict[str, str]
    node_control_data: dict[str, dict[str, Any]]
    _retry_source_statuses: dict[str, str]
    _retry_source_activity_name_statuses: dict[str, str]
    _retry_source_temporal_statuses: dict[str, str]
    _retry_selected_failure_paths: dict[str, list[list[int]]]
    skipped_nodes: set[str]
    node_inputs: dict[str, dict[str, Any]]
    loop_state: dict[str, LoopState]
    loop_iteration_results: dict[str, dict[str, list[Any]]]
    #: Body nodes per loop, derived from the graph during _prepare_retry. Cached
    #: because the loop control needs them on every iteration and the graph does
    #: not change during a run.
    _loop_bodies: dict[str, set[str]]
    _loop_direct_bodies: dict[str, set[str]]
    _loop_direct_child_loops: dict[str, set[str]]
    #: Which iteration each loop is currently replaying, so a body node's own replay
    #: can ask for the row for that iteration rather than the first.
    _active_loop_iteration: dict[str, int]

    def _initialize_state(
        self,
        execution_id: str,  # noqa: ARG002
        request_id: str | None = None,  # noqa: ARG002
        pre_resolved_outputs: dict[str, dict[str, Any]] | None = None,  # noqa: ARG002
        stop_after_nodes: list[str] | None = None,  # noqa: ARG002
        workflow_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Declare the retry state this mixin needs, before any node runs.

        Called from the workflow's own initializer rather than inlined there, so
        the set of retry attributes lives with the policy that uses them instead of
        being split across two files.

        The signature matches the workflow's own ``_initialize_state`` exactly, as
        cooperative ``super()`` initialization requires — the child drives the order
        and each mixin declares only the slice it owns. ``execution_id``,
        ``request_id``, ``pre_resolved_outputs`` and ``stop_after_nodes`` are
        accepted to keep that contract and are deliberately unused here.

        Ordering matters and is why this is a separate call. ``retry_context`` is
        control-plane state, not expression data: a user expression must not be
        able to read ``eligible_point_ids`` or the input overrides. The caller
        therefore has to assign it before walking the namespace, so that the loop
        which registers each entry can skip the ``retry`` key rather than popping
        it afterwards.
        """
        self.retry_context = dict(workflow_metadata.get("retry", {})) if workflow_metadata else {}
        # Memoised restorable set: derived from the graph and the retry context,
        # neither of which changes during a run.
        self._retry_restorable_cache: set[str] | None = None
        # The upstream region, and the source state for the nodes it restored.
        # The sync service consults the candidate set to tell a replayed activity
        # from an ordinary one before waiting on it, so these are filled during
        # _prepare_retry rather than on first use.
        self._retry_replay_candidates: set[str] = set()
        self._restored_node_timestamps: dict[str, dict[str, str | None]] = {}
        self._restored_node_statuses: dict[str, str] = {}
        self._restored_node_outputs: dict[str, dict[str, Any]] = {}
        self._restored_control_ports: dict[str, str] = {}
        self._resolved_control_port_cache: dict[str, str | None] = {}
        self._retry_source_statuses: dict[str, str] = {}
        self._retry_source_activity_name_statuses: dict[str, str] = {}
        self._retry_source_temporal_statuses: dict[str, str] = {}
        self._retry_selected_failure_paths: dict[str, list[list[int]]] = {}
        # Filled from the graph by _prepare_retry; a loop body replays per iteration,
        # and the control node needs the body set on every iteration.
        self._loop_bodies: dict[str, set[str]] = {}
        self._loop_direct_bodies: dict[str, set[str]] = {}
        self._loop_direct_child_loops: dict[str, set[str]] = {}
        self._active_loop_iteration: dict[str, int] = {}
        self._retry_loop_record_states: dict[str, dict[str, Any]] = {}
        self._retry_live_loop_ids: set[str] = set()

    def _create_loop_state_for_type(self, loop_type: str, node: ActivityNode) -> LoopState: ...  # type: ignore[empty-body]

    async def _prepare_retry(self, graph: WorkflowGraph) -> None:
        """Load source state once and exclude branches not selected for retry."""
        if not self.retry_context:
            return
        self._loop_bodies = {
            owner: set(nodes)
            for owner, nodes in collect_loop_bodies(
                {node.id: graph.get_successors(node.id) for node in graph.get_all_nodes()},
                {
                    owner: [node.id for node in graph.get_next_activities_by_port(owner, "iterate")]
                    for owner in [n.id for n in graph.get_all_nodes() if n.type == NodeType.LOOP]
                },
            ).items()
        }
        graph_nodes = {node.id: node for node in graph.get_all_nodes()}
        loop_ids = {node.id for node in graph_nodes.values() if node.type == NodeType.LOOP}
        self._loop_direct_bodies = collect_direct_loop_bodies(self._loop_bodies, loop_ids)
        self._loop_direct_child_loops = {loop_id: body & loop_ids for loop_id, body in self._loop_direct_bodies.items()}
        source_state = await workflow.execute_activity(
            ActivityName.RETRY_SOURCE_STATE,
            args=[self.retry_context["retry_from_execution_id"]],
            activity_id="__internal__fetch_retry_source_state",
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
        )
        # Newer fetches return all three indexes so nested iterations can be
        # classified by their exact Temporal ID. Keep accepting the original flat
        # mapping while a retry started by an older workflow version is replayed.
        if "activity_statuses" in source_state:
            self._retry_source_statuses = source_state["activity_statuses"]
            self._retry_source_activity_name_statuses = source_state.get("activity_name_statuses", {})
            self._retry_source_temporal_statuses = source_state.get("temporal_activity_statuses", {})
        else:
            self._retry_source_statuses = source_state
        self._retry_selected_failure_paths = self._selected_failure_iteration_paths()
        # Persisted routing, read before anything classifies. Restorable-node
        # selection and _should_restore_node are both synchronous, so the branch a
        # source run recorded has to be known already — otherwise both would fall
        # back to inference and reject a node whose branch is sitting in the row.
        self._restored_control_ports = await workflow.execute_activity(
            ActivityName.RETRY_CONTROL_PORTS,
            args=[self.retry_context["retry_from_execution_id"]],
            activity_id="__internal__fetch_retry_control_ports",
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
        )
        self._classify_unselected_branches(graph)
        # The upstream region, control nodes included: the set is expected to grow
        # into replaying every control node, so nothing is pre-subtracted here and
        # the replay-or-rerun choice is made when the node is scheduled. Decided
        # here rather than on first use because the sync service consults it the
        # moment an activity completes, so a node discovered mid-graph would look
        # like an ordinary execution and never get its source times.
        #
        # Control nodes are included even though 826 cannot replay all of them.
        # _maybe_restore_retry_output discards one the moment it decides to rerun
        # it, so the set can stay open to the control nodes a later PR will add
        # without the sync service ever waiting on one that will not replay.
        self._retry_replay_candidates = set(self._retry_restorable_nodes(graph))

    def _classify_unselected_branches(self, graph: WorkflowGraph) -> None:
        """Skip unselected failures without suppressing shared selected descendants.

        Completed nodes form a boundary: a satisfied converge and its descendants
        retain their results under R6c, even if a different predecessor failed.

        A failure the caller did not select is restored as a failure by
        ``_restore_node_state``, from its own recorded error. What this suppresses
        is everything *downstream* of such a failure — those nodes have nothing to
        run against, and the source run never produced results for them either. The
        failing node itself is deliberately not added here: marking it skipped would
        report a failure as a clean skip and drop the reason it failed.
        """
        selected = {strip_iteration_suffix(point) for point in self.retry_context.get("eligible_point_ids", [])}
        rerun: set[str] = set()
        for point in selected:
            rerun.update(self._walk_downstream(point, graph))
        for node_id, status in self._retry_source_statuses.items():
            if status != "failed" or node_id in rerun:
                continue
            pending = list(graph.get_successors(node_id))
            seen: set[str] = set()
            while pending:
                current = pending.pop()
                if current in seen or current in rerun or self._retry_source_statuses.get(current) == "completed":
                    continue
                seen.add(current)
                self.skipped_nodes.add(current)
                pending.extend(graph.get_successors(current))

    def _retry_restorable_nodes(self, graph: WorkflowGraph) -> set[str]:
        """Return the base node ids in this retry's upstream region.

        The control plane already validated the selection, so this only re-derives
        *which upstream nodes may be skipped* — a node qualifies when it is not a
        retry starting point, not a trigger node, and not downstream of a retry
        point. Loop bodies remain candidates because replay selects their source
        row for the active iteration.

        Control nodes stay in this set. Whether one is actually replayed is decided
        when traversal reaches it, not here: a condition or switch whose branch is
        recoverable is restored, and one whose branch cannot be recovered runs
        normally. Excluding them here and re-admitting them at the point of use
        encodes the same rule in two places that have to keep agreeing, and it
        leaves out the control nodes a later PR will want to replay.

        R6a's continue_on_failure case is covered by the ``downstream`` subtraction
        rather than a rule of its own. A failed CoF step is a retry point, so
        everything downstream of it is downstream of a failure point — which is
        exactly the set that must re-run, because its inputs may depend on the
        failed output that no longer exists. A separate walk over the same nodes
        could only produce a subset of that set, so it is not computed.
        """
        cached = self._retry_restorable_cache
        if cached is not None:
            return cached

        # The control plane resolves the selection to the set of failure points
        # that will actually run, and that set is the authority. There is no
        # separate record of what the caller originally picked: a default
        # selection is already expanded to every failed node by the time it gets
        # here, so reading one would either be absent or a stale duplicate.
        must_run = {strip_iteration_suffix(point) for point in self.retry_context.get("eligible_point_ids", [])}

        # Trigger nodes are excluded: the retry re-enters the graph at its first
        # eligible point, and the control plane already re-resolved the trigger
        # input, so there is no source output to restore for one.
        triggers = {node.id for node in graph.get_trigger_nodes()}

        # Keep the whole upstream region, including control nodes and loop bodies.
        # _maybe_restore_retry_output decides at scheduling time whether a control
        # node can replay; loop bodies use the active iteration to select the
        # corresponding source row. Removing either group here would prevent the
        # sync service from recognizing their replay activities.

        # Everything downstream of a failure point re-executes, so it cannot be
        # restored: a restored downstream node would never re-run to consume the
        # failure point's fresh output, silently discarding the result of the very
        # retry that was asked for.
        downstream: set[str] = set()
        for node_id in must_run:
            downstream |= self._walk_downstream(node_id, graph)

        restorable = {node.id for node in graph.get_all_nodes()} - must_run - triggers - downstream
        self._retry_restorable_cache = restorable
        return restorable

    def _resolved_control_port(self, node: ActivityNode, graph: WorkflowGraph) -> str | None:
        """Resolve the port this control node is routed by, or None to rerun.

        Resolved once per node, in the order the branch is actually known:

        1. what the source run persisted in ``control_data``,
        2. failing that, the branch inferred from the source run's statuses,
        3. failing that, rerun the node for real.

        The persisted value has to win in the synchronous paths too — restorable
        classification and ``_should_restore_node`` both run before any node can
        dispatch an activity, so an unconsulted record would be rejected before the
        branch was ever read.
        """
        temporal_id = self._source_temporal_activity_id(node)
        iteration_path = loop_index_chain(
            node.id, getattr(self, "loop_body_map", {}), getattr(self, "node_control_data", {})
        )
        cache_key = temporal_id if iteration_path else node.id
        if cache_key in self._resolved_control_port_cache:
            return self._resolved_control_port_cache[cache_key]

        recorded = self._restored_control_ports.get(temporal_id)
        if recorded is None and iteration_path:
            # A single-level pre-path history can still be identified by its
            # per-iteration activity name. Nested legacy rows are ambiguous and
            # must be inferred from current-path source statuses or rerun.
            if len(iteration_path) == 1 and loop_iteration_path(temporal_id) != iteration_path:
                recorded = self._restored_control_ports.get(self._replay_source_name(node.id))
        elif recorded is None:
            recorded = self._restored_control_ports.get(node.id)
        resolved = str(recorded) if recorded else self._infer_control_node_branch(node, graph)
        self._resolved_control_port_cache[cache_key] = resolved
        return resolved

    def _source_temporal_activity_id(self, node: ActivityNode) -> str:
        """Canonical source ID for this node at the active loop iteration path."""
        loop_body_map = getattr(self, "loop_body_map", {})
        node_control_data = getattr(self, "node_control_data", {})
        if node.type == NodeType.APPROVAL:
            return approval_temporal_activity_id(node.id, loop_body_map, node_control_data)
        return loop_body_temporal_activity_id(node.id, loop_body_map, node_control_data)

    def _selected_failure_iteration_paths(self) -> dict[str, list[list[int]]]:
        """Index selected failed rows by their recorded complete iteration path."""
        selected = {strip_iteration_suffix(point) for point in self.retry_context.get("eligible_point_ids", [])}
        paths: dict[str, list[list[int]]] = {}
        temporal_statuses = getattr(self, "_retry_source_temporal_statuses", {})
        activity_name_statuses = getattr(self, "_retry_source_activity_name_statuses", {})
        for temporal_id, status in temporal_statuses.items():
            node_id = strip_loop_iteration_suffixes(temporal_id)
            path = loop_iteration_path(temporal_id)
            if node_id in selected and status == ActivityStatus.FAILED.value and path:
                paths.setdefault(node_id, []).append(path)

        # Before path-aware Temporal IDs were introduced, single-level loop rows
        # were still named ``node#iter-N`` by the sync service. Recover that one
        # index for compatibility; nested legacy names do not encode a safe path.
        for activity_name, status in activity_name_statuses.items():
            if status != ActivityStatus.FAILED.value:
                continue
            node_id = strip_iteration_suffix(activity_name)
            if node_id not in selected:
                continue
            if paths.get(node_id):
                # A canonical Temporal ID already gives the complete path. The
                # composite display name carries only a global iteration counter
                # and must not be mistaken for another path in a nested loop.
                continue
            legacy_path = self._legacy_failure_iteration_path(activity_name, node_id)
            if legacy_path is None:
                continue
            if legacy_path not in paths.setdefault(node_id, []):
                paths[node_id].append(legacy_path)

        for node_paths in paths.values():
            node_paths.sort()
        return paths

    def _legacy_failure_iteration_path(self, activity_name: str, node_id: str) -> list[int] | None:
        """Recover an unambiguous single-loop index from the stored activity name."""
        loop_owners = [loop_id for loop_id, body in self._loop_bodies.items() if node_id in body]
        if len(loop_owners) != 1:
            # The activity-name counter is global per node, so it cannot recover
            # the outer and inner indices needed for a nested path.
            return None
        prefix, separator, suffix = activity_name.rpartition(LOOP_ITERATION_SEP)
        if separator:
            if LOOP_ITERATION_SEP in prefix or prefix != node_id or not suffix.isdigit():
                return None
            return [int(suffix)]
        return [0]

    def _source_status_for_node(self, node_id: str, graph: WorkflowGraph) -> str | None:
        """Return the source status for this node at its active iteration path."""
        try:
            node = graph.get_node(node_id)
        except KeyError:
            node = None
        if node is None:
            return self._retry_source_statuses.get(node_id)

        temporal_id = self._source_temporal_activity_id(node)
        iteration_path = loop_index_chain(
            node_id, getattr(self, "loop_body_map", {}), getattr(self, "node_control_data", {})
        )
        temporal_path = loop_iteration_path(temporal_id)
        if iteration_path:
            if len(iteration_path) > 1 and temporal_path != iteration_path:
                return None
            temporal_status = getattr(self, "_retry_source_temporal_statuses", {}).get(temporal_id)
            if len(iteration_path) > 1 and temporal_status is None:
                return None
            return (
                temporal_status
                or getattr(self, "_retry_source_activity_name_statuses", {}).get(self._replay_source_name(node_id))
                or self._retry_source_statuses.get(node_id)
            )

        return (
            getattr(self, "_retry_source_temporal_statuses", {}).get(temporal_id)
            or getattr(self, "_retry_source_activity_name_statuses", {}).get(node_id)
            or self._retry_source_statuses.get(node_id)
        )

    def _is_before_selected_failure_iteration(self, node_id: str) -> bool:
        """Whether this row belongs to an earlier enclosing-loop iteration.

        Static retry classification excludes a selected failure and all of its
        downstream nodes. In earlier iterations those rows already ran and must be
        restored, or the retry repeats their side effects before reaching the
        failed iteration.
        """
        node_loop_chain = self._loop_ancestor_chain(node_id)
        if not node_loop_chain:
            return False
        node_path = loop_index_chain(
            node_id, getattr(self, "loop_body_map", {}), getattr(self, "node_control_data", {})
        )
        for target_id, failure_paths in getattr(self, "_retry_selected_failure_paths", {}).items():
            target_loop_chain = self._loop_ancestor_chain(target_id)
            if target_loop_chain[: len(node_loop_chain)] != node_loop_chain:
                continue
            shared_depth = min(len(node_path), len(target_loop_chain))
            if shared_depth == 0:
                continue
            for failure_path in failure_paths:
                if len(failure_path) < shared_depth:
                    continue
                if node_path[:shared_depth] < failure_path[:shared_depth]:
                    return True
        return False

    def _loop_ancestor_chain(self, node_id: str) -> list[str]:
        """Return the enclosing loop IDs for a body node, outermost first."""
        chain: list[str] = []
        seen: set[str] = set()
        loop_body_map = getattr(self, "loop_body_map", {})
        parent = loop_body_map.get(node_id)
        while parent is not None and parent not in seen:
            seen.add(parent)
            chain.append(parent)
            parent = loop_body_map.get(parent)
        chain.reverse()
        return chain

    def _should_replay_loop(self, loop_node_id: str) -> bool:
        """Whether this loop is upstream of a retry point and still in replay mode."""
        if not self.retry_context or loop_node_id in self._retry_live_loop_ids:
            return False
        selected = {strip_iteration_suffix(point) for point in self.retry_context.get("eligible_point_ids", [])}
        if loop_node_id in selected:
            return False
        if loop_node_id in self._retry_replay_candidates:
            return True
        # A body failure's enclosing loop can be removed from the static upstream
        # set by the loop-back edge. It still needs synthetic traversal up to the
        # exact failed occurrence.
        return bool(selected & self._loop_bodies.get(loop_node_id, set()))

    async def _restore_retry_loop_record(self, loop_node_id: str) -> dict[str, Any]:
        """Restore the source loop row once and cache its resolved input/output."""
        cached = self._retry_loop_record_states.get(loop_node_id)
        if cached is not None:
            return cached

        report_activity_id = retry_loop_record_activity_id(loop_node_id)
        source_state = await workflow.execute_activity(
            ActivityName.RETRY_NODE_REPLAY,
            args=[self.retry_context["retry_from_execution_id"], loop_node_id],
            activity_id=f"__internal__fetch_retry_loop_record_{loop_node_id}",
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
        )
        if not isinstance(source_state, dict):
            msg = f"Cannot safely replay loop {loop_node_id}: its source execution record is missing"
            raise ApplicationError(msg, type="RetryLoopStateMissing", non_retryable=True)

        state = dict(source_state)
        selected = {strip_iteration_suffix(point) for point in self.retry_context.get("eligible_point_ids", [])}
        if selected & self._loop_bodies.get(loop_node_id, set()):
            # A failed workflow leaves an unfinished logical loop row to be
            # finalized as SKIPPED. Retrying inside that loop starts the same
            # logical loop again: retain the original start, clear its end, and
            # let real control activities after the failed occurrence finish it.
            state["status"] = ActivityStatus.RUNNING.value
            state["completed_at"] = None
            state["error_details"] = None

        input_data = state.get("input_data")
        if not isinstance(input_data, dict) or "type" not in input_data:
            msg = f"Cannot safely replay loop {loop_node_id}: its resolved source inputs are missing"
            raise ApplicationError(msg, type="RetryLoopInputsMissing", non_retryable=True)

        output_data = state.get("output_data")
        output_data = output_data if isinstance(output_data, dict) else {}
        control_data = state.get("control_data")
        self.node_inputs[loop_node_id] = input_data
        self.resolver.set_namespace(loop_node_id, output_data)
        if isinstance(control_data, dict):
            self.node_control_data[loop_node_id] = control_data

        self._restored_node_timestamps[report_activity_id] = {
            "started_at": state.get("started_at"),
            "completed_at": state.get("completed_at"),
            "status": state.get("status"),
            "error_details": state.get("error_details"),
        }
        self._retry_loop_record_states[loop_node_id] = state
        # Emit the sync event only after the logical row's input, output,
        # control data and source timestamps are queryable from workflow state.
        await workflow.execute_activity(
            ActivityName.RETRY_LOOP_RECORD_SYNC,
            activity_id=report_activity_id,
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
        )
        return state

    def _enter_live_retry_mode_at_selected_node(self, node: ActivityNode) -> bool:
        """Switch enclosing loop controls to live execution at the exact failure occurrence."""
        selected = {strip_iteration_suffix(point) for point in self.retry_context.get("eligible_point_ids", [])}
        if node.id not in selected:
            return False

        node_path = loop_index_chain(node.id, self.loop_body_map, self.node_control_data)
        failure_paths = self._retry_selected_failure_paths.get(node.id, [])
        if failure_paths and not any(path[: len(node_path)] == node_path for path in failure_paths):
            return False
        if not failure_paths and node_path:
            # A nested legacy row has no full path. _replayed_loop_control fails
            # closed before reaching an occurrence it cannot identify.
            return False

        live_loops = self._loop_ancestor_chain(node.id)
        self._retry_live_loop_ids.update(live_loops)
        # Once these controllers hand off, later live loop activities must not
        # make the sync service wait for replay timestamps that will never exist.
        self._retry_replay_candidates.difference_update(live_loops)
        return True

    def _infer_control_node_branch(self, node: ActivityNode, graph: WorkflowGraph) -> str | None:
        """Which output port a control node took in the source run, or None.

        A control node re-evaluates its own condition against the namespace this
        retry has rebuilt, and that namespace is incomplete while sibling branches
        are still restoring. So a restored control node is given the branch the
        source run recorded rather than being asked to decide again.

        The source run already records it implicitly: ``_skip_non_taken_branches``
        marks the untaken branch SKIPPED and cascades, so the branch that has
        activity is the one that ran.

        Only branch-exclusive nodes count. A node reachable from more than one port
        records activity whichever branch fired, so its status says nothing about
        the choice — a graph whose branches merge cannot be inferred, and returns
        None so the caller reruns the node.

        Returns:
            The port name, or None when it is not inferable: fewer than two ports,
            no branch has activity, more than one does, or no port is exclusive.

        """
        if node.type not in _INFERABLE_CONTROL_NODE_TYPES:
            return None

        ports = sorted({edge["from_port"] for edge in graph.get_outgoing_edges(node.id) if edge.get("from_port")})
        if len(ports) < _MIN_BRANCHES_FOR_INFERENCE:
            return None

        # Everything reachable through each port, so exclusivity can be computed by
        # set difference rather than a separate traversal per candidate pair.
        reach = {port: self._walk_from_port(node.id, port, graph) for port in ports}

        taken: list[str] = []
        for port in ports:
            others: set[str] = set()
            for other in ports:
                if other != port:
                    others |= reach[other]
            exclusive = reach[port] - others
            if any(
                self._source_status_for_node(node_id, graph) not in (None, ActivityStatus.SKIPPED.value)
                for node_id in exclusive
            ):
                taken.append(port)

        if len(taken) != 1:
            # No branch ran, or both did. Either way the recorded state does not
            # identify one branch, and guessing would send the retry down the wrong
            # edge.
            return None
        return taken[0]

    @staticmethod
    def _walk_from_port(node_id: str, port: str, graph: WorkflowGraph) -> set[str]:
        """Every node reachable from ``node_id`` through ``port``, exclusive.

        Plain adjacency from the port's immediate successors. A loop body is not
        followed through its owner: a node inside a loop is one execution per
        iteration, so its status cannot say which branch entered it.
        """
        seen: set[str] = set()
        queue = collections.deque(successor.id for successor in graph.get_next_activities_by_port(node_id, port))
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            node = graph.get_node(current)
            if node is not None and node.type == NodeType.LOOP:
                # Stop at a loop: its iterations are per-iteration records and say
                # nothing about which branch reached it.
                continue
            queue.extend(graph.get_successors(current))
        return seen

    @staticmethod
    def _loop_body_node_ids(graph: WorkflowGraph) -> set[str]:
        """Return every node that runs inside a loop body.

        Seeds from each loop node's ``iterate`` successors, then follows plain
        adjacency. Only a multi-output node's edges carry ``from_port``, so the
        walk may filter on it for the seed and must not for the rest of the body:
        doing so stops after the first node and leaves the remainder of the body
        looking like ordinary nodes. Feedback edges (``to_port="iterate"``) are
        stripped when the graph is built, so the walk terminates at the end of the
        body and cannot escape via the loop's ``complete`` port.

        Body nodes stay in the retry region. This helper identifies their loop
        owner so replay can choose the source row for the active iteration instead
        of treating each body node as a single execution.

        Args:
            graph: Workflow graph.

        """
        loop_ids = [node.id for node in graph.get_all_nodes() if node.type == NodeType.LOOP]
        bodies = collect_loop_bodies(
            {node.id: graph.get_successors(node.id) for node in graph.get_all_nodes()},
            {owner: [node.id for node in graph.get_next_activities_by_port(owner, "iterate")] for owner in loop_ids},
        )
        return set().union(*bodies.values()) if bodies else set()

    @staticmethod
    def _walk_downstream(start_node_id: str, graph: WorkflowGraph) -> set[str]:
        """Every node reachable from ``start_node_id``, inclusive."""
        seen: set[str] = set()
        queue = collections.deque([start_node_id])
        while queue:
            node_id = queue.popleft()
            if node_id in seen:
                continue
            seen.add(node_id)
            queue.extend(graph.get_successors(node_id))
        return seen

    async def _maybe_restore_retry_output(self, node: ActivityNode, graph: WorkflowGraph) -> dict[str, Any] | None:
        """Restore this node's source-run outcome instead of executing it.

        Returns the synthetic completion for a node that qualified, or None to fall
        through to normal execution — either because this is not a retry, the node
        may not be skipped, or the source run has no restorable record for it.

        A restored node keeps the status it had in the source run rather than
        arriving as a success: a skipped node stays skipped, and a failure the
        caller did not select stays failed. Reporting either as completed would
        misstate the source run, and a failure reported as a skip would drop the
        reason it failed.
        """
        if not self.retry_context:
            return None
        if not self._should_restore_node(node.id, graph):
            # This node is about to run for real, so it must stop looking like a
            # replay candidate before it completes. The sync service asks the
            # workflow whether a completing activity is one it should expect a
            # replay for, and a candidate that never replays costs it a 5s wait
            # for a timestamp that is never written. Discarding here — at the
            # moment the decision is made, and before the node runs — is what
            # lets the candidate set start out holding every upstream node
            # without paying for the ones that turn out to rerun. A no-op for a
            # node that was never a candidate.
            self._retry_replay_candidates.discard(node.id)
            return None
        return await self._restore_node_state(node, graph)

    def _should_restore_node(self, node_id: str, graph: WorkflowGraph) -> bool:
        """Whether this node's stored output may be injected instead of running it.

        Membership decides it, for every node type. A condition or switch in the
        set is held to the extra test of whether its recorded branch is recoverable;
        if it is not, it re-decides normally. A loop must reach its executor so
        its per-iteration probe can route it; generic restoration would lose that
        routing state. A converge still reruns because restoring it would release
        successors without evaluating its gate.
        """
        if not self.retry_context:
            return False
        if strip_iteration_suffix(node_id) not in self._retry_restorable_nodes(
            graph
        ) and not self._is_before_selected_failure_iteration(node_id):
            return False
        node = graph.get_node(node_id)
        if node is not None and node.type == NodeType.LOOP:
            return False
        if node is not None and node.type in _CONTROL_NODE_TYPES_FOR_RETRY:
            return node.type in _INFERABLE_CONTROL_NODE_TYPES and bool(self._resolved_control_port(node, graph))
        return self._source_status_for_node(node_id, graph) in _RESTORABLE_SOURCE_STATUS_VALUES

    async def _restore_node_state(  # noqa: PLR0911
        self, node: ActivityNode, graph: WorkflowGraph
    ) -> dict[str, Any] | None:
        """Replay this node's recorded outcome from its source run, or None.

        One path for both node kinds. The replay fetch is the same, and so is the
        state it publishes — the recorded input, status and times — so only the
        result differs: a control node routes on the branch the source run took,
        an ordinary node publishes the output it recorded.

        The recorded status and times are kept for the sync service, which is what
        writes the row: without them the sync records the replay activity's own
        successful completion and every restored node would be reported COMPLETED.
        The input goes to ``node_inputs`` (what ``get_activity_input`` reads), so a
        restored node shows the same input on drill-down as one that executed.

        Two differences from the ordinary path are deliberate and kept rather than
        unified. A control node carries no status guard and tolerates a vanished
        record, because it can still be restored from a recorded port; an ordinary
        node cannot, so it skips the replay entirely and raises if the row is gone.

        The replay activity runs under the node's canonical Temporal ID — not an
        ``__internal__`` id — so the normal event-driven sync records it node by
        node, with the same full iteration path used by an executed body node.

        Returns:
            The synthetic completion for a node that qualified, or None to fall
            through to normal execution. A node that never reached a terminal state
            cannot be restored, because there would be nothing to reproduce.

        """
        is_control = node.type in _CONTROL_NODE_TYPES_FOR_RETRY

        # Decided up front rather than after the fetch: the replay runs under the
        # node's own activity id, so the event it emits is consumed as *this node's*
        # execution and marks the row terminal; a real execution afterwards is then
        # refused by the sync service's terminal-status guard, leaving the row
        # showing the replay's output and times. This costs a lookup rather than a
        # query, because ``_prepare_retry`` already read every source status.
        if not is_control and self._source_status_for_node(node.id, graph) not in _RESTORABLE_SOURCE_STATUS_VALUES:
            self._retry_replay_candidates.discard(node.id)
            return None

        # A loop body is one execution per iteration, so the row asked for is the
        # one for the iteration this loop is replaying — not the node's first. The
        # base name is what iteration 0 is stored under.
        source_name = self._replay_source_name(node.id)
        iteration_path = loop_index_chain(
            node.id, getattr(self, "loop_body_map", {}), getattr(self, "node_control_data", {})
        )
        source_temporal_id = self._source_temporal_activity_id(node)
        has_full_iteration_path = loop_iteration_path(source_temporal_id) == iteration_path
        if len(iteration_path) > 1 and not has_full_iteration_path:
            self._retry_replay_candidates.discard(node.id)
            return None

        record = await workflow.execute_activity(
            ActivityName.RETRY_NODE_REPLAY,
            args=[
                self.retry_context.get("retry_from_execution_id"),
                source_name,
                source_temporal_id if has_full_iteration_path else None,
                not iteration_path or len(iteration_path) == 1,
            ],
            activity_id=source_temporal_id,
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
        )
        if not is_control and record is None:
            # The status map said this node was restorable but the row is gone —
            # deleted between _prepare_retry and here. Rare, but the replay event
            # has already been emitted under the node's id and will be persisted
            # as this node's execution, so the real run that follows would be
            # refused by the sync service's terminal-status guard. There is no
            # safe recovery once it has fired: skipping the node would leave it
            # never executed, and letting it run would corrupt its row. Raised so
            # the failure is visible instead of leaving a plausible-looking row
            # that reports the replay's output forever.
            msg = f"source record for retry node {node.id} disappeared between classification and replay"
            raise SafeValueError(msg)

        output = (record or {}).get("output_data") or {}
        source_status = str((record or {}).get("status") or ActivityStatus.COMPLETED.value)
        error_details = (record or {}).get("error_details")
        self.node_inputs[node.id] = (record or {}).get("input_data") or {}
        self._restored_node_statuses[node.id] = source_status
        restored_timestamps = {
            "started_at": (record or {}).get("started_at"),
            "completed_at": (record or {}).get("completed_at"),
            # The source run's own status and times, so the row this node ends up
            # with reports what actually happened rather than the replay's success.
            "status": source_status,
            "error_details": error_details,
        }
        # Iteration-aware sync asks by Temporal ID; retain the base key for older
        # sync workers and non-iterated callers.
        self._restored_node_timestamps[source_temporal_id] = restored_timestamps
        self._restored_node_timestamps[node.id] = restored_timestamps

        if is_control:
            # A control node needs the routing decision, not a payload, and the
            # source row already carries it. The persisted ``control_data`` wins,
            # because the sync layer records the branch the run actually took;
            # inference stays the fallback for runs predating that column and for
            # control data with no ``next_port``. The output is the source run's own
            # and must not be replaced — only the port travels as control data,
            # which is what the scheduler reads to pick the edge.
            stored_control = (record or {}).get("control_data") or {}
            recorded_port = stored_control.get("next_port") if isinstance(stored_control, dict) else None
            port = str(recorded_port) if recorded_port else self._resolved_control_port(node, graph)
            if port is None:
                return None
            workflow.logger.info(
                "Restored control node branch from source run", extra={"node_id": node.id, "port": port}
            )
            return {"output": output, "control": {"next_port": port}}

        # Only a node that did not succeed has output worth keeping: a restored
        # completion publishes its own output through the normal path.
        if source_status != ActivityStatus.COMPLETED.value and output:
            self._restored_node_outputs[node.id] = output

        workflow.logger.info(
            "Replayed retry node state",
            extra={
                "node_id": node.id,
                "source_status": source_status,
                "input_keys": sorted(self.node_inputs[node.id]),
                "output_keys": sorted(output),
            },
        )

        # SKIPPED and FAILED publish the failure namespace and record the node
        # accordingly, so the scheduler treats them as terminal without executing
        # them: a restored skip must not schedule downstream work, and a restored
        # failure must not read as a success.
        if source_status != ActivityStatus.COMPLETED.value:
            return self._restored_terminal_result(node, source_status, output, error_details)

        # A completed approval is the one restored node that must still route.
        # Everything else that is completed publishes a plain completion, leaving
        # the scheduler to follow the node's ordinary successors.
        if node.type == NodeType.APPROVAL:
            return {"output": output, "control": self._restored_approval_control(output)}

        return {"output": output, "control": None}

    def _replay_source_name(self, node_id: str) -> str:
        """Resolve the stored activity name to replay for ``node_id`` on this pass.

        An ordinary node restores under its own id. A loop body restores per
        iteration, so it needs the row for the iteration its loop is replaying —
        which the sync service names ``{node}#iter-{n}`` once the previous row
        reached a terminal status. Iteration 0 keeps the plain node name, so the
        first iteration needs no suffix.
        """
        loop_id = self._enclosing_loop(node_id)
        if loop_id is None:
            return node_id
        active_iterations = cast("dict[str, int]", getattr(self, "_active_loop_iteration", {}))
        index = active_iterations.get(loop_id)
        if index is None:
            path = loop_index_chain(node_id, getattr(self, "loop_body_map", {}), getattr(self, "node_control_data", {}))
            if not path:
                return node_id
            index = path[-1]
        return node_id if index == 0 else f"{node_id}{LOOP_ITERATION_SEP}{index}"

    def _enclosing_loop(self, node_id: str) -> str | None:
        """Find the loop whose body ``node_id`` sits in, or None if it is not a body."""
        loop_bodies = cast("dict[str, set[str]]", getattr(self, "_loop_bodies", {}))
        for loop_id, body in loop_bodies.items():
            if node_id in body:
                return loop_id
        return None

    @staticmethod
    def _restored_approval_control(output: dict[str, Any]) -> dict[str, str] | None:
        """Route a restored approval by the decision the source run recorded.

        A live approval returns ``control: {next_port: decision}`` — the decision
        doubles as the port. Restoring one has to do the same, or
        ``get_next_activities_by_port`` is handed no port and returns *both* the
        approved and the rejected branch, running a human decision twice.

        Only a completed approval routes. A skipped or failed one never reaches
        here: it takes the terminal path, which suppresses successors outright.

        Raises:
            SafeValueError: If a completed approval carries no usable decision.
                That combination cannot arise from a real run — the approval
                activity rejects any other value — so it means the stored output
                is corrupt, and guessing a branch would be worse than stopping.

        """
        decision = output.get("decision")
        if decision not in ("approved", "rejected"):
            msg = f"restored approval has no usable decision to route on: {decision!r}"
            raise SafeValueError(msg)
        return {"next_port": str(decision)}

    def _restored_terminal_result(
        self,
        node: ActivityNode,
        source_status: str,
        output: dict[str, Any],
        error_details: str | None,
    ) -> dict[str, Any]:
        """Publish a restored node that did not succeed, and return its result.

        Mirrors what a live failure publishes — namespace entry, ``failed_nodes`` or
        ``skipped_nodes`` — so the scheduler and the run view see the same shape as
        for a node that genuinely failed or was genuinely skipped.

        This only records the outcome. The completion path reads
        ``_restored_node_statuses`` and decides what to do with it, because a task
        that returns normally is otherwise indistinguishable from one that really
        succeeded — it would republish the namespace as completed and schedule the
        successors of a node that was never run.
        """
        if source_status == ActivityStatus.SKIPPED.value:
            self.skipped_nodes.add(node.id)
            entry: dict[str, Any] = {**output, "status": "skipped"}
        else:
            message = error_details or f"Restored from a source run that ended {source_status}"
            self.failed_nodes[node.id] = message
            entry = {**output, "status": "failed", "error": message}

        self.resolver.set_namespace(node.id, entry)
        return {"output": entry, "control": None}

    def _apply_input_overrides(self, node: ActivityNode, resolved_parameters: dict[str, Any]) -> None:
        """Replace a node's resolved inputs with the retry's user-supplied overrides.

        Applied after ``_resolve_node_parameters`` so the override wins over the
        value the node would otherwise receive, which is the value
        *after* upstream outputs were injected. Mutates in place so the caller's
        copy and ``self.node_inputs`` stay consistent.

        Overrides were already validated fail-closed by the control plane, so
        anything reaching here for this node is a legitimate target. Keys that
        are not parameters of this node are ignored rather than injected: the
        validator guarantees they cannot occur, and treating an unexpected key as
        a new parameter would redefine the workflow for one run.
        """
        overrides = self.retry_context.get("input_parameter_overrides") or {}
        supplied = overrides.get(node.id)
        if not supplied:
            return
        for param_name, value in supplied.items():
            if param_name in resolved_parameters:
                resolved_parameters[param_name] = value
