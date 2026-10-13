"""Replaying a CONDITION or SWITCH by the branch the source run took.

A control node normally cannot be restored: it re-evaluates its own condition
against a namespace the retry has only partly rebuilt, while sibling branches are
still restoring. These tests cover the exception this PR adds — when exactly one
branch carries activity the source run's choice is known, so the node is handed
that branch instead of being asked to decide again.
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend
from syntara.workflows.workflow_engine.retry_mixin import (
    _INFERABLE_CONTROL_NODE_TYPES,
    _MIN_BRANCHES_FOR_INFERENCE,
    WorkflowRetryMixin,
)

from .conftest import init_workflow_runtime


@pytest.fixture
def mock_wf() -> Generator[MagicMock, None, None]:
    """Patch the Temporal workflow module so its logger is callable outside a run.

    ``_restored_control_result`` logs when it restores a branch, and
    ``workflow.logger`` refuses to emit unless a workflow event loop is active.
    """
    with (
        patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as patched,
        patch("syntara.workflows.workflow_engine.retry_mixin.workflow", patched),
    ):
        patched.logger = MagicMock()
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
    wf.retry_context = retry_context or {"source_execution_id": "src-1"}
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


def test_restored_control_result_publishes_the_port_and_marks_completed(mock_wf: MagicMock) -> None:
    """A restored control node carries its routing decision and no payload."""
    wf = _make_workflow()
    graph = _condition_graph()
    wf._retry_source_statuses = {
        "step_true": ActivityStatus.COMPLETED.value,
        "step_false": ActivityStatus.SKIPPED.value,
    }
    node = _node(graph, "cond_1")
    wf._retry_replay_candidates = {"cond_1"}

    result = wf._restored_control_result(node, graph)

    assert result == {"output": {}, "control": {"next_port": "true"}}
    assert wf._restored_node_ports["cond_1"] == "true"
    assert wf._restored_node_statuses["cond_1"] == ActivityStatus.COMPLETED.value


def test_restored_control_result_leaves_no_candidate_to_wait_on(mock_wf: MagicMock) -> None:
    """No activity is dispatched, so the sync service must not wait for one."""
    wf = _make_workflow()
    graph = _condition_graph()
    wf._retry_source_statuses = {
        "step_true": ActivityStatus.COMPLETED.value,
        "step_false": ActivityStatus.SKIPPED.value,
    }
    node = _node(graph, "cond_1")
    wf._retry_replay_candidates = {"cond_1", "step_2"}

    wf._restored_control_result(node, graph)

    assert "cond_1" not in wf._retry_replay_candidates
    assert "step_2" in wf._retry_replay_candidates, "other candidates are untouched"


def test_restored_control_result_is_none_when_inference_fails(mock_wf: MagicMock) -> None:
    """The caller must fall through to real execution rather than assume a branch."""
    wf = _make_workflow()
    graph = _condition_graph()
    wf._retry_source_statuses = {"step_true": ActivityStatus.SKIPPED.value, "step_false": ActivityStatus.SKIPPED.value}
    node = _node(graph, "cond_1")

    assert wf._restored_control_result(node, graph) is None
    assert "cond_1" not in wf._restored_node_ports


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

    restorable = wf._retry_restorable_nodes(graph)

    assert "cond_1" not in restorable
    assert wf._should_restore_node("cond_1", graph) is False


def test_loop_body_statuses_do_not_imply_a_branch() -> None:
    """A completed loop body must not be read as evidence for the true branch."""
    wf = _make_workflow()
    graph = _loop_after_condition_graph()
    wf._retry_source_statuses = {"body_a": ActivityStatus.COMPLETED.value}

    assert wf._infer_control_node_branch(_node(graph, "cond_1"), graph) is None
