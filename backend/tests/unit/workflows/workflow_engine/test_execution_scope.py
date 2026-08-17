"""Unit tests for _apply_execution_scope — parallel-branch and multi-trigger isolation."""

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
    mock_logger = MagicMock()
    with (
        patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf,
        patch("syntara.workflows.workflow_engine.converge_mixin.workflow", mock_wf),
    ):
        mock_wf.logger = mock_logger
        mock_wf.info.return_value = MagicMock(workflow_id="test-wf-id")
        yield mock_wf


def _make_workflow(stop_after_nodes: set[str] | None = None) -> OrchestratorWorkflow:
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
    wf._cof_failed_nodes = set()
    wf._converge_branch_nodes = {}
    init_workflow_runtime(wf)
    wf.pre_resolved_outputs = {}
    wf.stop_after_nodes = stop_after_nodes if stop_after_nodes is not None else set()
    return wf


def _node(node_id: str, node_type: str = "script") -> dict[str, Any]:
    return {"id": node_id, "type": node_type, "parameters": {}}


class TestApplyExecutionScope:
    """Tests for OrchestratorWorkflow._apply_execution_scope."""

    def test_noop_when_no_stop_after_nodes(self) -> None:
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", _node("trigger", "manual_trigger"))
        backend.add_node("a", _node("a"))
        backend.add_node("b", _node("b"))
        backend.add_edge("trigger", "a", None)
        backend.add_edge("a", "b", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow(stop_after_nodes=set())
        wf._apply_execution_scope(graph)

        assert wf.skipped_nodes == set()

    def test_linear_chain_skips_downstream(self) -> None:
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", _node("trigger", "manual_trigger"))
        backend.add_node("a", _node("a"))
        backend.add_node("b", _node("b"))
        backend.add_node("c", _node("c"))
        backend.add_edge("trigger", "a", None)
        backend.add_edge("a", "b", None)
        backend.add_edge("b", "c", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow(stop_after_nodes={"b"})
        wf._apply_execution_scope(graph)

        assert "c" in wf.skipped_nodes
        assert "a" not in wf.skipped_nodes
        assert "b" not in wf.skipped_nodes

    def test_parallel_branch_skips_unrelated(self) -> None:
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", _node("trigger", "manual_trigger"))
        backend.add_node("a", _node("a"))
        backend.add_node("x", _node("x"))
        backend.add_node("b", _node("b"))
        backend.add_node("y", _node("y"))
        backend.add_edge("trigger", "a", None)
        backend.add_edge("a", "x", None)
        backend.add_edge("trigger", "b", None)
        backend.add_edge("b", "y", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow(stop_after_nodes={"x"})
        wf._apply_execution_scope(graph)

        assert "b" in wf.skipped_nodes
        assert "y" in wf.skipped_nodes
        assert "a" not in wf.skipped_nodes
        assert "x" not in wf.skipped_nodes

    def test_diamond_converge_keeps_all_feeding_branches(self) -> None:
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", _node("trigger", "manual_trigger"))
        backend.add_node("a", _node("a"))
        backend.add_node("b", _node("b"))
        backend.add_node("conv", _node("conv", "converge"))
        backend.add_node("c", _node("c"))
        backend.add_edge("trigger", "a", None)
        backend.add_edge("trigger", "b", None)
        backend.add_edge("a", "conv", None)
        backend.add_edge("b", "conv", None)
        backend.add_edge("conv", "c", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow(stop_after_nodes={"conv"})
        wf._apply_execution_scope(graph)

        assert "c" in wf.skipped_nodes
        assert "a" not in wf.skipped_nodes
        assert "b" not in wf.skipped_nodes
        assert "conv" not in wf.skipped_nodes

    def test_multiple_targets_union_scope(self) -> None:
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", _node("trigger", "manual_trigger"))
        backend.add_node("a", _node("a"))
        backend.add_node("x", _node("x"))
        backend.add_node("b", _node("b"))
        backend.add_node("y", _node("y"))
        backend.add_edge("trigger", "a", None)
        backend.add_edge("a", "x", None)
        backend.add_edge("trigger", "b", None)
        backend.add_edge("b", "y", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow(stop_after_nodes={"x", "y"})
        wf._apply_execution_scope(graph)

        assert wf.skipped_nodes == set()

    def test_triggers_never_skipped(self) -> None:
        backend = InMemoryGraphBackend()
        backend.add_node("t1", _node("t1", "manual_trigger"))
        backend.add_node("t2", _node("t2", "webhook_trigger"))
        backend.add_node("a", _node("a"))
        backend.add_node("b", _node("b"))
        backend.add_edge("t1", "a", None)
        backend.add_edge("t2", "b", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow(stop_after_nodes={"a"})
        wf._apply_execution_scope(graph)

        assert "t1" not in wf.skipped_nodes
        assert "t2" not in wf.skipped_nodes
        assert "b" in wf.skipped_nodes

    def test_target_itself_in_scope(self) -> None:
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", _node("trigger", "manual_trigger"))
        backend.add_node("a", _node("a"))
        backend.add_node("b", _node("b"))
        backend.add_edge("trigger", "a", None)
        backend.add_edge("a", "b", None)
        graph = WorkflowGraph(backend)

        wf = _make_workflow(stop_after_nodes={"b"})
        wf._apply_execution_scope(graph)

        assert "b" not in wf.skipped_nodes
        assert "a" not in wf.skipped_nodes
