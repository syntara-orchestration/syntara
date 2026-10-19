"""Replaying a CONDITION or SWITCH by the branch the source run took.

A control node normally cannot be restored: it re-evaluates its own condition
against a namespace the retry has only partly rebuilt, while sibling branches are
still restoring. These tests cover the exception this PR adds — when exactly one
branch carries activity the source run's choice is known, so the node is handed
that branch instead of being asked to decide again.
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.core.exceptions import SafeValueError
from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName
from syntara.workflows.workflow_engine.retry_mixin import (
    _INFERABLE_CONTROL_NODE_TYPES,
    _MIN_BRANCHES_FOR_INFERENCE,
    WorkflowRetryMixin,
)

from .conftest import init_workflow_runtime


@pytest.fixture
def mock_wf() -> Generator[MagicMock, None, None]:
    """Patch the Temporal workflow module so its logger is callable outside a run.

    ``_restore_node_state`` logs when it restores a branch, and
    ``workflow.logger`` refuses to emit unless a workflow event loop is active.
    """
    with (
        patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as patched,
        patch("syntara.workflows.workflow_engine.retry_mixin.workflow", patched),
    ):
        patched.logger = MagicMock()
        # execute_activity is awaited on the real workflow module.
        patched.execute_activity = AsyncMock(return_value={"output_data": {}, "status": "completed"})
        yield patched


def _make_workflow(retry_context: dict[str, Any] | None = None) -> OrchestratorWorkflow:
    """Create an OrchestratorWorkflow with initialized state, bypassing __init__."""
    from syntara.workflows.utils.namespace_resolver import NamespaceResolver

    wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
    wf.skipped_nodes = set()
    wf.failed_nodes = {}
    wf.resolver = NamespaceResolver()
    wf.node_inputs = {}
    wf.node_control_data = {}
    wf.loop_state = {}
    wf.loop_body_map = {}
    wf.loop_iteration_results = {}
    wf._loop_bodies = {}
    wf._active_loop_iteration = {}
    wf._timeout_tasks = {}
    wf._timed_out_converge_nodes = set()
    wf._detached_nodes = set()
    wf._converge_branch_nodes = {}
    init_workflow_runtime(wf)
    wf._restored_control_ports = {}
    wf._resolved_control_port_cache = {}
    wf.execution_id = "test-execution-id"
    wf._created_by_user_id = ""
    wf.request_id = None
    wf.pre_resolved_outputs = {}
    wf.stop_after_nodes = set()
    wf.retry_context = retry_context or {"retry_from_execution_id": "src-1"}
    return wf


def _condition_graph(*, merge_branches: bool = False, single_port: bool = False) -> WorkflowGraph:
    """Build trigger -> cond_1 -> (step_true | step_false) -> step_2.

    ``merge_branches`` routes both branches through a shared node, so neither has
    an exclusive successor and no branch choice can be read off the statuses.
    ``single_port`` gives the condition one output port, below
    ``_MIN_BRANCHES_FOR_INFERENCE``.
    """
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("cond_1", {"id": "cond_1", "type": "condition", "parameters": {}})
    backend.add_node("step_true", {"id": "step_true", "type": "script", "parameters": {}})
    backend.add_node("step_false", {"id": "step_false", "type": "script", "parameters": {}})
    backend.add_node("step_2", {"id": "step_2", "type": "script", "parameters": {}})
    backend.add_edge("trigger", "cond_1", None)
    if single_port:
        backend.add_edge("cond_1", "step_true", {"from_port": "true"})
    else:
        backend.add_edge("cond_1", "step_true", {"from_port": "true"})
        backend.add_edge("cond_1", "step_false", {"from_port": "false"})
    if merge_branches:
        backend.add_edge("step_true", "step_2", None)
        backend.add_edge("step_false", "step_2", None)
    else:
        backend.add_edge("step_true", "step_2", None)
        backend.add_edge("step_false", "step_2", None)
    return WorkflowGraph(backend)


def _loop_after_condition_graph() -> WorkflowGraph:
    """Condition whose only true-branch successor is a loop, with a body inside it."""
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("cond_1", {"id": "cond_1", "type": "condition", "parameters": {}})
    backend.add_node("step_false", {"id": "step_false", "type": "script", "parameters": {}})
    backend.add_node("loop_1", {"id": "loop_1", "type": "loop", "parameters": {}})
    backend.add_node("body_a", {"id": "body_a", "type": "script", "parameters": {}})
    backend.add_node("step_2", {"id": "step_2", "type": "script", "parameters": {}})
    backend.add_edge("trigger", "cond_1", None)
    backend.add_edge("cond_1", "loop_1", {"from_port": "true"})
    backend.add_edge("cond_1", "step_false", {"from_port": "false"})
    backend.add_edge("loop_1", "body_a", {"from_port": "iterate"})
    backend.add_edge("loop_1", "step_2", {"from_port": "complete"})
    backend.add_edge("body_a", "body_a", {"from_port": "iterate"})
    return WorkflowGraph(backend)


def _node(graph: WorkflowGraph, node_id: str) -> ActivityNode:
    node = graph.get_node(node_id)
    assert node is not None, f"missing node {node_id}"
    return node


# --- the branch is inferable when exactly one branch carries activity ---


def test_infers_the_branch_the_source_run_took() -> None:
    """Only the taken branch has activity; the other was skipped."""
    wf = _make_workflow()
    graph = _condition_graph()
    wf._retry_source_statuses = {
        "step_true": ActivityStatus.COMPLETED.value,
        "step_false": ActivityStatus.SKIPPED.value,
        "step_2": ActivityStatus.COMPLETED.value,
    }

    port = wf._infer_control_node_branch(_node(graph, "cond_1"), graph)

    assert port == "true", "should follow the edge the source run took, not re-decide"


def test_infers_the_false_branch_too() -> None:
    """Inference is not hardcoded to the first port."""
    wf = _make_workflow()
    graph = _condition_graph()
    wf._retry_source_statuses = {
        "step_true": ActivityStatus.SKIPPED.value,
        "step_false": ActivityStatus.COMPLETED.value,
    }

    assert wf._infer_control_node_branch(_node(graph, "cond_1"), graph) == "false"


# --- and is not, when the recorded state does not identify one branch ---


def test_returns_none_when_no_branch_ran() -> None:
    """Both skipped means the source run never left the condition."""
    wf = _make_workflow()
    graph = _condition_graph()
    wf._retry_source_statuses = {"step_true": ActivityStatus.SKIPPED.value, "step_false": ActivityStatus.SKIPPED.value}

    assert wf._infer_control_node_branch(_node(graph, "cond_1"), graph) is None


def test_returns_none_when_both_branches_ran() -> None:
    """Two active branches do not identify a choice; guessing would be wrong."""
    wf = _make_workflow()
    graph = _condition_graph()
    wf._retry_source_statuses = {
        "step_true": ActivityStatus.COMPLETED.value,
        "step_false": ActivityStatus.COMPLETED.value,
    }

    assert wf._infer_control_node_branch(_node(graph, "cond_1"), graph) is None


def test_returns_none_when_branches_merge() -> None:
    """With no exclusive successor, a node's status says nothing about the choice."""
    wf = _make_workflow()
    graph = _condition_graph(merge_branches=True)
    # Only the shared successor has status, so both ports see the same activity.
    wf._retry_source_statuses = {"step_2": ActivityStatus.COMPLETED.value}

    assert wf._infer_control_node_branch(_node(graph, "cond_1"), graph) is None


def test_returns_none_below_the_minimum_branch_count() -> None:
    """One port is not a branch choice, so it must rerun."""
    wf = _make_workflow()
    graph = _condition_graph(single_port=True)
    wf._retry_source_statuses = {"step_true": ActivityStatus.COMPLETED.value}

    assert len({edge["from_port"] for edge in graph.get_outgoing_edges("cond_1") if edge.get("from_port")}) == 1
    assert _MIN_BRANCHES_FOR_INFERENCE == 2
    assert wf._infer_control_node_branch(_node(graph, "cond_1"), graph) is None


def test_returns_none_for_a_node_type_outside_the_allowlist() -> None:
    """LOOP and WAIT stay excluded whatever the statuses say."""
    wf = _make_workflow()
    graph = _condition_graph()
    loop_node = ActivityNode(node_id="loop_1", node_type="loop", parameters={})

    assert loop_node.type not in _INFERABLE_CONTROL_NODE_TYPES
    assert wf._infer_control_node_branch(loop_node, graph) is None


# --- exclusivity computation ---


def test_walk_from_port_does_not_follow_through_a_loop() -> None:
    """A loop body is one record per iteration, so it cannot say which branch ran."""
    graph = _loop_after_condition_graph()

    reached = WorkflowRetryMixin._walk_from_port("cond_1", "true", graph)

    assert "loop_1" in reached, "the loop itself is on the path"
    assert "body_a" not in reached, "walking must stop at the loop, not enter its body"


def test_shared_downstream_does_not_count_as_exclusive() -> None:
    """step_2 is reachable from both ports, so only step_true/step_false are exclusive."""
    graph = _condition_graph()

    reached_true = WorkflowRetryMixin._walk_from_port("cond_1", "true", graph)
    reached_false = WorkflowRetryMixin._walk_from_port("cond_1", "false", graph)

    assert "step_2" in reached_true
    assert "step_2" in reached_false
    assert "step_true" in reached_true
    assert "step_true" not in reached_false


# --- the restored result the scheduler consumes ---


@pytest.mark.asyncio
async def test_restored_control_result_publishes_the_inferred_port(mock_wf: MagicMock) -> None:
    """The inferred branch travels as control data, which is what the scheduler reads."""
    wf = _make_workflow()
    graph = _condition_graph()
    wf._retry_source_statuses = {
        "step_true": ActivityStatus.COMPLETED.value,
        "step_false": ActivityStatus.SKIPPED.value,
    }
    node = _node(graph, "cond_1")
    mock_wf.execute_activity.return_value = {"output_data": {"evaluated_result": True}, "status": "completed"}

    result = await wf._restore_node_state(node, graph)

    assert result is not None
    assert result["control"] == {"next_port": "true"}
    assert wf._restored_node_statuses["cond_1"] == ActivityStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_restored_control_result_keeps_the_source_run_output(mock_wf: MagicMock) -> None:
    """CONDITION's evaluated_result must survive, not be replaced by an empty dict."""
    wf = _make_workflow()
    graph = _condition_graph()
    wf._retry_source_statuses = {
        "step_true": ActivityStatus.COMPLETED.value,
        "step_false": ActivityStatus.SKIPPED.value,
    }
    node = _node(graph, "cond_1")
    mock_wf.execute_activity.return_value = {
        "output_data": {"evaluated_result": True},
        "status": "completed",
        "input_data": {"left": 2, "right": 2},
    }

    result = await wf._restore_node_state(node, graph)

    assert result is not None
    assert result["output"] == {"evaluated_result": True}, "the source output must not be fabricated away"
    assert result["control"] == {"next_port": "true"}, "the inferred port is control, not output"
    assert wf.node_inputs["cond_1"] == {"left": 2, "right": 2}, "the source input is republished too"


@pytest.mark.asyncio
async def test_restored_control_result_reads_the_replay_under_the_node_id(mock_wf: MagicMock) -> None:
    """The source row is fetched under this node's own id, like any restored node."""
    wf = _make_workflow()
    graph = _condition_graph()
    wf._retry_source_statuses = {
        "step_true": ActivityStatus.COMPLETED.value,
        "step_false": ActivityStatus.SKIPPED.value,
    }
    node = _node(graph, "cond_1")
    mock_wf.execute_activity.return_value = {"output_data": {}, "status": "completed"}

    await wf._restore_node_state(node, graph)

    assert mock_wf.execute_activity.await_args.kwargs["activity_id"] == "cond_1"
    assert mock_wf.execute_activity.await_args.kwargs["args"] == ["src-1", "cond_1"], "the node id names the source row"


@pytest.mark.asyncio
async def test_restored_control_result_is_none_when_inference_fails(mock_wf: MagicMock) -> None:
    """The caller must fall through to real execution rather than assume a branch."""
    wf = _make_workflow()
    graph = _condition_graph()
    wf._retry_source_statuses = {"step_true": ActivityStatus.SKIPPED.value, "step_false": ActivityStatus.SKIPPED.value}
    node = _node(graph, "cond_1")

    assert await wf._restore_node_state(node, graph) is None
    # The source row is read before inference, because it is also where
    # control_data comes from. So an ambiguous branch still costs one read; that
    # is the price of taking the persisted port when there is one.
    assert mock_wf.execute_activity.await_count == 1


# --- how this reaches the restorable set ---


def test_inferable_condition_is_restorable_when_a_branch_is_known() -> None:
    """The whole point: a condition becomes restorable instead of always rerunning."""
    wf = _make_workflow()
    graph = _condition_graph()
    wf._retry_source_statuses = {
        "step_true": ActivityStatus.COMPLETED.value,
        "step_false": ActivityStatus.SKIPPED.value,
    }

    restorable = wf._retry_restorable_nodes(graph)

    assert "cond_1" in restorable
    assert wf._should_restore_node("cond_1", graph) is True


def test_condition_is_not_restorable_when_the_branch_is_unknown() -> None:
    """Falling back to rerun must stay the default when nothing identifies a branch."""
    wf = _make_workflow()
    graph = _condition_graph()
    wf._retry_source_statuses = {"step_true": ActivityStatus.SKIPPED.value, "step_false": ActivityStatus.SKIPPED.value}

    # The condition stays in the upstream region; it is the scheduling-time
    # decision that refuses it, because no branch can be recovered for it.
    assert "cond_1" in wf._retry_restorable_nodes(graph)
    assert wf._should_restore_node("cond_1", graph) is False


def test_loop_body_statuses_do_not_imply_a_branch() -> None:
    """A completed loop body must not be read as evidence for the true branch."""
    wf = _make_workflow()
    graph = _loop_after_condition_graph()
    wf._retry_source_statuses = {"body_a": ActivityStatus.COMPLETED.value}

    assert wf._infer_control_node_branch(_node(graph, "cond_1"), graph) is None


@pytest.mark.asyncio
async def test_restoring_a_condition_needs_no_manually_initialised_retry_state(
    mock_wf: MagicMock,
) -> None:
    """Nothing on the restore path may depend on a field only the fixtures set.

    Every other test here builds through ``init_workflow_runtime``, which seeds a
    pile of ``_restored_*`` dictionaries. That hid a real crash: an attribute
    assigned by the restore path but never initialised in production raised
    ``AttributeError`` on the first inferable condition in a real retry, while all
    of these tests passed. This one builds the workflow the way ``__init__`` does
    — nothing seeded by hand — so an uninitialised field fails loudly here.
    """
    from syntara.workflows.utils.namespace_resolver import NamespaceResolver

    wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
    wf.retry_context = {"retry_from_execution_id": "src-1", "eligible_point_ids": ["step_true"]}
    wf.resolver = NamespaceResolver()
    wf.node_inputs = {}
    wf.node_control_data = {}
    wf._runtime_settings = {}
    wf._has_unhandled_failure = False
    # Deliberately NOT calling init_workflow_runtime: only _initialize_retry_state
    # and _initialize_state exist in production, and both are exercised elsewhere.
    graph = _condition_graph()
    wf._retry_source_statuses = {
        "step_true": ActivityStatus.COMPLETED.value,
        "step_false": ActivityStatus.SKIPPED.value,
    }
    wf._retry_replay_candidates = set()
    wf._restored_node_timestamps = {}
    wf._restored_node_statuses = {}
    wf._restored_node_outputs = {}
    wf._restored_control_ports = {}
    wf._resolved_control_port_cache = {}
    mock_wf.execute_activity.return_value = {"output_data": {"evaluated_result": True}, "status": "completed"}

    result = await wf._restore_node_state(_node(graph, "cond_1"), graph)

    assert result is not None
    assert result["control"] == {"next_port": "true"}
    assert result["output"] == {"evaluated_result": True}


# --- control_data is read directly; inference is only the fallback ---


@pytest.mark.asyncio
async def test_port_is_read_from_persisted_control_data(mock_wf: MagicMock) -> None:
    """A run recorded since control data landed needs no inference at all."""
    wf = _make_workflow()
    graph = _condition_graph()
    node = _node(graph, "cond_1")
    # Deliberately ambiguous statuses: if inference were consulted it would fail
    # and the node would rerun, so this only passes on the direct read.
    wf._retry_source_statuses = {ActivityStatus.SKIPPED.value: ActivityStatus.SKIPPED.value}
    mock_wf.execute_activity.return_value = {
        "output_data": {"evaluated_result": True},
        "status": "completed",
        "control_data": {"next_port": "true"},
    }
    inference = MagicMock(return_value=None)
    wf._infer_control_node_branch = inference  # type: ignore[method-assign]  # type: ignore[method-assign]

    result = await wf._restore_node_state(node, graph)

    assert result is not None
    assert result["control"] == {"next_port": "true"}
    inference.assert_not_called()  # control_data is authoritative; inference must not run


@pytest.mark.asyncio
async def test_persisted_port_wins_over_an_ambiguous_inference(mock_wf: MagicMock) -> None:
    """The recorded decision outranks anything re-derived from branch statuses."""
    wf = _make_workflow()
    graph = _condition_graph()
    node = _node(graph, "cond_1")
    wf._retry_source_statuses = {
        "step_true": ActivityStatus.COMPLETED.value,
        "step_false": ActivityStatus.COMPLETED.value,
    }
    mock_wf.execute_activity.return_value = {
        "output_data": {"matched_port": "fallback"},
        "status": "completed",
        "control_data": {"next_port": "fallback"},
    }
    wf._infer_control_node_branch = MagicMock(return_value="true")  # type: ignore[method-assign]

    result = await wf._restore_node_state(node, graph)

    assert result is not None
    assert result["control"] == {"next_port": "fallback"}


@pytest.mark.asyncio
async def test_falls_back_to_inference_when_control_data_is_absent(mock_wf: MagicMock) -> None:
    """Runs predating the column still replay, via the inference path."""
    wf = _make_workflow()
    graph = _condition_graph()
    node = _node(graph, "cond_1")
    wf._retry_source_statuses = {
        "step_true": ActivityStatus.COMPLETED.value,
        "step_false": ActivityStatus.SKIPPED.value,
    }
    mock_wf.execute_activity.return_value = {"output_data": {}, "status": "completed"}
    inference = MagicMock(return_value="true")
    wf._infer_control_node_branch = inference  # type: ignore[method-assign]  # type: ignore[method-assign]

    result = await wf._restore_node_state(node, graph)

    assert result is not None
    assert result["control"] == {"next_port": "true"}
    inference.assert_called_once()  # no control data to read, so inference must run


@pytest.mark.asyncio
async def test_falls_back_when_control_data_has_no_next_port(mock_wf: MagicMock) -> None:
    """Control data present but carrying no port is not enough to route."""
    wf = _make_workflow()
    graph = _condition_graph()
    node = _node(graph, "cond_1")
    wf._retry_source_statuses = {
        "step_true": ActivityStatus.COMPLETED.value,
        "step_false": ActivityStatus.SKIPPED.value,
    }
    mock_wf.execute_activity.return_value = {
        "output_data": {},
        "status": "completed",
        "control_data": {"something_else": 1},
    }
    inference = MagicMock(return_value="false")
    wf._infer_control_node_branch = inference  # type: ignore[method-assign]  # type: ignore[method-assign]

    result = await wf._restore_node_state(node, graph)

    assert result is not None
    assert result["control"] == {"next_port": "false"}
    inference.assert_called_once()


@pytest.mark.asyncio
async def test_null_control_data_is_treated_as_absent(mock_wf: MagicMock) -> None:
    """The column is nullable, so a null must not raise or short-circuit."""
    wf = _make_workflow()
    graph = _condition_graph()
    node = _node(graph, "cond_1")
    wf._retry_source_statuses = {
        "step_true": ActivityStatus.COMPLETED.value,
        "step_false": ActivityStatus.SKIPPED.value,
    }
    mock_wf.execute_activity.return_value = {"output_data": {}, "status": "completed", "control_data": None}
    wf._infer_control_node_branch = MagicMock(return_value="true")  # type: ignore[method-assign]

    result = await wf._restore_node_state(node, graph)

    assert result is not None
    assert result["control"] == {"next_port": "true"}


# --- the prefetched ports, which is what classification actually reads -------


@pytest.mark.asyncio
async def test_prefetched_port_makes_a_node_restorable_without_inference(mock_wf: MagicMock) -> None:
    """Restorable classification must honour the persisted port on its own.

    Classification runs before any node can dispatch an activity, so it can only
    consult what ``_prepare_retry`` prefetched. If it fell back to inference here
    an ambiguous-but-recorded node would be rejected before its branch was read.
    """
    wf = _make_workflow()
    graph = _condition_graph()
    # Ambiguous on purpose: inference would decline, so only the prefetch can pass.
    wf._retry_source_statuses = {ActivityStatus.SKIPPED.value: ActivityStatus.SKIPPED.value}
    wf._restored_control_ports = {"cond_1": "true"}

    assert "cond_1" in wf._retry_restorable_nodes(graph)
    assert wf._should_restore_node("cond_1", graph) is True
    mock_wf.execute_activity.assert_not_awaited(), "classification must not dispatch to learn a port"


@pytest.mark.asyncio
async def test_prefetched_port_wins_over_a_contradicting_inference(mock_wf: MagicMock) -> None:
    """A recorded port outranks anything inference would conclude."""
    wf = _make_workflow()
    graph = _condition_graph()
    wf._retry_source_statuses = {
        "step_true": ActivityStatus.COMPLETED.value,
        "step_false": ActivityStatus.COMPLETED.value,
    }
    wf._restored_control_ports = {"cond_1": "false"}
    inference = MagicMock(return_value="true")
    wf._infer_control_node_branch = inference  # type: ignore[method-assign]

    assert wf._resolved_control_port(_node(graph, "cond_1"), graph) == "false"
    inference.assert_not_called()


@pytest.mark.asyncio
async def test_no_prefetched_port_still_falls_back_to_inference(mock_wf: MagicMock) -> None:
    """Runs predating the column keep the inference path."""
    wf = _make_workflow()
    graph = _condition_graph()
    wf._retry_source_statuses = {
        "step_true": ActivityStatus.COMPLETED.value,
        "step_false": ActivityStatus.SKIPPED.value,
    }
    inference = MagicMock(return_value="true")
    wf._infer_control_node_branch = inference  # type: ignore[method-assign]

    assert wf._resolved_control_port(_node(graph, "cond_1"), graph) == "true"
    inference.assert_called_once()


# --- the candidate set the sync service gates on ----------------------------
#
# _retry_replay_candidates is read by the sync service the moment an activity
# completes: it asks the workflow whether this node is one it should expect a
# replay for, and waits if so. A node listed but never replayed costs the
# monitor a serial 5s wait for a timestamp that is never written. These assert
# the set through _prepare_retry, which is what populates it.


async def test_a_loop_is_a_candidate_and_is_replayed(
    mock_wf: MagicMock,
) -> None:
    """A loop in the upstream candidate set uses the loop replay path."""
    wf = _make_workflow({"retry_from_execution_id": "src-1", "eligible_point_ids": ["step_2"]})
    graph = _loop_after_condition_graph()
    wf._retry_source_statuses = {"step_2": ActivityStatus.FAILED.value}

    await wf._prepare_retry(graph)

    assert "loop_1" in wf._retry_replay_candidates
    assert wf._should_restore_node("loop_1", graph) is True


async def test_a_control_node_is_dropped_from_the_candidates_when_it_must_rerun(
    mock_wf: MagicMock,
) -> None:
    """The set starts open and narrows as nodes are scheduled.

    A loop 826 cannot replay is a candidate from the start, so the set can grow
    into every control node. Once traversal reaches it and decides to rerun, it
    is discarded — before it completes, so the sync service is never asked about
    it and never waits out its timeout.
    """
    wf = _make_workflow({"retry_from_execution_id": "src-1", "eligible_point_ids": ["step_2"]})
    graph = _loop_after_condition_graph()
    wf._retry_source_statuses = {"step_2": ActivityStatus.FAILED.value}
    await wf._prepare_retry(graph)
    assert "loop_1" in wf._retry_replay_candidates, "it starts as a candidate"

    assert await wf._maybe_restore_retry_output(_node(graph, "loop_1"), graph) is None
    assert "loop_1" not in wf._retry_replay_candidates, "and is gone once it reruns"


async def test_a_restored_control_node_stays_a_candidate(mock_wf: MagicMock) -> None:
    """The other direction: a node that does replay must keep its candidate slot."""
    wf = _make_workflow({"retry_from_execution_id": "src-1", "eligible_point_ids": ["step_2"]})
    graph = _condition_graph()

    async def _activity(name: str, **kwargs: object) -> object:
        if name == ActivityName.RETRY_CONTROL_PORTS:
            return {"cond_1": "true"}
        return {"step_true": ActivityStatus.COMPLETED.value, "step_2": ActivityStatus.FAILED.value}

    mock_wf.execute_activity.side_effect = _activity
    await wf._prepare_retry(graph)

    assert await wf._maybe_restore_retry_output(_node(graph, "cond_1"), graph) is not None
    assert "cond_1" in wf._retry_replay_candidates


async def test_the_resolver_runs_once_per_node(mock_wf: MagicMock) -> None:
    """Inference is memoised: candidate construction and scheduling must agree.

    Workflow code has to reach the same answer wherever it is asked, and
    re-deriving the branch is both redundant work and a way for the two call
    sites to disagree.
    """
    wf = _make_workflow({"retry_from_execution_id": "src-1", "eligible_point_ids": ["step_true"]})
    graph = _condition_graph()
    wf._retry_source_statuses = {
        "step_true": ActivityStatus.COMPLETED.value,
        "step_false": ActivityStatus.SKIPPED.value,
    }

    inference = MagicMock(return_value="true")
    wf._infer_control_node_branch = inference  # type: ignore[method-assign]

    node = _node(graph, "cond_1")
    first = wf._resolved_control_port(node, graph)
    second = wf._resolved_control_port(node, graph)

    assert first == second == "true"
    inference.assert_called_once()  # the second call is served from the cache


async def test_a_refused_node_is_not_re_resolved(mock_wf: MagicMock) -> None:
    """None is a real answer, so it is cached too rather than re-inferred."""
    wf = _make_workflow({"retry_from_execution_id": "src-1", "eligible_point_ids": ["step_true"]})
    graph = _condition_graph(merge_branches=True)
    inference = MagicMock(return_value=None)
    wf._infer_control_node_branch = inference  # type: ignore[method-assign]

    node = _node(graph, "cond_1")
    assert wf._resolved_control_port(node, graph) is None
    assert wf._resolved_control_port(node, graph) is None

    inference.assert_called_once()


async def test_a_restored_condition_is_a_candidate_so_the_service_asks_about_it(
    mock_wf: MagicMock,
) -> None:
    """The other direction: a replayed control node must be advertised.

    Dropping it from the set would make the service treat the replay as an
    ordinary execution and keep Temporal's timestamps, losing the source times
    the replay is supposed to restore.
    """
    wf = _make_workflow({"retry_from_execution_id": "src-1", "eligible_point_ids": ["step_2"]})
    graph = _condition_graph()

    async def _activity(name: str, **kwargs: object) -> object:
        if name == ActivityName.RETRY_CONTROL_PORTS:
            return {"cond_1": "true"}
        return {"step_true": ActivityStatus.COMPLETED.value, "step_2": ActivityStatus.FAILED.value}

    mock_wf.execute_activity.side_effect = _activity

    await wf._prepare_retry(graph)

    assert wf._should_restore_node("cond_1", graph) is True
    assert "cond_1" in wf._retry_replay_candidates


async def test_a_vanished_record_does_not_raise_for_a_control_node(
    mock_wf: MagicMock,
) -> None:
    """A control node tolerates a missing record; an ordinary one does not.

    The two paths differ here on purpose. The replay runs under the node's own
    activity id, so an ordinary node whose row disappeared raises rather than
    let a real execution follow and be refused by the sync service's terminal
    guard. A control node still has a recorded port, so it restores from that
    and the vanished row costs it nothing.
    """
    wf = _make_workflow({"retry_from_execution_id": "src-1", "eligible_point_ids": ["step_2"]})
    graph = _condition_graph()
    wf._restored_control_ports = {"cond_1": "true"}
    mock_wf.execute_activity = AsyncMock(return_value=None)

    result = await wf._restore_node_state(_node(graph, "cond_1"), graph)

    assert result is not None, "the recorded port still restores it"
    assert result["control"] == {"next_port": "true"}


async def test_a_vanished_record_raises_for_an_ordinary_node(mock_wf: MagicMock) -> None:
    """The other half of the difference, so the guard above is not accidental."""
    wf = _make_workflow({"retry_from_execution_id": "src-1", "eligible_point_ids": ["step_2"]})
    graph = _condition_graph()
    wf._retry_source_statuses = {"step_true": ActivityStatus.COMPLETED.value}
    mock_wf.execute_activity = AsyncMock(return_value=None)

    with pytest.raises(SafeValueError, match="disappeared"):
        await wf._restore_node_state(_node(graph, "step_true"), graph)
