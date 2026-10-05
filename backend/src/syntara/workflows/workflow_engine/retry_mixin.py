"""Retry-from-failure orchestration, sharing the normal node completion path."""

import collections
from datetime import timedelta
from typing import Any

from temporalio import workflow

from syntara.workflows.utils.loop_body_nodes import collect_loop_bodies
from syntara.workflows.utils.loop_iteration_names import strip_iteration_suffix
from syntara.workflows.workflow_engine.constants import DEFAULT_ACTIVITY_TIMEOUT_SECONDS
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, LoopState, LoopType, NodeType
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
    _restored_nodes: set[str]
    _restored_node_timestamps: dict[str, dict[str, str | None]]
    _resumed_loops: set[str]
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
    def _loop_body_node_ids(graph: WorkflowGraph, loop_id: str | None = None) -> set[str]:
        """Return the nodes that run inside a loop body.

        Seeds from the loop node's ``iterate`` successors, then follows plain
        adjacency. Only a multi-output node's edges carry ``from_port``, so the
        walk may filter on it for the seed and must not for the rest of the body:
        doing so stops after the first node and leaves the remainder of the body
        looking like ordinary nodes. Feedback edges (``to_port="iterate"``) are
        stripped when the graph is built, so the walk terminates at the end of the
        body and cannot escape via the loop's ``complete`` port.

        Args:
            graph: Workflow graph.
            loop_id: Restrict the result to this loop's body. Required when the
                result is attributed to a specific loop, since with several loops
                in one definition the union would let one loop adopt another's
                body. Omit only to exclude bodies wholesale.

        """
        loop_ids = (
            [loop_id]
            if loop_id is not None
            else [node.id for node in graph.get_all_nodes() if node.type == NodeType.LOOP]
        )
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
        return await self._restore_node_output(node)

    def _should_restore_node(self, node_id: str, graph: WorkflowGraph) -> bool:
        """Whether this node's stored output may be injected instead of running it."""
        if not self.retry_context:
            return False
        node = graph.get_node(node_id)
        if node is not None and node.type in _CONTROL_NODE_TYPES:
            return False
        return strip_iteration_suffix(node_id) in self._retry_restorable_nodes(graph)

    async def _restore_node_output(self, node: ActivityNode) -> dict[str, Any] | None:
        """Replay this node from its source run instead of executing it, or None.

        Returns None when the source run has no completed record for the node, so
        the caller falls through to normal execution. A node that never completed
        cannot be skipped, because there would be nothing to inject.

        The replay activity runs under the node's own id — not an
        ``__internal__`` id — so the normal event-driven sync records it
        node-by-node: the sync service maps it to this node, writes its row, and
        emits a per-node WebSocket delta exactly as for an executed node. Both
        halves are republished: the output into the execution namespace, and the
        input into ``node_inputs`` (what ``get_activity_input`` reads), so a
        restored node shows the same input and output on drill-down as one that
        executed. The source timestamps are kept so the sync service can report
        when the work ran rather than the restore time.
        """
        fetched = await workflow.execute_activity(
            ActivityName.RETRY_OUTPUTS,
            args=[self.retry_context.get("retry_from_execution_id"), [node.id]],
            activity_id=node.id,
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
        )
        record = (fetched or {}).get(node.id)
        if record is None:
            return None

        output = record.get("output_data") or {}
        self.node_inputs[node.id] = record.get("input_data") or {}
        self._restored_node_timestamps[node.id] = {
            "started_at": record.get("started_at"),
            "completed_at": record.get("completed_at"),
        }
        workflow.logger.info(
            "Replayed retry node data",
            extra={"node_id": node.id, "input_keys": sorted(self.node_inputs[node.id]), "output_keys": sorted(output)},
        )
        return {"output": output, "control": None}

    async def _maybe_resume_loop(self, node: ActivityNode, graph: WorkflowGraph | None) -> None:
        """Seed a loop's iteration state when a retry re-enters it mid-run.

        A loop that already completed iterations in the source run must not
        restart from zero: its iterations may have external side effects, and the
        loop's aggregated output is assembled from every iteration it has done.
        This fetches the source run's per-iteration state and seeds
        ``loop_state`` and ``loop_iteration_results`` so the loop resumes at the
        failed iteration with the finished iterations already accounted for.

        No-op unless this retry actually re-enters the loop, so a loop running for
        the first time in this run is untouched.
        """
        if not self.retry_context or node.id in self._resumed_loops:
            return
        if graph is None:
            # Only reachable from a caller that omitted the graph; the dispatcher
            # always supplies one. Warn rather than silently restarting the loop
            # from iteration 0, which would repeat the skipped iterations'
            # side effects.
            workflow.logger.warning(
                "Retry cannot resume loop without a graph; restarting from the first iteration",
                extra={"loop_id": node.id},
            )
            return
        eligible = {strip_iteration_suffix(point) for point in self.retry_context.get("eligible_point_ids", [])}
        # Scoped to this loop: with several loops in one definition the union of
        # all bodies would let this loop adopt another's body nodes, resume at an
        # index that belongs to a different loop, and aggregate the wrong results.
        body_ids = sorted(self._loop_body_node_ids(graph, node.id))
        if not eligible.intersection(body_ids):
            return
        self._resumed_loops.add(node.id)

        state = await workflow.execute_activity(
            ActivityName.RETRY_LOOP_STATE,
            args=[self.retry_context.get("retry_from_execution_id"), {node.id: body_ids}],
            activity_id=f"__internal__fetch_retry_loop_state_{node.id}",
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
        )
        resume = (state or {}).get(node.id)
        if not resume:
            return

        self._restored_nodes.update(resume.get("restored_activity_names", []))
        resume_iteration = int(resume.get("resume_iteration", 0))
        iteration_results = resume.get("iteration_results") or {}

        # The loop node has not been dispatched yet on this path, so its state is
        # created from its own parameters first; only the counter and the
        # accumulated results are seeded from the source run.
        if node.id not in self.loop_state:
            loop_type = node.parameters.get("type", LoopType.FOR_EACH)
            self.loop_state[node.id] = self._create_loop_state_for_type(loop_type, node)
        self.loop_state[node.id].current_index = resume_iteration

        seeded = self.loop_iteration_results.setdefault(node.id, {})
        for key, values in iteration_results.items():
            seeded.setdefault(key, []).extend(values)

        workflow.logger.info(
            "Resumed loop from source run",
            extra={
                "loop_id": node.id,
                "resume_iteration": resume_iteration,
                "restored_fields": len(iteration_results),
            },
        )

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
