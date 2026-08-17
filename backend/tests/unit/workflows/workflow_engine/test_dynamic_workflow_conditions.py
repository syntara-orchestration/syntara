"""Unit tests for OrchestratorWorkflow condition routing and skip propagation (task 6.3).

Tests cover:
- Condition routing (true/false branches)
- Skip propagation (non-taken branch nodes marked skipped)
"""

import asyncio
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.graph import WorkflowGraph
from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend
from tests.unit.workflows.workflow_engine.conftest import init_workflow_runtime


@pytest.fixture(autouse=True)
def _mock_temporal_workflow() -> Generator[MagicMock]:
    """Mock the Temporal workflow module to avoid 'Not in workflow event loop' errors."""
    mock_logger = MagicMock()
    with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf:
        mock_wf.logger = mock_logger
        mock_wf.info.return_value = MagicMock(workflow_id="test-wf-id")
        yield mock_wf


def _make_workflow(
    skipped_nodes: set[str] | None = None,
    failed_nodes: dict[str, str] | None = None,
    resolver: NamespaceResolver | None = None,
) -> OrchestratorWorkflow:
    """Create an OrchestratorWorkflow with initialized state, bypassing __init__."""
    wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
    wf.skipped_nodes = skipped_nodes if skipped_nodes is not None else set()
    wf.failed_nodes = failed_nodes if failed_nodes is not None else {}
    wf.resolver = resolver if resolver is not None else NamespaceResolver()
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
    wf.pre_resolved_outputs = {}
    wf.stop_after_nodes = set()
    return wf


def _build_condition_graph() -> WorkflowGraph:
    """Build: trigger -> condition -> (true: true_branch, false: false_branch)."""
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("cond", {"id": "cond", "type": "condition", "parameters": {"expr": "true"}})
    backend.add_node("true_branch", {"id": "true_branch", "type": "script", "parameters": {}})
    backend.add_node("false_branch", {"id": "false_branch", "type": "script", "parameters": {}})
    backend.add_edge("trigger", "cond", None)
    backend.add_edge("cond", "true_branch", {"from_port": "true"})
    backend.add_edge("cond", "false_branch", {"from_port": "false"})
    return WorkflowGraph(backend)


def _build_condition_with_downstream_graph() -> WorkflowGraph:
    """Build: trigger -> condition -> (true: A -> C, false: B -> D)."""
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("cond", {"id": "cond", "type": "condition", "parameters": {"expr": "true"}})
    backend.add_node("true_node", {"id": "true_node", "type": "script", "parameters": {}})
    backend.add_node("false_node", {"id": "false_node", "type": "script", "parameters": {}})
    backend.add_node("true_downstream", {"id": "true_downstream", "type": "script", "parameters": {}})
    backend.add_node("false_downstream", {"id": "false_downstream", "type": "script", "parameters": {}})
    backend.add_edge("trigger", "cond", None)
    backend.add_edge("cond", "true_node", {"from_port": "true"})
    backend.add_edge("cond", "false_node", {"from_port": "false"})
    backend.add_edge("true_node", "true_downstream", None)
    backend.add_edge("false_node", "false_downstream", None)
    return WorkflowGraph(backend)


def _build_linear_graph() -> WorkflowGraph:
    """Build: trigger -> node_a -> node_b (linear chain)."""
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("node_a", {"id": "node_a", "type": "script", "parameters": {}})
    backend.add_node("node_b", {"id": "node_b", "type": "script", "parameters": {}})
    backend.add_edge("trigger", "node_a", None)
    backend.add_edge("node_a", "node_b", None)
    return WorkflowGraph(backend)


def _run_schedule_successors(
    wf: OrchestratorWorkflow,
    completed_node_id: str,
    graph: WorkflowGraph,
    pending: dict[str, asyncio.Task[Any]],
) -> None:
    """Run _schedule_successors in a fresh event loop, cleaning up tasks after."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(wf._schedule_successors(completed_node_id, graph, pending))
    finally:
        for task in pending.values():
            task.cancel()
        loop.close()


# ---------------------------------------------------------------------------
# Tests: Condition routing
# ---------------------------------------------------------------------------


class TestConditionRouting:
    """Test condition node routes to true/false branches based on control data."""

    def test_true_branch_successor_scheduled(self) -> None:
        """When condition routes to 'true', only true_branch is scheduled."""
        wf = _make_workflow()
        graph = _build_condition_graph()
        wf.resolver.set_namespace("trigger", {})
        wf.resolver.set_namespace("cond", {"result": True})
        wf.node_control_data["cond"] = {"next_port": "true"}
        pending: dict[str, asyncio.Task[Any]] = {}

        _run_schedule_successors(wf, "cond", graph, pending)

        assert "true_branch" in pending
        assert "false_branch" not in pending

    def test_false_branch_successor_scheduled(self) -> None:
        """When condition routes to 'false', only false_branch is scheduled."""
        wf = _make_workflow()
        graph = _build_condition_graph()
        wf.resolver.set_namespace("trigger", {})
        wf.resolver.set_namespace("cond", {"result": False})
        wf.node_control_data["cond"] = {"next_port": "false"}
        pending: dict[str, asyncio.Task[Any]] = {}

        _run_schedule_successors(wf, "cond", graph, pending)

        assert "false_branch" in pending
        assert "true_branch" not in pending

    def test_non_taken_branch_marked_skipped(self) -> None:
        """The non-taken branch node should be marked as skipped."""
        wf = _make_workflow()
        graph = _build_condition_graph()
        wf.resolver.set_namespace("trigger", {})
        wf.resolver.set_namespace("cond", {"result": True})
        wf.node_control_data["cond"] = {"next_port": "true"}
        pending: dict[str, asyncio.Task[Any]] = {}

        _run_schedule_successors(wf, "cond", graph, pending)

        assert "false_branch" in wf.skipped_nodes


# ---------------------------------------------------------------------------
# Tests: Skip propagation
# ---------------------------------------------------------------------------


class TestSkipPropagation:
    """Test that skipping propagates downstream through non-taken branches."""

    def test_downstream_of_skipped_branch_also_skipped(self) -> None:
        """Nodes downstream of a non-taken branch should also be skipped."""
        wf = _make_workflow()
        graph = _build_condition_with_downstream_graph()
        wf.resolver.set_namespace("trigger", {})
        wf.resolver.set_namespace("cond", {"result": True})
        wf.node_control_data["cond"] = {"next_port": "true"}
        pending: dict[str, asyncio.Task[Any]] = {}

        _run_schedule_successors(wf, "cond", graph, pending)

        assert "false_node" in wf.skipped_nodes
        assert "false_downstream" in wf.skipped_nodes

    def test_taken_branch_downstream_not_skipped(self) -> None:
        """Nodes on the taken branch should NOT be skipped."""
        wf = _make_workflow()
        graph = _build_condition_with_downstream_graph()
        wf.resolver.set_namespace("trigger", {})
        wf.resolver.set_namespace("cond", {"result": True})
        wf.node_control_data["cond"] = {"next_port": "true"}
        pending: dict[str, asyncio.Task[Any]] = {}

        _run_schedule_successors(wf, "cond", graph, pending)

        assert "true_node" not in wf.skipped_nodes
        assert "true_downstream" not in wf.skipped_nodes

    def test_mark_downstream_propagates_through_chain(self) -> None:
        """_mark_downstream_as_skipped propagates through a multi-node chain."""
        wf = _make_workflow()
        graph = _build_linear_graph()
        wf.skipped_nodes.add("node_a")

        wf._mark_downstream_as_skipped("node_a", graph)

        assert "node_b" in wf.skipped_nodes


# ---------------------------------------------------------------------------
# Tests: String condition evaluation
# ---------------------------------------------------------------------------


class TestStringConditionEvaluation:
    """Test condition node with string comparison expressions."""

    def test_condition_with_string_template_resolves_correctly(self) -> None:
        """Condition node comparing string template values should evaluate correctly."""
        wf = _make_workflow()
        graph = _build_condition_graph()

        # Set up resolver with string value
        wf.resolver.set_namespace("trigger", {"status": "completed"})

        # Modify the condition node to use string comparison
        backend = graph._backend
        cond_data = backend.get_node_data("cond")
        cond_data["parameters"]["expr"] = '${trigger.status} == "completed"'

        # The condition should evaluate to true
        wf.node_control_data["cond"] = {"next_port": "true"}
        pending: dict[str, asyncio.Task[Any]] = {}

        _run_schedule_successors(wf, "cond", graph, pending)

        # Should route through true branch
        assert "true_branch" in pending
        assert "false_branch" not in pending
        assert "false_branch" in wf.skipped_nodes

    def test_condition_with_mismatched_string_routes_false(self) -> None:
        """Condition node with non-matching string should route to false branch."""
        wf = _make_workflow()
        graph = _build_condition_graph()

        # Set up resolver with different string value
        wf.resolver.set_namespace("trigger", {"status": "failed"})

        # Modify the condition node to use string comparison
        backend = graph._backend
        cond_data = backend.get_node_data("cond")
        cond_data["parameters"]["expr"] = '${trigger.status} == "completed"'

        # The condition should evaluate to false
        wf.node_control_data["cond"] = {"next_port": "false"}
        pending: dict[str, asyncio.Task[Any]] = {}

        _run_schedule_successors(wf, "cond", graph, pending)

        # Should route through false branch
        assert "false_branch" in pending
        assert "true_branch" not in pending
        assert "true_branch" in wf.skipped_nodes
