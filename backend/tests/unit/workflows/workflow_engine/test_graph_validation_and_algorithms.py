"""Tests for graph validation and backend algorithms (task 5.2).

Tests cover:
- InMemoryGraphBackend.find_cycles() — DFS-based cycle detection
- InMemoryGraphBackend.topological_sort() — topological ordering for DAGs, ValueError for cyclic graphs
- WorkflowGraph.validate_structure() — structural validation checks
- WorkflowGraph.from_dict() — validation integration on graph construction
"""

import pytest

from syntara.workflows.workflow_engine.graph import WorkflowGraph
from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _backend_with_dag() -> InMemoryGraphBackend:
    """A -> B -> C (simple DAG, no cycles)."""
    b = InMemoryGraphBackend()
    b.add_node("A", {"id": "A", "type": "action", "parameters": {}})
    b.add_node("B", {"id": "B", "type": "action", "parameters": {}})
    b.add_node("C", {"id": "C", "type": "action", "parameters": {}})
    b.add_edge("A", "B")
    b.add_edge("B", "C")
    return b


def _backend_with_cycle() -> InMemoryGraphBackend:
    """A -> B -> C -> A (single cycle)."""
    b = InMemoryGraphBackend()
    b.add_node("A", {"id": "A", "type": "action", "parameters": {}})
    b.add_node("B", {"id": "B", "type": "action", "parameters": {}})
    b.add_node("C", {"id": "C", "type": "action", "parameters": {}})
    b.add_edge("A", "B")
    b.add_edge("B", "C")
    b.add_edge("C", "A")
    return b


def _backend_with_self_loop() -> InMemoryGraphBackend:
    """A -> A (self-loop)."""
    b = InMemoryGraphBackend()
    b.add_node("A", {"id": "A", "type": "action", "parameters": {}})
    b.add_edge("A", "A")
    return b


def _valid_workflow_dict() -> dict[str, object]:
    """Minimal valid workflow definition with a trigger and connected node."""
    return {
        "schema_version": "1",
        "name": "test",
        "description": "test workflow",
        "triggers": [{"id": "t1", "type": "http_trigger", "parameters": {}}],
        "nodes": [{"id": "n1", "type": "action", "parameters": {}}],
        "edges": [{"from": "t1", "to": "n1"}],
    }


class TestFindCycles:
    """Tests for cycle detection using DFS."""

    def test_no_cycles_in_dag(self) -> None:
        backend = _backend_with_dag()
        assert backend.find_cycles() == []

    def test_detects_simple_cycle(self) -> None:
        backend = _backend_with_cycle()
        cycles = backend.find_cycles()
        assert len(cycles) >= 1
        # The cycle should contain all three nodes (no trailing duplicate)
        cycle_nodes = set(cycles[0])
        assert cycle_nodes == {"A", "B", "C"}

    def test_cycle_is_contiguous_path(self) -> None:
        backend = _backend_with_cycle()
        cycles = backend.find_cycles()
        assert len(cycles) >= 1
        assert len(cycles[0]) == 3  # A->B->C, no trailing duplicate

    def test_detects_self_loop(self) -> None:
        backend = _backend_with_self_loop()
        cycles = backend.find_cycles()
        assert len(cycles) >= 1
        assert cycles[0] == ["A"]

    def test_empty_graph_has_no_cycles(self) -> None:
        backend = InMemoryGraphBackend()
        assert backend.find_cycles() == []

    def test_single_node_no_edges_has_no_cycles(self) -> None:
        backend = InMemoryGraphBackend()
        backend.add_node("X", {"id": "X", "type": "action", "parameters": {}})
        assert backend.find_cycles() == []

    def test_disconnected_components_one_with_cycle(self) -> None:
        """Cycle in one component should still be detected."""
        b = InMemoryGraphBackend()
        # Component 1: DAG
        b.add_node("A", {"id": "A", "type": "action", "parameters": {}})
        b.add_node("B", {"id": "B", "type": "action", "parameters": {}})
        b.add_edge("A", "B")
        # Component 2: Cycle
        b.add_node("X", {"id": "X", "type": "action", "parameters": {}})
        b.add_node("Y", {"id": "Y", "type": "action", "parameters": {}})
        b.add_edge("X", "Y")
        b.add_edge("Y", "X")

        cycles = b.find_cycles()
        assert len(cycles) >= 1

    def test_diamond_dag_has_no_cycles(self) -> None:
        """A -> B, A -> C, B -> D, C -> D — no cycle."""
        b = InMemoryGraphBackend()
        for nid in ("A", "B", "C", "D"):
            b.add_node(nid, {"id": nid, "type": "action", "parameters": {}})
        b.add_edge("A", "B")
        b.add_edge("A", "C")
        b.add_edge("B", "D")
        b.add_edge("C", "D")
        assert b.find_cycles() == []


class TestTopologicalSort:
    """Tests for topological ordering."""

    def test_simple_dag_ordering(self) -> None:
        backend = _backend_with_dag()
        order = backend.topological_sort()
        assert order.index("A") < order.index("B")
        assert order.index("B") < order.index("C")

    def test_returns_all_nodes(self) -> None:
        backend = _backend_with_dag()
        order = backend.topological_sort()
        assert set(order) == {"A", "B", "C"}

    def test_raises_value_error_on_cycle(self) -> None:
        backend = _backend_with_cycle()
        with pytest.raises(ValueError, match="cycle"):
            backend.topological_sort()

    def test_raises_value_error_on_self_loop(self) -> None:
        backend = _backend_with_self_loop()
        with pytest.raises(ValueError, match="cycle"):
            backend.topological_sort()

    def test_single_node(self) -> None:
        b = InMemoryGraphBackend()
        b.add_node("only", {"id": "only", "type": "action", "parameters": {}})
        assert b.topological_sort() == ["only"]

    def test_empty_graph(self) -> None:
        b = InMemoryGraphBackend()
        assert b.topological_sort() == []

    def test_diamond_dag_respects_all_edges(self) -> None:
        """A -> B, A -> C, B -> D, C -> D."""
        b = InMemoryGraphBackend()
        for nid in ("A", "B", "C", "D"):
            b.add_node(nid, {"id": nid, "type": "action", "parameters": {}})
        b.add_edge("A", "B")
        b.add_edge("A", "C")
        b.add_edge("B", "D")
        b.add_edge("C", "D")

        order = b.topological_sort()
        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("D")

    def test_disconnected_dag(self) -> None:
        """Two separate chains: A->B and C->D."""
        b = InMemoryGraphBackend()
        for nid in ("A", "B", "C", "D"):
            b.add_node(nid, {"id": nid, "type": "action", "parameters": {}})
        b.add_edge("A", "B")
        b.add_edge("C", "D")

        order = b.topological_sort()
        assert order.index("A") < order.index("B")
        assert order.index("C") < order.index("D")


class TestValidateStructure:
    """Tests for structural validation of the workflow graph."""

    def test_valid_graph_returns_no_errors(self) -> None:
        backend = InMemoryGraphBackend()
        backend.add_node("t1", {"id": "t1", "type": "http_trigger", "parameters": {}})
        backend.add_node("n1", {"id": "n1", "type": "action", "parameters": {}})
        backend.add_edge("t1", "n1")
        graph = WorkflowGraph(backend)

        assert graph.validate_structure() == []

    def test_no_trigger_node_returns_error(self) -> None:
        backend = InMemoryGraphBackend()
        backend.add_node("n1", {"id": "n1", "type": "action", "parameters": {}})
        backend.add_node("n2", {"id": "n2", "type": "action", "parameters": {}})
        backend.add_edge("n1", "n2")
        graph = WorkflowGraph(backend)

        errors = graph.validate_structure()
        assert any("trigger" in e.lower() for e in errors)

    def test_orphan_node_returns_error(self) -> None:
        backend = InMemoryGraphBackend()
        backend.add_node("t1", {"id": "t1", "type": "http_trigger", "parameters": {}})
        backend.add_node("n1", {"id": "n1", "type": "action", "parameters": {}})
        backend.add_node("orphan", {"id": "orphan", "type": "action", "parameters": {}})
        backend.add_edge("t1", "n1")
        graph = WorkflowGraph(backend)

        errors = graph.validate_structure()
        assert any("orphan" in e.lower() for e in errors)

    def test_trigger_node_not_flagged_as_orphan(self) -> None:
        """Trigger nodes with no incoming edges should not be flagged as orphans."""
        backend = InMemoryGraphBackend()
        backend.add_node("t1", {"id": "t1", "type": "http_trigger", "parameters": {}})
        backend.add_node("n1", {"id": "n1", "type": "action", "parameters": {}})
        backend.add_edge("t1", "n1")
        graph = WorkflowGraph(backend)

        errors = graph.validate_structure()
        assert not any("t1" in e for e in errors)

    def test_edge_referencing_nonexistent_node(self) -> None:
        """Edge pointing to a node not in the graph should produce an error."""
        backend = InMemoryGraphBackend()
        backend.add_node("t1", {"id": "t1", "type": "http_trigger", "parameters": {}})
        backend.add_node("n1", {"id": "n1", "type": "action", "parameters": {}})
        backend.add_edge("t1", "n1")
        # Manually add edge to non-existent node
        backend.add_edge("n1", "ghost")
        graph = WorkflowGraph(backend)

        errors = graph.validate_structure()
        assert any("ghost" in e for e in errors)
        assert any("non-existent" in e.lower() for e in errors)

    def test_multiple_errors_returned(self) -> None:
        """When multiple problems exist, all errors should be returned."""
        backend = InMemoryGraphBackend()
        # No trigger nodes
        backend.add_node("n1", {"id": "n1", "type": "action", "parameters": {}})
        backend.add_node("n2", {"id": "n2", "type": "action", "parameters": {}})
        # n1 orphan, n2 orphan, no trigger
        graph = WorkflowGraph(backend)

        errors = graph.validate_structure()
        # Should have at least: no trigger + orphan errors
        assert len(errors) >= 2

    def test_node_with_only_outgoing_edge_not_orphan(self) -> None:
        """A non-trigger node with only outgoing edges is not orphan."""
        backend = InMemoryGraphBackend()
        backend.add_node("t1", {"id": "t1", "type": "http_trigger", "parameters": {}})
        backend.add_node("n1", {"id": "n1", "type": "action", "parameters": {}})
        backend.add_node("n2", {"id": "n2", "type": "action", "parameters": {}})
        backend.add_edge("t1", "n1")
        backend.add_edge("n1", "n2")
        graph = WorkflowGraph(backend)

        errors = graph.validate_structure()
        assert not any("n1" in e for e in errors)

    def test_node_with_only_incoming_edge_not_orphan(self) -> None:
        """A node with only incoming edges (leaf node) is not orphan."""
        backend = InMemoryGraphBackend()
        backend.add_node("t1", {"id": "t1", "type": "http_trigger", "parameters": {}})
        backend.add_node("leaf", {"id": "leaf", "type": "action", "parameters": {}})
        backend.add_edge("t1", "leaf")
        graph = WorkflowGraph(backend)

        errors = graph.validate_structure()
        assert not any("leaf" in e for e in errors)


class TestFromDictValidation:
    """Tests that from_dict() calls validate_structure() and raises on errors."""

    def test_valid_workflow_succeeds(self) -> None:
        data = _valid_workflow_dict()
        graph = WorkflowGraph.from_dict(data)
        assert len(graph.get_all_nodes()) == 2

    def test_raises_on_no_trigger(self) -> None:
        data = {
            "schema_version": "1",
            "name": "bad",
            "description": "no trigger",
            "triggers": [],
            "nodes": [{"id": "n1", "type": "action", "parameters": {}}],
            "edges": [],
        }
        with pytest.raises(ValueError, match="validation failed"):
            WorkflowGraph.from_dict(data)

    def test_raises_on_orphan_node(self) -> None:
        data = {
            "schema_version": "1",
            "name": "bad",
            "description": "orphan",
            "triggers": [{"id": "t1", "type": "http_trigger", "parameters": {}}],
            "nodes": [
                {"id": "n1", "type": "action", "parameters": {}},
                {"id": "orphan", "type": "action", "parameters": {}},
            ],
            "edges": [{"from": "t1", "to": "n1"}],
        }
        with pytest.raises(ValueError, match="validation failed"):
            WorkflowGraph.from_dict(data)

    def test_raises_on_edge_to_nonexistent_node(self) -> None:
        data = {
            "schema_version": "1",
            "name": "bad",
            "description": "bad edge",
            "triggers": [{"id": "t1", "type": "http_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "action", "parameters": {}}],
            "edges": [
                {"from": "t1", "to": "n1"},
                {"from": "n1", "to": "ghost"},
            ],
        }
        with pytest.raises(ValueError, match="validation failed"):
            WorkflowGraph.from_dict(data)

    def test_error_message_contains_details(self) -> None:
        data = {
            "schema_version": "1",
            "name": "bad",
            "description": "no trigger",
            "triggers": [],
            "nodes": [{"id": "n1", "type": "action", "parameters": {}}],
            "edges": [],
        }
        with pytest.raises(ValueError, match="trigger"):
            WorkflowGraph.from_dict(data)

    def test_trigger_only_workflow_is_valid(self) -> None:
        """A workflow with just a trigger and no other nodes is valid."""
        data = {
            "schema_version": "1",
            "name": "simple",
            "description": "trigger only",
            "triggers": [{"id": "t1", "type": "http_trigger", "parameters": {}}],
            "nodes": [],
            "edges": [],
        }
        graph = WorkflowGraph.from_dict(data)
        assert len(graph.get_all_nodes()) == 1

    def test_loop_feedback_edges_are_skipped_during_build(self) -> None:
        """Edges with to_port='iterate' should be filtered out, not cause validation errors."""
        data = {
            "schema_version": "1",
            "name": "loop",
            "description": "loop workflow",
            "triggers": [{"id": "t1", "type": "http_trigger", "parameters": {}}],
            "nodes": [
                {"id": "loop1", "type": "loop", "parameters": {}},
                {"id": "body", "type": "action", "parameters": {}},
            ],
            "edges": [
                {"from": "t1", "to": "loop1"},
                {"from": "loop1", "to": "body", "from_port": "iterate"},
                {"from": "body", "to": "loop1", "to_port": "iterate"},
            ],
        }
        # The iterate feedback edge is filtered, so body only has incoming from loop1
        # and loop1 has outgoing to body — no orphans, has trigger
        graph = WorkflowGraph.from_dict(data)
        assert len(graph.get_all_nodes()) == 3
