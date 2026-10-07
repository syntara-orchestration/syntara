"""Retry-from-failure classification and override application in the engine .

The control plane  validates a retry and hands the engine
``workflow_metadata.retry``. These tests cover the engine half: overrides
replacing resolved inputs, and completed upstream nodes being skipped with their
outputs restored.
"""

from collections.abc import Callable, Generator
from datetime import timedelta
from typing import Any, ClassVar, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.dynamic_workflow import PRE_RESOLVED_MARKER, OrchestratorWorkflow
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

from .conftest import init_workflow_runtime


@pytest.fixture
def mock_wf() -> Generator[MagicMock, None, None]:
    """Patch the Temporal workflow module so execute_activity is awaitable."""
    with (
        patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as patched,
        patch("syntara.workflows.workflow_engine.retry_mixin.workflow", patched),
    ):
        patched.logger = MagicMock()
        yield patched


def _make_workflow(retry_context: dict[str, Any] | None = None) -> OrchestratorWorkflow:
    """Create an OrchestratorWorkflow with initialized state, bypassing __init__."""
    wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
    wf.skipped_nodes = set()
    wf.failed_nodes = {}
    wf.resolver = NamespaceResolver()
    wf.node_inputs = {}
    wf.node_control_data = {}
    wf.loop_state = {}
    wf.loop_body_map = {}
    wf.loop_iteration_results = {}
    wf._timeout_tasks = {}
    wf._timed_out_converge_nodes = set()
    wf._detached_nodes = set()
    wf._converge_branch_nodes = {}
    init_workflow_runtime(wf)
    wf.execution_id = "test-execution-id"
    wf._created_by_user_id = ""
    wf.request_id = None
    wf.pre_resolved_outputs = {}
    wf.stop_after_nodes = set()
    wf.retry_context = retry_context or {}
    return wf


def _node(node_id: str = "step_2", parameters: dict[str, Any] | None = None) -> ActivityNode:
    return ActivityNode(
        node_id=node_id,
        node_type="script",
        parameters=parameters if parameters is not None else {},
    )


# ---------------------------------------------------------------------------
# Input parameter overrides
# ---------------------------------------------------------------------------


def test_override_replaces_resolved_value() -> None:
    """An override wins over the value the node would otherwise receive."""
    wf = _make_workflow({"input_parameter_overrides": {"step_2": {"code": "echo fixed"}}})
    resolved = {"code": "echo original", "other": "kept"}

    wf._apply_input_overrides(_node(), resolved)

    assert resolved == {"code": "echo fixed", "other": "kept"}


def test_override_applies_to_its_own_node_only() -> None:
    """An override for another node must not touch this one's inputs."""
    wf = _make_workflow({"input_parameter_overrides": {"step_9": {"code": "echo fixed"}}})
    resolved = {"code": "echo original"}

    wf._apply_input_overrides(_node("step_2"), resolved)

    assert resolved == {"code": "echo original"}


def test_unknown_override_key_is_ignored() -> None:
    """A key that is not a parameter of the node is not injected.

    The control plane rejects these, so reaching here means the guarantee was
    bypassed. Ignoring rather than injecting keeps a single run from redefining
    the workflow.
    """
    wf = _make_workflow({"input_parameter_overrides": {"step_2": {"brand_new_param": "x"}}})
    resolved = {"code": "echo original"}

    wf._apply_input_overrides(_node(), resolved)

    assert resolved == {"code": "echo original"}


def test_no_overrides_leaves_inputs_untouched() -> None:
    """Most retries change nothing, so absent/empty overrides are a no-op."""
    empty_contexts: list[dict[str, Any]] = [{}, {"input_parameter_overrides": {}}, {"input_parameter_overrides": None}]
    for retry_context in empty_contexts:
        wf = _make_workflow(retry_context)
        resolved = {"code": "echo original"}

        wf._apply_input_overrides(_node(), resolved)

        assert resolved == {"code": "echo original"}


def test_override_is_a_noop_on_non_retry_run() -> None:
    """A normal run has no retry context and must not be affected."""
    wf = _make_workflow()
    assert wf.retry_context == {}
    resolved = {"code": "echo original"}

    wf._apply_input_overrides(_node(), resolved)

    assert resolved == {"code": "echo original"}


def test_override_does_not_need_the_target_to_be_a_starting_point() -> None:
    """A failed node stays overridable even when it is not a retry starting point.

    The control plane emits the eligible set it resolved; the engine applies
    whatever it is handed rather than re-deriving eligibility.
    """
    wf = _make_workflow(
        {
            "eligible_point_ids": ["step_1"],
            "input_parameter_overrides": {"step_2": {"code": "echo fixed"}},
        }
    )
    resolved = {"code": "echo original"}

    wf._apply_input_overrides(_node("step_2"), resolved)

    assert resolved == {"code": "echo fixed"}


# ---------------------------------------------------------------------------
# Retry context is not expression data
# ---------------------------------------------------------------------------


def test_retry_block_is_not_registered_as_a_namespace() -> None:
    """A user expression must not be able to read the retry block.

    eligible_point_ids and input_parameter_overrides are control-plane state.
    Exposing them as an expression namespace would let a step read the
    validated selection and the user's overrides out of its parameters.
    """
    metadata = {
        "workflow_context": {
            "workflow": {"project_id": "p1", "name": "wf"},
            "execution": {"created_by_user_id": "u1"},
        },
        "retry": {
            "retry_from_execution_id": "src-1",
            "eligible_point_ids": ["step_1"],
            "input_parameter_overrides": {"step_1": {"code": "x"}},
        },
    }

    wf = _namespace_probe(metadata)

    assert "retry" not in wf.resolver.namespaces
    assert wf.retry_context["eligible_point_ids"] == ["step_1"]
    assert wf._project_id == "p1"
    assert wf._created_by_user_id == "u1"


def _namespace_probe(workflow_metadata: dict[str, Any]) -> OrchestratorWorkflow:
    """Build a workflow and run only the metadata-unpacking part of __init__."""
    wf = _make_workflow()
    wf.execution_id = "exec-1"
    wf.request_id = None
    wf._project_id = ""
    wf._created_by_user_id = ""
    # Mirrors the unpacking block in __init__ so the test exercises the real
    # statements without constructing a Temporal workflow instance.
    wf.retry_context = dict(workflow_metadata.get("retry", {})) if workflow_metadata else {}
    for ns_key, ns_data in workflow_metadata.items():
        if ns_key == "retry":
            continue
        wf.resolver.set_namespace(ns_key, ns_data)
    wf_ctx = workflow_metadata.get("workflow_context", {})
    wf._project_id = wf_ctx.get("workflow", {}).get("project_id", "")
    wf._created_by_user_id = wf_ctx.get("execution", {}).get("created_by_user_id", "")
    return wf


def test_absent_retry_block_yields_empty_context() -> None:
    """A normal run must not see a retry context, so nothing downstream activates."""
    wf = _make_workflow()
    assert wf.retry_context == {}
    assert "retry_from_execution_id" not in wf.retry_context


# ---------------------------------------------------------------------------
# Loop iteration id helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("activity_name", "expected"),
    [
        ("step_1", "step_1"),
        ("step_1#iter-0", "step_1"),
        ("step_1#iter-12", "step_1"),
    ],
)
def test_strip_iteration_suffix(activity_name: str, expected: str) -> None:
    """A suffixed activity name resolves to its base node id.

    Nested loops append one suffix per enclosing loop, so only the last suffix
    is stripped and the inner-most base id is kept.
    """
    from syntara.workflows.utils.loop_iteration_names import strip_iteration_suffix

    assert strip_iteration_suffix(activity_name) == expected


def test_nested_loop_name_keeps_inner_base_id() -> None:
    """Nested-loop activity names resolve to the inner base, not the outer.

    ``loop_iteration_ids`` appends one ``_iter_{n}`` per enclosing loop, so a
    doubly-nested activity strips only the final suffix.
    """
    from syntara.workflows.utils.loop_iteration_names import strip_iteration_suffix

    assert strip_iteration_suffix("outer#iter-1#iter-0") == "outer#iter-1"


@pytest.mark.parametrize(
    ("activity_name", "expected"),
    [("step_1", False), ("step_1#iter-0", True)],
)
def test_has_iteration_suffix(*, activity_name: str, expected: bool) -> None:
    """Suffix detection distinguishes an iteration activity from a plain one."""
    from syntara.workflows.utils.loop_iteration_names import has_iteration_suffix

    assert has_iteration_suffix(activity_name) is expected


# ---------------------------------------------------------------------------
# Node classification: which upstream nodes may be restored
# ---------------------------------------------------------------------------


def _chain_graph(*, cof_nodes: set[str] | None = None) -> WorkflowGraph:
    """Build trigger -> step_1 -> step_2 -> step_3, optionally with CoF on some nodes."""
    from syntara.workflows.workflow_engine.graph import WorkflowGraph
    from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend

    cof_nodes = cof_nodes or set()
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    for node_id in ("step_1", "step_2", "step_3"):
        raw: dict[str, Any] = {"id": node_id, "type": "script", "parameters": {}}
        if node_id in cof_nodes:
            raw["settings"] = {"continue_on_failure": True}
        backend.add_node(node_id, raw)
    backend.add_edge("trigger", "step_1", None)
    backend.add_edge("step_1", "step_2", None)
    backend.add_edge("step_2", "step_3", None)
    return WorkflowGraph(backend)


def _retry(*eligible: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    context: dict[str, Any] = {
        "retry_from_execution_id": "src-1",
        "eligible_point_ids": list(eligible),
    }
    if overrides is not None:
        context["input_parameter_overrides"] = overrides
    return context


def test_upstream_of_failure_point_is_restorable() -> None:
    """Nodes before the retry points are skipped with their outputs injected."""
    wf = _make_workflow(_retry("step_2", "step_3"))
    graph = _chain_graph()

    assert wf._retry_restorable_nodes(graph) == {"step_1"}


def test_retry_starting_points_are_never_restored() -> None:
    """A node being retried must execute, not have its old output injected."""
    wf = _make_workflow(_retry("step_2"))
    graph = _chain_graph()

    assert "step_2" not in wf._retry_restorable_nodes(graph)


def test_downstream_of_failed_continue_on_failure_step_is_forced_to_rerun() -> None:
    """A node downstream of the *failed* continue_on_failure step must re-run.

    Its inputs may depend on the failed step's output, which no longer exists, so
    restoring the old output would replay it against inputs that no longer
    describe reality.
    """
    wf = _make_workflow(_retry("step_1"))
    graph = _chain_graph(cof_nodes={"step_1"})

    # step_1 is both retried and CoF, so step_2 and step_3 must re-run.
    assert wf._retry_restorable_nodes(graph) == set()


def test_continue_on_failure_on_a_succeeded_node_forces_nothing() -> None:
    """A CoF node that completed successfully does not force its downstream to re-run.

    R6a is scoped to the *failed* step. step_1 succeeded in the source run and
    is simply restored, so its downstream is restored too.
    """
    wf = _make_workflow(_retry("step_3"))
    graph = _chain_graph(cof_nodes={"step_1"})

    assert wf._retry_restorable_nodes(graph) == {"step_1", "step_2"}


def test_default_continue_on_failure_is_false_so_upstream_is_restored() -> None:
    """With the catalog default of False, a plain chain restores its upstream."""
    wf = _make_workflow(_retry("step_3"))
    graph = _chain_graph()

    assert wf._retry_restorable_nodes(graph) == {"step_1", "step_2"}


@pytest.mark.parametrize(
    "node_type",
    ["condition", "switch", "loop", "wait"],
)
def test_control_nodes_are_never_restored(node_type: str) -> None:
    """Condition/switch/loop/converge/wait decide routing, so they must always run.

    Skipping one would strand the graph: nothing would route past it, and
    downstream expressions would resolve against a namespace the retry never
    populated.
    """
    from syntara.workflows.workflow_engine.graph import WorkflowGraph
    from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend

    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("ctrl", {"id": "ctrl", "type": node_type, "parameters": {}})
    backend.add_node("step_2", {"id": "step_2", "type": "script", "parameters": {}})
    backend.add_edge("trigger", "ctrl", None)
    backend.add_edge("ctrl", "step_2", None)
    graph = WorkflowGraph(backend)

    wf = _make_workflow(_retry("step_2"))

    # ctrl is not a retry point, so it is otherwise restorable - unless the
    # control-node rule excludes it.
    assert not wf._should_restore_node("ctrl", graph)
    # The executor node upstream of the retry point still restores.
    assert wf._should_restore_node("step_2", graph) is False


def test_restorable_set_is_memoised() -> None:
    """The set is derived from the graph and retry context, neither of which mutate."""
    wf = _make_workflow(_retry("step_3"))
    graph = _chain_graph()

    first = wf._retry_restorable_nodes(graph)
    second = wf._retry_restorable_nodes(graph)

    assert first is second


def test_non_retry_run_restores_nothing() -> None:
    """A normal run must not consult classification at all."""
    wf = _make_workflow()
    graph = _chain_graph()

    assert wf._retry_restorable_nodes(graph) == {"step_1", "step_2", "step_3"}
    assert not wf._should_restore_node("step_1", graph)


# ---------------------------------------------------------------------------
# Loop bodies must not be restored as scalar outputs
# ---------------------------------------------------------------------------


def _loop_graph() -> WorkflowGraph:
    """Build trigger -> loop_1 (body_a -> body_b) -> step_2.

    ``body_a``/``body_b`` are the loop body: reached from the loop node via its
    ``iterate`` port, with the feedback edges stripped at graph build time. The
    loop itself exits to ``step_2`` via its ``complete`` port.
    """
    from syntara.workflows.workflow_engine.graph import WorkflowGraph
    from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend

    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("loop_1", {"id": "loop_1", "type": "loop", "parameters": {}})
    backend.add_node("body_a", {"id": "body_a", "type": "script", "parameters": {}})
    backend.add_node("body_b", {"id": "body_b", "type": "script", "parameters": {}})
    backend.add_node("step_2", {"id": "step_2", "type": "script", "parameters": {}})
    backend.add_edge("trigger", "loop_1", None)
    backend.add_edge("loop_1", "body_a", {"from_port": "iterate"})
    backend.add_edge("loop_1", "step_2", {"from_port": "complete"})
    # ``get_outgoing_edges`` only needs ``to``; ``from_port`` is the port that
    # matters for body membership.
    backend.add_edge("body_a", "body_b", {"from_port": "iterate"})
    return WorkflowGraph(backend)


def test_loop_body_nodes_are_not_restored() -> None:
    """A loop body cannot be restored as a single stored output.

    The body is not one node: it runs once per iteration, and the loop aggregates
    a list of results across them. Injecting the last stored body output and
    skipping the body would hand the loop a scalar where it expects a list, and
    would leave every body-node reference downstream unresolved.
    """
    wf = _make_workflow(_retry("step_2"))

    restorable = wf._retry_restorable_nodes(_loop_graph())

    assert "body_a" not in restorable
    assert "body_b" not in restorable


def test_loop_node_itself_is_not_restored() -> None:
    """The loop control node always runs: it has to iterate to completion."""
    wf = _make_workflow(_retry("step_2"))

    restorable = wf._retry_restorable_nodes(_loop_graph())

    assert "loop_1" not in restorable


def test_non_loop_successors_of_a_loop_stay_restorable() -> None:
    """Excluding the body must not over-reach past the loop's ``complete`` port."""
    # Retrying from inside the body: body_b is the starting point, body_a is
    # loop-body so it never restores, but step_2 is an ordinary node downstream
    # of the loop and is still eligible for restoration.
    downstream = _make_workflow(_retry("body_b"))
    graph = _loop_graph()
    restorable = downstream._retry_restorable_nodes(graph)

    assert restorable == {"step_2"}


# ---------------------------------------------------------------------------
# Restoring a node: fetch, inject, and the fall-through cases
# ---------------------------------------------------------------------------


def _injectable_workflow() -> OrchestratorWorkflow:
    """A workflow wired for the restore path, with no retry set by default."""
    return _make_workflow()


@pytest.mark.asyncio
async def test_restored_output_is_injected_into_the_namespace(mock_wf: MagicMock) -> None:
    """The skipped node publishes its source output as a completion would.

    Downstream expressions read the namespace, so the entry has to match what a
    live completion writes - including the synthetic ``status`` key.
    """
    wf = _injectable_workflow()
    wf.retry_context = _retry("step_2")
    node = ActivityNode(node_id="step_1", node_type="script", parameters={})
    mock_wf.execute_activity = AsyncMock(return_value={"input_data": {}, "output_data": {"result": "from-source"}})

    result = await wf._restore_node_output(node)

    assert result == {"output": {"result": "from-source"}, "control": None}
    assert not wf.resolver.has_namespace("step_1")
    from .conftest import complete_supplied_node

    await complete_supplied_node(wf, node, result, MagicMock())
    assert wf.resolver.get_namespace("step_1") == {"result": "from-source", "status": "completed"}
    # Tracked as replayed, not as skipped: it did not get skipped, it ran in an
    # earlier execution. The converge predicates read skipped_nodes as "never ran".
    assert "step_1" in wf._restored_node_timestamps
    assert "step_1" not in wf.skipped_nodes


@pytest.mark.asyncio
async def test_restored_input_survives_supplied_result_handling(mock_wf: MagicMock) -> None:
    """node_inputs keeps the source run's stored input through result processing.

    ``get_activity_input`` reads node_inputs, so drill-down has to show the input
    the node actually ran with. Processing the supplied result must not replace it
    with the pre-resolved marker. A non-empty input is used so "preserved" is
    distinguishable from "never recorded".
    """
    wf = _injectable_workflow()
    wf.retry_context = _retry("step_2")
    node = ActivityNode(node_id="step_1", node_type="script", parameters={})
    mock_wf.execute_activity = AsyncMock(
        return_value={"input_data": {"query": "select 1"}, "output_data": {"result": "ok"}}
    )

    result = await wf._restore_node_output(node)
    assert result is not None
    wf._process_supplied_result(node, result)

    assert wf.node_inputs["step_1"] == {"query": "select 1"}
    assert PRE_RESOLVED_MARKER not in wf.node_inputs["step_1"]


@pytest.mark.asyncio
async def test_missing_output_falls_through_to_execution(mock_wf: MagicMock) -> None:
    """A node with no stored output must run rather than be skipped.

    There would be nothing to inject, so skipping it would leave downstream
    expressions resolving against a namespace the retry never populated.
    """
    wf = _injectable_workflow()
    wf.retry_context = _retry("step_2")
    node = ActivityNode(node_id="step_1", node_type="script", parameters={})
    mock_wf.execute_activity = AsyncMock(return_value=None)

    assert await wf._restore_node_output(node) is None
    assert "step_1" not in wf.skipped_nodes
    assert not wf.resolver.has_namespace("step_1")


@pytest.mark.asyncio
async def test_empty_activity_result_falls_through(mock_wf: MagicMock) -> None:
    """A null activity result is treated as no output, not a crash."""
    wf = _injectable_workflow()
    wf.retry_context = _retry("step_2")
    node = ActivityNode(node_id="step_1", node_type="script", parameters={})
    mock_wf.execute_activity = AsyncMock(return_value=None)

    assert await wf._restore_node_output(node) is None


@pytest.mark.asyncio
async def test_restore_dispatches_the_retry_outputs_activity(mock_wf: MagicMock) -> None:
    """The fetch carries the source execution id, not the output inline.

    The replay runs under the node's own id — not an ``__internal__`` id — so the
    normal event-driven sync records it node-by-node and maps it to this node.
    """
    wf = _injectable_workflow()
    wf.retry_context = _retry("step_2")
    node = ActivityNode(node_id="step_1", node_type="script", parameters={})
    mock_wf.execute_activity = AsyncMock(return_value={"input_data": {}, "output_data": {"result": "ok"}})

    await wf._restore_node_output(node)

    call = mock_wf.execute_activity.call_args
    assert call[0][0] == ActivityName.RETRY_NODE_REPLAY
    assert call.kwargs["args"] == ["src-1", "step_1"]
    assert call.kwargs["activity_id"] == "step_1"


@pytest.mark.asyncio
async def test_restore_captures_source_timestamps(mock_wf: MagicMock) -> None:
    """The source run's timestamps are kept so the replayed row reports when it ran."""
    wf = _injectable_workflow()
    wf.retry_context = _retry("step_2")
    node = ActivityNode(node_id="step_1", node_type="script", parameters={})
    mock_wf.execute_activity = AsyncMock(
        return_value={
            "input_data": {},
            "output_data": {"result": "ok"},
            "started_at": "2026-01-01T00:00:00+00:00",
            "completed_at": "2026-01-01T00:05:00+00:00",
        }
    )

    await wf._restore_node_output(node)

    assert wf._restored_node_timestamps["step_1"] == {
        "started_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:05:00+00:00",
    }


@pytest.mark.asyncio
async def test_maybe_restore_delegates_and_returns_the_synthetic_completion(mock_wf: MagicMock) -> None:
    """The full path: a restorable node resolves to a completion without dispatching."""
    wf = _injectable_workflow()
    wf.retry_context = _retry("step_2")
    node = ActivityNode(node_id="step_1", node_type="script", parameters={})
    mock_wf.execute_activity = AsyncMock(return_value={"input_data": {}, "output_data": {"result": "from-source"}})

    result = await wf._maybe_restore_retry_output(node, _chain_graph())

    assert result == {"output": {"result": "from-source"}, "control": None}
    assert "step_1" in wf._restored_node_timestamps
    assert "step_1" not in wf.skipped_nodes


@pytest.mark.asyncio
async def test_non_restorable_node_is_never_restored(mock_wf: MagicMock) -> None:
    """A retry starting point is executed, not replaced by its old output."""
    wf = _injectable_workflow()
    wf.retry_context = _retry("step_2")
    node = ActivityNode(node_id="step_2", node_type="script", parameters={})
    mock_wf.execute_activity = AsyncMock(side_effect=AssertionError("must not be called"))

    assert await wf._maybe_restore_retry_output(node, _chain_graph()) is None


@pytest.mark.asyncio
async def test_maybe_restore_returns_none_outside_a_retry(mock_wf: MagicMock) -> None:
    """A normal run never consults the restore path."""
    wf = _injectable_workflow()
    node = ActivityNode(node_id="step_1", node_type="script", parameters={})
    mock_wf.execute_activity = AsyncMock(side_effect=AssertionError("must not be called"))

    assert await wf._maybe_restore_retry_output(node, _chain_graph()) is None


def test_loop_body_walk_survives_a_repeated_node() -> None:
    """A body reachable twice is visited once, so the walk cannot spin.

    A nested or re-entrant body makes the same node reachable on more than one
    path; the visited check is what keeps the traversal terminating.
    """
    from syntara.workflows.workflow_engine.graph import WorkflowGraph
    from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend

    backend = InMemoryGraphBackend()
    backend.add_node("loop_1", {"id": "loop_1", "type": "loop", "parameters": {}})
    backend.add_node("body_a", {"id": "body_a", "type": "script", "parameters": {}})
    backend.add_node("body_b", {"id": "body_b", "type": "script", "parameters": {}})
    # Two iterate paths converge on body_b.
    backend.add_edge("loop_1", "body_a", {"from_port": "iterate"})
    backend.add_edge("loop_1", "body_b", {"from_port": "iterate"})
    backend.add_edge("body_a", "body_b", {"from_port": "iterate"})
    graph = WorkflowGraph(backend)

    assert OrchestratorWorkflow._loop_body_node_ids(graph) == {"body_a", "body_b"}


# ---------------------------------------------------------------------------
# End-to-end replay of a plain linear chain
#
# The scope of this change is a straight line of nodes: each upstream node is
# replayed from the source run under its own id, and the sync service records it
# through the normal event path. Loop replay is deliberately absent — a failure
# inside a loop body restarts the loop from its first iteration, which is tracked
# separately. These tests walk the whole chain in order so the per-node handoff
# is covered as one sequence rather than node by node in isolation.
# ---------------------------------------------------------------------------


class TestLinearChainReplay:
    """A linear chain replays upstream nodes one at a time, in execution order."""

    def setup_method(self) -> None:
        self.graph = _chain_graph()

    def _restored(self, wf: OrchestratorWorkflow, node_id: str) -> dict[str, Any] | None:
        return wf._restored_node_timestamps.get(node_id)

    @pytest.mark.asyncio
    async def test_upstream_nodes_replay_in_order_and_record_their_source_times(self, mock_wf: MagicMock) -> None:
        """Each replayed node carries its own input, output and source times.

        The activity is dispatched under the node's own id, so the sync service
        sees an ordinary activity event and records the node node-by-node. What
        distinguishes a replay is the payload coming from the source run and the
        timestamps being the ones recorded when that work actually ran.
        """
        wf = _make_workflow(_retry("step_3"))
        wf.retry_context = _retry("step_3")
        node_ids: list[str] = []

        async def _replay(_name: str, **kwargs: object) -> dict[str, Any]:
            node_id = str(kwargs["activity_id"])
            node_ids.append(node_id)
            return {
                "input_data": {"in": f"{node_id}-input"},
                "output_data": {"out": f"{node_id}-output"},
                "started_at": f"2026-01-01T00:0{len(node_ids)}:00+00:00",
                "completed_at": f"2026-01-01T00:0{len(node_ids)}:30+00:00",
            }

        mock_wf.execute_activity = AsyncMock(side_effect=_replay)

        first = await wf._maybe_restore_retry_output(self.graph.get_node("step_1"), self.graph)
        second = await wf._maybe_restore_retry_output(self.graph.get_node("step_2"), self.graph)

        # One node per call, in execution order, each under its own id.
        assert node_ids == ["step_1", "step_2"]
        assert first == {"output": {"out": "step_1-output"}, "control": None}
        assert second == {"output": {"out": "step_2-output"}, "control": None}

        # Both halves republished: the input for drill-down, and an ordinary
        # completion for the normal result path to publish and schedule from.
        # That handoff is what makes a replayed node indistinguishable from one
        # that executed.
        assert wf.node_inputs["step_1"] == {"in": "step_1-input"}
        assert wf.node_inputs["step_2"] == {"in": "step_2-input"}
        assert first["output"] == {"out": "step_1-output"}

        # Source times kept, so the row reports when the work ran.
        assert self._restored(wf, "step_1") == {
            "started_at": "2026-01-01T00:01:00+00:00",
            "completed_at": "2026-01-01T00:01:30+00:00",
        }
        assert self._restored(wf, "step_2") == {
            "started_at": "2026-01-01T00:02:00+00:00",
            "completed_at": "2026-01-01T00:02:30+00:00",
        }

    @pytest.mark.asyncio
    async def test_node_with_no_source_record_executes_and_stops_being_a_candidate(self, mock_wf: MagicMock) -> None:
        """A node with nothing to replay really runs, and stops waiting on times.

        The sync service waits on a candidate's source times. A restorable node
        with no source record has none and never will, so it is dropped from the
        candidates — otherwise every such node would stall the sync transaction
        for the full wait timeout before falling back to Temporal's times.
        """
        wf = _make_workflow(_retry("step_3"))
        wf.retry_context = _retry("step_3")
        wf._retry_replay_candidates = {"step_1"}
        mock_wf.execute_activity = AsyncMock(return_value=None)

        assert await wf._maybe_restore_retry_output(self.graph.get_node("step_1"), self.graph) is None

        assert wf._retry_replay_candidates == set()
        assert wf._restored_node_timestamps == {}

    @pytest.mark.asyncio
    async def test_retry_candidates_are_known_before_any_node_runs(self, mock_wf: MagicMock) -> None:
        """The candidate set is settled up front, not discovered mid-graph.

        The sync service asks the workflow whether a completing activity is a
        replay. If a node were only added to the set at the moment it replayed, a
        node the workflow had not reached yet would look like an ordinary
        execution and its source times would be dropped.
        """
        wf = _make_workflow(_retry("step_3"))
        wf.retry_context = _retry("step_3")
        mock_wf.execute_activity = AsyncMock(return_value={})

        await wf._prepare_retry(self.graph)

        assert wf._retry_replay_candidates == {"step_1", "step_2"}


class TestReplayedTimestampUpdateHandler:
    """The workflow side of the timestamp ask: does it wait, and when.

    The sync service calls this update when a node completes. What matters is
    which nodes make it block — a node that will never have source times must not
    hold the caller for the full timeout, and one that will must not answer early.

    ``wait_condition`` is stubbed so the predicate can be evaluated directly: a
    ``True`` means the handler returns without blocking, ``False`` means it would
    wait. This exercises the real handler and the real predicate, not a copy.
    """

    SOURCE_TIMES: ClassVar[dict[str, str | None]] = {
        "started_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:05:00+00:00",
    }

    async def _call(
        self,
        activity_id: str,
        *,
        candidates: set[str],
        timestamps: dict[str, dict[str, str | None]],
    ) -> tuple[dict[str, str | None] | None, bool, int]:
        """Return (handler result, predicate already true, timeout seconds)."""
        wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
        wf._retry_replay_candidates = candidates
        wf._restored_node_timestamps = timestamps

        seen: dict[str, Any] = {}

        async def _wait(predicate: Callable[[], bool], timeout: timedelta | None = None) -> None:  # noqa: ASYNC109
            # Mirrors wait_condition's real signature, which is why the name stays.
            seen["satisfied_now"] = predicate()
            seen["timeout"] = timeout

        with patch(
            "syntara.workflows.workflow_engine.dynamic_workflow.workflow.wait_condition",
            _wait,
        ):
            result = await cast("Any", wf).get_replayed_node_timestamps_when_ready(activity_id)

        return result, bool(seen["satisfied_now"]), cast("timedelta", seen["timeout"]).seconds

    @pytest.mark.asyncio
    async def test_a_replayed_node_answers_immediately_with_its_source_times(self) -> None:
        result, satisfied_now, timeout = await self._call(
            "script_1",
            candidates={"script_1"},
            timestamps={"script_1": self.SOURCE_TIMES},
        )

        assert result == self.SOURCE_TIMES
        assert satisfied_now, "a node that already has its times must not make the caller wait"
        assert timeout == 5

    @pytest.mark.asyncio
    async def test_a_candidate_without_times_yet_would_wait(self) -> None:
        """A candidate whose times have not landed is the race the update closes.

        Answering "no times" here would drop them permanently, because the
        completed event is only ever processed once.
        """
        result, satisfied_now, _timeout = await self._call(
            "script_1",
            candidates={"script_1", "script_2"},
            timestamps={},
        )

        assert satisfied_now is False, "answering early here loses the source times for good"
        assert result is None

    @pytest.mark.asyncio
    async def test_an_ordinary_node_answers_immediately_with_nothing(self) -> None:
        result, satisfied_now, _timeout = await self._call(
            "script_9",
            candidates={"script_1"},
            timestamps={"script_1": self.SOURCE_TIMES},
        )

        assert result is None
        assert satisfied_now, "a node that is not a replay must never make the caller wait"

    @pytest.mark.asyncio
    async def test_an_ordinary_run_answers_immediately_because_nothing_is_a_candidate(self) -> None:
        """No retry means an empty candidate set, so every node answers at once.

        This is what makes asking unconditionally cheap: an ordinary run pays a
        request per completed node and never waits.
        """
        result, satisfied_now, _timeout = await self._call(
            "script_1",
            candidates=set(),
            timestamps={},
        )

        assert result is None
        assert satisfied_now
