"""Retry-from-failure orchestration, sharing the normal node completion path."""

import collections
from datetime import timedelta
from typing import Any

from temporalio import workflow

from syntara.core.exceptions import SafeValueError
from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.utils.loop_body_nodes import collect_loop_bodies
from syntara.workflows.utils.loop_iteration_names import strip_iteration_suffix
from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.activities.retry_node_replay_activity import RESTORABLE_SOURCE_STATUSES
from syntara.workflows.workflow_engine.constants import DEFAULT_ACTIVITY_TIMEOUT_SECONDS
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, LoopState, NodeType

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
        NodeType.LOOP,
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
    #: Nodes this retry may replay, decided up front in ``_prepare_retry``.
    #: The sync service asks the workflow whether a completing activity is one of
    #: these before waiting on it, so it must be populated before any node runs.
    _retry_replay_candidates: set[str]
    _restored_node_timestamps: dict[str, dict[str, str | None]]
    #: The source status of a node this retry restored, keyed by node id. Read by the
    #: completion path so a restored skip or failure is not republished as a success
    #: and does not have its successors scheduled.
    _restored_node_statuses: dict[str, str]
    #: The routing decision each restorable control node's source run recorded,
    #: keyed by node id. Read once during ``_prepare_retry`` so the synchronous
    #: classification paths can honour it without awaiting anything.
    _restored_control_ports: dict[str, str]
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
    _retry_source_statuses: dict[str, str]
    skipped_nodes: set[str]
    node_inputs: dict[str, dict[str, Any]]
    loop_state: dict[str, LoopState]
    loop_iteration_results: dict[str, dict[str, list[Any]]]

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
        # Nodes this retry may replay, and the source state for the ones it did.
        # The sync service consults the candidate set to tell a replayed activity
        # from an ordinary one before waiting on it, so these are filled during
        # _prepare_retry rather than on first use.
        self._retry_replay_candidates: set[str] = set()
        self._restored_node_timestamps: dict[str, dict[str, str | None]] = {}
        self._restored_node_statuses: dict[str, str] = {}
        self._restored_node_outputs: dict[str, dict[str, Any]] = {}
        self._restored_control_ports: dict[str, str] = {}
        self._retry_source_statuses: dict[str, str] = {}

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

        The control plane already validated the selection, so this only re-derives
        *which upstream nodes may be skipped* — a node qualifies when it is not a
        retry starting point, not a trigger or control node, not a loop body, and not
        downstream of a retry point.

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

        # Control nodes decide routing rather than producing a value to inject,
        # and a loop body is not one node but one execution per iteration. Both
        # are excluded here so the set means what it says, instead of relying on
        # _should_restore_node to filter them again at the point of use.
        control = {node.id for node in graph.get_all_nodes() if node.type in _CONTROL_NODE_TYPES_FOR_RETRY}
        loop_bodies = self._loop_body_node_ids(graph)

        # Everything downstream of a failure point re-executes, so it cannot be
        # restored: a restored downstream node would never re-run to consume the
        # failure point's fresh output, silently discarding the result of the very
        # retry that was asked for.
        downstream: set[str] = set()
        for node_id in must_run:
            downstream |= self._walk_downstream(node_id, graph)

        # A control node is normally excluded because it decides routing rather
        # than producing a value. CONDITION and SWITCH are the exception when their
        # branch is inferable: the retry can hand them the branch the source run
        # took, so they need not re-decide against a half-rebuilt namespace. LOOP,
        # WAIT and CONVERGE stay excluded unconditionally.
        control = control - {node.id for node in graph.get_all_nodes() if self._resolved_control_port(node, graph)}

        restorable = (
            {node.id for node in graph.get_all_nodes()} - must_run - triggers - control - loop_bodies - downstream
        )
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
        recorded = self._restored_control_ports.get(node.id)
        if recorded:
            return str(recorded)
        return self._infer_control_node_branch(node, graph)

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
                self._retry_source_statuses.get(node_id) not in (None, ActivityStatus.SKIPPED.value)
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
        if node.type in _INFERABLE_CONTROL_NODE_TYPES:
            return await self._restored_control_result(node, graph)
        return await self._restore_node_output(node)

    def _should_restore_node(self, node_id: str, graph: WorkflowGraph) -> bool:
        """Whether this node's stored output may be injected instead of running it."""
        if not self.retry_context:
            return False
        node = graph.get_node(node_id)
        if node is not None and node.type in _CONTROL_NODE_TYPES_FOR_RETRY:
            # A condition or switch may still be restored when the branch the
            # source run took is recoverable — see _infer_control_node_branch.
            if node.type in _INFERABLE_CONTROL_NODE_TYPES and self._resolved_control_port(node, graph):
                return strip_iteration_suffix(node_id) in self._retry_restorable_nodes(graph)
            return False
        return strip_iteration_suffix(node_id) in self._retry_restorable_nodes(graph)

    async def _restored_control_result(self, node: ActivityNode, graph: WorkflowGraph) -> dict[str, Any] | None:
        """Restore a condition or switch by replaying the branch the source run took.

        No payload and no fetch: what a control node needs is the routing decision,
        and that is already recorded by the branch's own node statuses. The branch is
        published into ``node_control_data`` so ``_determine_output_port`` follows
        the same edge, and the node counts as completed so the scheduler advances.

        Returns None when the branch cannot be inferred, so the caller falls through
        to real execution — which re-evaluates the condition rather than assuming one.
        """
        # The source run's own row is read first, because it answers both questions.
        # Its ``control_data`` carries the routing decision the sync layer persisted,
        # so for any run recorded since that landed the port is read directly rather
        # than re-derived from branch statuses. Inference stays as the fallback for
        # runs that predate the column — and for any control data that carries no
        # ``next_port``.
        record = await workflow.execute_activity(
            ActivityName.RETRY_NODE_REPLAY,
            args=[self.retry_context.get("retry_from_execution_id"), node.id],
            activity_id=node.id,
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
        )
        source_output = (record or {}).get("output_data") or {}
        source_status = str((record or {}).get("status") or ActivityStatus.COMPLETED.value)
        stored_control = (record or {}).get("control_data") or {}
        recorded_port = stored_control.get("next_port") if isinstance(stored_control, dict) else None

        port = str(recorded_port) if recorded_port else self._resolved_control_port(node, graph)
        if port is None:
            return None

        self.node_inputs[node.id] = (record or {}).get("input_data") or {}
        self._restored_node_statuses[node.id] = source_status
        self._restored_node_timestamps[node.id] = {
            "started_at": (record or {}).get("started_at"),
            "completed_at": (record or {}).get("completed_at"),
            # The source run's own status and times, so the row this node ends up
            # with reports what actually happened rather than the replay's success.
            "status": source_status,
            "error_details": (record or {}).get("error_details"),
        }

        workflow.logger.info("Restored control node branch from source run", extra={"node_id": node.id, "port": port})
        # The inferred port travels as control data, which is what the scheduler
        # reads; the output is the source run's own and must not be replaced.
        return {"output": source_output, "control": {"next_port": port}}

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

        The replay is not scheduled at all when the source run has no restorable
        record for this node. It runs under the node's own activity id, so the
        event it emits is consumed as *this node's* execution and marks the row
        terminal; a real execution afterwards is then refused by the sync
        service's terminal-status guard, leaving the row showing the replay's
        output and times instead of the real run's. Deciding up front costs
        nothing: ``_prepare_retry`` already read every source status, so this is
        a lookup rather than a query, and it saves an activity and a history
        event for every node that was never replayable.
        """
        if self._retry_source_statuses.get(node.id) not in _RESTORABLE_SOURCE_STATUS_VALUES:
            self._retry_replay_candidates.discard(node.id)
            return None

        record = await workflow.execute_activity(
            ActivityName.RETRY_NODE_REPLAY,
            args=[self.retry_context.get("retry_from_execution_id"), node.id],
            activity_id=node.id,
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
        )
        if record is None:
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

        if source_status != ActivityStatus.COMPLETED.value:
            return self._restored_terminal_result(node, source_status, output, error_details)

        # A completed approval is the one restored node that must still route.
        # Everything else that is completed publishes a plain completion, leaving
        # the scheduler to follow the node's ordinary successors.
        if node.type == NodeType.APPROVAL:
            return {"output": output, "control": self._restored_approval_control(output)}

        return {"output": output, "control": None}

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
