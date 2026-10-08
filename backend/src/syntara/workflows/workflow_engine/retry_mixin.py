"""Retry-from-failure orchestration, sharing the normal node completion path."""

import collections
from datetime import timedelta
from typing import Any

from temporalio import workflow

from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.utils.loop_body_nodes import collect_loop_bodies
from syntara.workflows.utils.loop_iteration_names import strip_iteration_suffix
from syntara.workflows.utils.namespace_resolver import NamespaceResolver
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
        # A converge decides whether it has enough predecessors to run, so skipping
        # it would strand the nodes waiting on it. It is a control node in every
        # sense that matters here, and leaving it out meant one could be restored —
        # which then released its successors without the gate ever being evaluated.
        NodeType.CONVERGE,
    }
)


class WorkflowRetryMixin:
    """Retry policy and restoration; state is initialized by the workflow."""

    retry_context: dict[str, Any]
    _retry_restorable_cache: set[str] | None
    #: Nodes this retry may replay, decided up front in ``_prepare_retry``.
    #: The sync service asks the workflow whether a completing activity is one of
    #: these before waiting on it, so it must be populated before any node runs.
    _retry_replay_candidates: set[str]
    _restored_node_timestamps: dict[str, dict[str, str | None]]
    #: The source status of a node this retry restored, keyed by node id. Read by the
    #: completion path so a restored skip or failure is not republished as a success
    #: and does not have its successors scheduled.
    _restored_node_statuses: dict[str, str]
    #: The output a restored node produced before it failed in the source run,
    #: keyed by node id. Republished by the failure path, so a successor reading it
    #: sees what the source run produced rather than an empty output model.
    _restored_node_outputs: dict[str, dict[str, Any]]
    #: Loops this retry resumes, keyed by loop node id: the iteration to restart at
    #: and the per-iteration results for the iterations below it. Seeded when the
    #: loop first dispatches, so the skipped iterations read as already done.
    _resumed_loop_state: dict[str, dict[str, Any]]
    _runtime_settings: dict[str, Any]
    #: Published by the workflow: where a restored failure is recorded, so it reads
    #: the same as one that genuinely failed in this run.
    failed_nodes: dict[str, str]
    #: The namespace resolver the workflow holds. Typed by the workflow itself, so
    #: this only declares that the mixin needs one; a narrower type here would
    #: override the workflow's own annotation.
    resolver: NamespaceResolver
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
        # Decided here rather than on first use: the sync service consults this set
        # the moment an activity completes, so a node discovered mid-graph would
        # otherwise look like an ordinary execution and never get its source times.
        self._retry_replay_candidates = set(self._retry_restorable_nodes(graph))

    def _classify_unselected_branches(self, graph: WorkflowGraph) -> None:
        """Skip unselected failures without suppressing shared selected descendants.

        Completed nodes form a boundary: a satisfied converge and its descendants
        retain their results under R6c, even if a different predecessor failed.

        A failure the caller did not select is restored as a failure by
        ``_restore_node_output``, from its own recorded error. What this suppresses
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
        # A loop is replayable only when the source run recorded where to resume it.
        # Without a resume point there is nothing to skip, so it stays in the control
        # set and runs from the first iteration exactly as it does today.
        resumable_loops = set(self._resumed_loop_state)
        control -= resumable_loops
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
        if not self.retry_context or not self._should_restore_node(node.id, graph):
            return None
        return await self._restore_node_output(node)

    async def _load_resumed_loop_state(self, graph: WorkflowGraph) -> None:
        """Fetch each loop's resume point once, before any loop dispatches.

        A loop that failed inside its body restarts at the iteration that failed
        rather than at the first, so the iterations below it are treated as already
        done — both their results and the loop's own position. Nothing is fetched
        unless a retry context exists, and a loop with no failed iteration in the
        source run is simply absent from the result.
        """
        self._resumed_loop_state = {}
        if not self.retry_context:
            return

        source_execution_id = self.retry_context.get("retry_from_execution_id")
        loop_ids = [node.id for node in graph.get_all_nodes() if node.type == NodeType.LOOP]
        if not source_execution_id or not loop_ids:
            return

        loops = {loop_id: sorted(self._loop_body_node_ids_for(graph, loop_id)) for loop_id in loop_ids}
        state = await workflow.execute_activity(
            ActivityName.RETRY_LOOP_STATE,
            args=[source_execution_id, {k: v for k, v in loops.items() if v}],
            activity_id="__internal__fetch_retry_loop_state",
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
        )
        self._resumed_loop_state = state or {}
        if self._resumed_loop_state:
            workflow.logger.info(
                "Loaded retry loop resume points",
                extra={"resumes": {k: v.get("resume_iteration") for k, v in self._resumed_loop_state.items()}},
            )

    def _loop_body_node_ids_for(self, graph: WorkflowGraph, loop_id: str) -> set[str]:
        """Body nodes owned by one loop."""
        bodies = collect_loop_bodies(
            {node.id: graph.get_successors(node.id) for node in graph.get_all_nodes()},
            {owner: [n.id for n in graph.get_next_activities_by_port(owner, "iterate")] for owner in [loop_id]},
        )
        return set(bodies.get(loop_id, set()))

    def _seed_resumed_loop(
        self,
        loop_id: str,
        loop_state: LoopState,
        resume_iteration: int,
        iteration_results: dict[str, list[Any]],
    ) -> None:
        """Position a resumed loop and republish the iterations it skips.

        The loop's own ``current_index`` moves to the resume point, so the control
        activity starts there instead of re-running earlier iterations whose side
        effects already happened. The per-iteration results are seeded into
        ``loop_iteration_results`` under the same ``"{node}.{field}"`` keys the
        engine accumulates, so a body node reading ``loop.iteration_results`` sees
        the same ragged lists the original run produced.
        """
        # Both loop state models carry ``current_index``, so the resume point is set
        # directly rather than probed for.
        loop_state.current_index = resume_iteration
        self._resumed_loop_state.setdefault(loop_id, {})["seeded"] = True

        target = self.loop_iteration_results.setdefault(loop_id, {})
        for key, values in (iteration_results or {}).items():
            target.setdefault(key, []).extend(values)

    def _should_restore_node(self, node_id: str, graph: WorkflowGraph) -> bool:
        """Whether this node's stored output may be injected instead of running it."""
        if not self.retry_context:
            return False
        node = graph.get_node(node_id)
        if node is not None and node.type == NodeType.LOOP:
            # A resumable loop is not restored through the payload path at all: it
            # is seeded from its resume point when it dispatches. Anything else —
            # a loop with no resume point, or a loop body node, which is one
            # execution per iteration — stays excluded.
            return False
        if node is not None and node.type in _CONTROL_NODE_TYPES:
            return False
        return strip_iteration_suffix(node_id) in self._retry_restorable_nodes(graph)

    async def _restore_node_output(self, node: ActivityNode) -> dict[str, Any] | None:
        """Replay this node's recorded outcome from its source run, or None.

        Returns None when the source run has no restorable record for the node, so
        the caller falls through to normal execution. A node that never reached a
        terminal state cannot be restored, because there would be nothing to
        reproduce.

        The replay activity runs under the node's own id — not an
        ``__internal__`` id — so the normal event-driven sync records it
        node-by-node: the sync service maps it to this node, writes its row, and
        emits a per-node WebSocket delta exactly as for an executed node. Both
        halves are republished: the output into the execution namespace, and the
        input into ``node_inputs`` (what ``get_activity_input`` reads), so a
        restored node shows the same input and output on drill-down as one that
        executed.

        The recorded status decides what this returns. COMPLETED publishes a normal
        completion, so the scheduler treats the node as done and its successors run.
        SKIPPED and FAILED publish the failure namespace and record the node
        accordingly, so the scheduler treats them as terminal without executing
        them — a restored skip must not schedule downstream work, and a restored
        failure must not read as a success.

        Either way the recorded status and times are kept for the sync service,
        which is what writes the row: without them the sync records the replay
        activity's own successful completion and every restored node would be
        reported as COMPLETED.
        """
        record = await workflow.execute_activity(
            ActivityName.RETRY_NODE_REPLAY,
            args=[self.retry_context.get("retry_from_execution_id"), node.id],
            activity_id=node.id,
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
        )
        if record is None:
            # Nothing to replay, so this node will really execute. Drop it from
            # the candidates: the sync service waits on a candidate's timestamp,
            # and waiting here would stall for the full timeout on a node that
            # is going to report its real execution time anyway.
            self._retry_replay_candidates.discard(node.id)
            return None

        source_status = str(record.get("status") or ActivityStatus.COMPLETED.value)
        output = record.get("output_data") or {}
        error_details = record.get("error_details")
        self.node_inputs[node.id] = record.get("input_data") or {}
        self._restored_node_timestamps[node.id] = {
            "started_at": record.get("started_at"),
            "completed_at": record.get("completed_at"),
            # The status and error travel to the sync service so the row reports
            # what the source run recorded rather than the replay's own success.
            "status": source_status,
            "error_details": error_details,
        }
        self._restored_node_statuses[node.id] = source_status
        if source_status != ActivityStatus.COMPLETED.value and output:
            # Only a node that did not succeed has output worth keeping: a restored
            # completion publishes its own output through the normal path.
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

        if source_status == ActivityStatus.COMPLETED.value:
            return {"output": output, "control": None}

        return self._restored_terminal_result(node, source_status, output, error_details)

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
