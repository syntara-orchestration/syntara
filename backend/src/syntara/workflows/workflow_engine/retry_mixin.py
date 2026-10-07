"""Retry-from-failure orchestration, sharing the normal node completion path."""

import collections
from datetime import timedelta
from typing import Any

from temporalio import workflow

from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.utils.loop_body_nodes import collect_loop_bodies
from syntara.workflows.utils.loop_iteration_names import strip_iteration_suffix
from syntara.workflows.workflow_engine.constants import DEFAULT_ACTIVITY_TIMEOUT_SECONDS
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, LoopState, NodeType
from syntara.workflows.workflow_engine.node_settings_resolver import resolve_continue_on_failure

#: Node types that decide routing rather than producing an output. A retry never
#: restores these from a source run: skipping one would strand the graph, so
#: they always execute.
_CONTROL_NODE_TYPES = frozenset(
    {
        NodeType.CONDITION,
        NodeType.SWITCH,
        NodeType.LOOP,
        NodeType.WAIT,
    }
)


class WorkflowRetryMixin:
    """Retry policy and restoration; state is initialized by the workflow."""

    retry_context: dict[str, Any]
    _retry_restorable_cache: set[str] | None
    #: Source-run state for the nodes this retry may replay, fetched once and
    #: cached. ``None`` until first needed, which is what makes the fetch lazy:
    #: a retry whose rerunning steps read no upstream output never pays for it.
    _replay_records: dict[str, dict[str, Any]] | None
    _runtime_settings: dict[str, Any]
    _retry_source_statuses: dict[str, str]
    skipped_nodes: set[str]
    node_inputs: dict[str, dict[str, Any]]
    loop_state: dict[str, LoopState]
    loop_iteration_results: dict[str, dict[str, list[Any]]]

    def _create_loop_state_for_type(self, loop_type: str, node: ActivityNode) -> LoopState: ...  # type: ignore[empty-body]

    async def _prepare_retry(self, graph: WorkflowGraph) -> None:
        """Load source state once and exclude branches not selected for retry."""
        if not self.retry_context:
            return
        self._retry_source_statuses = await workflow.execute_activity(
            ActivityName.RETRY_SOURCE_STATE,
            args=[self.retry_context["retry_from_execution_id"]],
            activity_id="__internal__fetch_retry_source_state",
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
        )
        self._classify_unselected_branches(graph)
        self._replay_records = None

    def _classify_unselected_branches(self, graph: WorkflowGraph) -> None:
        """Skip unselected failures without suppressing shared selected descendants.

        Completed nodes form a boundary: a satisfied converge and its descendants
        retain their results under R6c, even if a different predecessor failed.
        """
        selected = {strip_iteration_suffix(point) for point in self.retry_context.get("eligible_point_ids", [])}
        rerun: set[str] = set()
        for point in selected:
            rerun.update(self._walk_downstream(point, graph))
        for node_id, status in self._retry_source_statuses.items():
            if status != "failed" or node_id in rerun:
                continue
            pending = [node_id]
            seen: set[str] = set()
            while pending:
                current = pending.pop()
                if current in seen or current in rerun or self._retry_source_statuses.get(current) == "completed":
                    continue
                seen.add(current)
                self.skipped_nodes.add(current)
                pending.extend(graph.get_successors(current))

    def _retry_restorable_nodes(self, graph: WorkflowGraph) -> set[str]:
        """Return the base node ids whose stored output this retry can restore.

        The control plane already validated the selection, so this
        only re-derives *which upstream nodes may be skipped* — a node qualifies
        when it is not a retry starting point and nothing downstream of it forced
        it to re-run.

        A node that ran downstream of a ``continue_on_failure`` step is excluded:
        its inputs may depend on the failed node's output, which no longer exists,
        so restoring it would replay it against stale inputs. The global default
        for ``workflow_engine.continue_on_failure`` is False, so this set is
        empty unless an operator opted in per node.
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

        # Nodes forced to re-run: everything downstream of a continue_on_failure
        # step that is itself inside the retried region. Walking from each CoF
        # node in the region, rather than the whole graph, keeps the walk bounded
        # to what this retry can actually affect.
        forced: set[str] = set()
        for node in graph.get_all_nodes():
            if node.id in must_run and resolve_continue_on_failure(node, self._runtime_settings):
                forced |= self._walk_downstream(node.id, graph)

        # Trigger nodes are excluded: the retry re-enters the graph at its first
        # eligible point, and the control plane already re-resolved the trigger
        # input, so there is no source output to restore for one.
        triggers = {node.id for node in graph.get_trigger_nodes()}

        # Control nodes decide routing rather than producing a value to inject,
        # and a loop body is not one node but one execution per iteration. Both
        # are excluded here so the set means what it says, instead of relying on
        # _should_restore_node to filter them again at the point of use.
        control = {node.id for node in graph.get_all_nodes() if node.type in _CONTROL_NODE_TYPES}
        loop_bodies = self._loop_body_node_ids(graph)

        # Everything downstream of a failure point re-executes, so it cannot be
        # restored: a restored downstream node would never re-run to consume the
        # failure point's fresh output, silently discarding the result of the very
        # retry that was asked for.
        downstream: set[str] = set()
        for node_id in must_run:
            downstream |= self._walk_downstream(node_id, graph)

        restorable = (
            {node.id for node in graph.get_all_nodes()}
            - must_run
            - forced
            - triggers
            - control
            - loop_bodies
            - downstream
        )
        self._retry_restorable_cache = restorable
        return restorable

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

        A body node is excluded from restoration because it is not one node but
        one execution per iteration, so a single stored output cannot stand in
        for all of them.

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
        """Restore this node's source-run output instead of executing it.

        Returns the synthetic completion for a node that qualified, or None to
        fall through to normal execution — either because this is not a retry,
        the node may not be skipped, or the source run has no output for it.
        """
        if not self.retry_context or not self._should_restore_node(node.id, graph):
            return None

        records = await self._lazy_replay_records()
        record = records.get(node.id)
        # A record with no output is a node that did not complete. Restoring it
        # would inject nothing and leave downstream expressions unresolved, so it
        # runs for real instead.
        if record is None or record.get("status") != ActivityStatus.COMPLETED.value:
            return None

        output = record.get("output_data") or {}
        self.node_inputs[node.id] = record.get("input_data") or {}
        workflow.logger.info(
            "Restored retry node output from source run",
            extra={"node_id": node.id, "input_keys": sorted(self.node_inputs[node.id]), "output_keys": sorted(output)},
        )
        return {"output": output, "control": None}

    async def _lazy_replay_records(self) -> dict[str, dict[str, Any]]:
        """Fetch every restorable node's source-run state in one call.

        Called at most once per workflow and cached. The alternative shape is one
        activity per node; this asks for the whole set because the classification
        is already known up front, so a single read of the source run's rows
        answers every lookup the run will make.

        Lazy in the sense that nothing is fetched until a node actually needs
        restoring: a retry whose rerunning steps read none of the upstream
        outputs costs no read at all.
        """
        if self._replay_records is not None:
            return self._replay_records

        self._replay_records = {}
        if not self.retry_context:
            return self._replay_records

        source_execution_id = self.retry_context.get("retry_from_execution_id")
        if not source_execution_id:
            return self._replay_records

        records = await workflow.execute_activity(
            ActivityName.RETRY_SOURCE_STATE,
            args=[source_execution_id, True],
            activity_id="__internal__fetch_retry_node_records",
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
        )
        self._replay_records = {
            node_id: record for node_id, record in (records or {}).items() if isinstance(record, dict)
        }
        workflow.logger.info(
            "Fetched source node records for retry replay",
            extra={
                "source_execution_id": source_execution_id,
                "node_count": len(self._replay_records),
                "node_ids": sorted(self._replay_records),
            },
        )
        return self._replay_records

    def _should_restore_node(self, node_id: str, graph: WorkflowGraph) -> bool:
        """Whether this node's stored output may be injected instead of running it."""
        if not self.retry_context:
            return False
        node = graph.get_node(node_id)
        if node is not None and node.type in _CONTROL_NODE_TYPES:
            return False
        return strip_iteration_suffix(node_id) in self._retry_restorable_nodes(graph)

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
