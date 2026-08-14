"""Unit tests for OrchestratorWorkflow switch routing and skip propagation.

Tests cover:
- Switch routing (multiple case branches)
- Skip propagation (non-taken branches marked skipped)
- Default port routing
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


def _build_switch_graph() -> WorkflowGraph:
    """Build: trigger -> switch -> (case_0: action_a, case_1: action_b, default: action_c)."""
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node(
        "sw",
        {
            "id": "sw",
            "type": "switch",
            "parameters": {
                "cases": [
                    {"port": "case_0", "label": "Approved", "condition": "${status} == 'approved'"},
                    {"port": "case_1", "label": "Rejected", "condition": "${status} == 'rejected'"},
                ],
                "default_port": "default",
            },
        },
    )
    backend.add_node("action_a", {"id": "action_a", "type": "script", "parameters": {}})
    backend.add_node("action_b", {"id": "action_b", "type": "script", "parameters": {}})
    backend.add_node("action_c", {"id": "action_c", "type": "script", "parameters": {}})
    backend.add_edge("trigger", "sw", None)
    backend.add_edge("sw", "action_a", {"from_port": "case_0"})
    backend.add_edge("sw", "action_b", {"from_port": "case_1"})
    backend.add_edge("sw", "action_c", {"from_port": "default"})
    return WorkflowGraph(backend)


def _build_switch_with_downstream_graph() -> WorkflowGraph:
    """Build: trigger -> switch -> (case_0: A -> D, case_1: B -> E, default: C -> F)."""
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node(
        "sw",
        {
            "id": "sw",
            "type": "switch",
            "parameters": {
                "cases": [
                    {"port": "case_0", "label": "Case 0", "condition": "True"},
                    {"port": "case_1", "label": "Case 1", "condition": "False"},
                ],
                "default_port": "default",
            },
        },
    )
    backend.add_node("a", {"id": "a", "type": "script", "parameters": {}})
    backend.add_node("b", {"id": "b", "type": "script", "parameters": {}})
    backend.add_node("c", {"id": "c", "type": "script", "parameters": {}})
    backend.add_node("a_downstream", {"id": "a_downstream", "type": "script", "parameters": {}})
    backend.add_node("b_downstream", {"id": "b_downstream", "type": "script", "parameters": {}})
    backend.add_node("c_downstream", {"id": "c_downstream", "type": "script", "parameters": {}})
    backend.add_edge("trigger", "sw", None)
    backend.add_edge("sw", "a", {"from_port": "case_0"})
    backend.add_edge("sw", "b", {"from_port": "case_1"})
    backend.add_edge("sw", "c", {"from_port": "default"})
    backend.add_edge("a", "a_downstream", None)
    backend.add_edge("b", "b_downstream", None)
    backend.add_edge("c", "c_downstream", None)
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
# Tests: Switch routing
# ---------------------------------------------------------------------------


class TestSwitchRouting:
    """Test switch node routes to correct case branch based on control data."""

    def test_case_0_successor_scheduled(self) -> None:
        """When switch routes to 'case_0', only action_a is scheduled."""
        wf = _make_workflow()
        graph = _build_switch_graph()
        wf.node_control_data["sw"] = {"next_port": "case_0"}
        pending: dict[str, asyncio.Task[Any]] = {}

        _run_schedule_successors(wf, "sw", graph, pending)

        assert "action_a" in pending
        assert "action_b" not in pending
        assert "action_c" not in pending

    def test_case_1_successor_scheduled(self) -> None:
        """When switch routes to 'case_1', only action_b is scheduled."""
        wf = _make_workflow()
        graph = _build_switch_graph()
        wf.node_control_data["sw"] = {"next_port": "case_1"}
        pending: dict[str, asyncio.Task[Any]] = {}

        _run_schedule_successors(wf, "sw", graph, pending)

        assert "action_b" in pending
        assert "action_a" not in pending
        assert "action_c" not in pending

    def test_default_port_successor_scheduled(self) -> None:
        """When switch routes to 'default', only action_c is scheduled."""
        wf = _make_workflow()
        graph = _build_switch_graph()
        wf.node_control_data["sw"] = {"next_port": "default"}
        pending: dict[str, asyncio.Task[Any]] = {}

        _run_schedule_successors(wf, "sw", graph, pending)

        assert "action_c" in pending
        assert "action_a" not in pending
        assert "action_b" not in pending

    def test_non_taken_branches_marked_skipped(self) -> None:
        """Non-taken branch nodes should be marked as skipped."""
        wf = _make_workflow()
        graph = _build_switch_graph()
        wf.node_control_data["sw"] = {"next_port": "case_0"}
        pending: dict[str, asyncio.Task[Any]] = {}

        _run_schedule_successors(wf, "sw", graph, pending)

        assert "action_b" in wf.skipped_nodes
        assert "action_c" in wf.skipped_nodes
        assert "action_a" not in wf.skipped_nodes


# ---------------------------------------------------------------------------
# Tests: Skip propagation through switch branches
# ---------------------------------------------------------------------------


class TestSwitchSkipPropagation:
    """Test that skipping propagates downstream through non-taken switch branches."""

    def test_downstream_of_skipped_branches_also_skipped(self) -> None:
        """Nodes downstream of non-taken branches should also be skipped."""
        wf = _make_workflow()
        graph = _build_switch_with_downstream_graph()
        wf.node_control_data["sw"] = {"next_port": "case_0"}
        pending: dict[str, asyncio.Task[Any]] = {}

        _run_schedule_successors(wf, "sw", graph, pending)

        assert "b" in wf.skipped_nodes
        assert "b_downstream" in wf.skipped_nodes
        assert "c" in wf.skipped_nodes
        assert "c_downstream" in wf.skipped_nodes

    def test_taken_branch_downstream_not_skipped(self) -> None:
        """Nodes on the taken branch should NOT be skipped."""
        wf = _make_workflow()
        graph = _build_switch_with_downstream_graph()
        wf.node_control_data["sw"] = {"next_port": "case_0"}
        pending: dict[str, asyncio.Task[Any]] = {}

        _run_schedule_successors(wf, "sw", graph, pending)

        assert "a" not in wf.skipped_nodes
        assert "a_downstream" not in wf.skipped_nodes
