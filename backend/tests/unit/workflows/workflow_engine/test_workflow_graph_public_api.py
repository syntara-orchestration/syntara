"""Tests for WorkflowGraph public methods added in task 2.1.

Verifies that get_successors() and get_outgoing_edges() are exposed as
public methods on WorkflowGraph and correctly delegate to the backend.
Also verifies dynamic_workflow.py no longer accesses graph._backend.
"""

import inspect

from syntara.workflows.workflow_engine.graph import WorkflowGraph
from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend


def _make_graph() -> WorkflowGraph:
    r"""Build a small graph for testing.

    Structure:
        trigger -> nodeA -> nodeB
                        \-> nodeC  (via port "false")
    """
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "http_trigger", "parameters": {}})
    backend.add_node("nodeA", {"id": "nodeA", "type": "condition", "parameters": {}})
    backend.add_node("nodeB", {"id": "nodeB", "type": "action", "parameters": {}})
    backend.add_node("nodeC", {"id": "nodeC", "type": "action", "parameters": {}})

    backend.add_edge("trigger", "nodeA", None)
    backend.add_edge("nodeA", "nodeB", {"from_port": "true"})
    backend.add_edge("nodeA", "nodeC", {"from_port": "false"})

    return WorkflowGraph(backend)


class TestGetSuccessors:
    """Tests for WorkflowGraph.get_successors()."""

    def test_returns_successor_ids(self) -> None:
        graph = _make_graph()
        result = graph.get_successors("nodeA")
        assert sorted(result) == ["nodeB", "nodeC"]

    def test_returns_empty_list_for_leaf_node(self) -> None:
        graph = _make_graph()
        assert graph.get_successors("nodeB") == []

    def test_returns_empty_list_for_another_leaf(self) -> None:
        graph = _make_graph()
        assert graph.get_successors("nodeC") == []

    def test_single_successor(self) -> None:
        graph = _make_graph()
        assert graph.get_successors("trigger") == ["nodeA"]

    def test_matches_backend_directly(self) -> None:
        """Public method must return the same result as _backend."""
        graph = _make_graph()
        assert graph.get_successors("nodeA") == graph._backend.get_successors("nodeA")


class TestGetOutgoingEdges:
    """Tests for WorkflowGraph.get_outgoing_edges()."""

    def test_returns_edge_dicts_with_ports(self) -> None:
        graph = _make_graph()
        edges = graph.get_outgoing_edges("nodeA")
        assert len(edges) == 2
        ports = {e["from_port"] for e in edges}
        assert ports == {"true", "false"}

    def test_edge_dicts_contain_from_and_to_keys(self) -> None:
        graph = _make_graph()
        edges = graph.get_outgoing_edges("nodeA")
        for edge in edges:
            assert "from" in edge
            assert "to" in edge
            assert edge["from"] == "nodeA"

    def test_edge_without_port_data(self) -> None:
        """Edge added with data=None should still have from/to keys."""
        graph = _make_graph()
        edges = graph.get_outgoing_edges("trigger")
        assert len(edges) == 1
        assert edges[0]["from"] == "trigger"
        assert edges[0]["to"] == "nodeA"

    def test_returns_empty_list_for_leaf_node(self) -> None:
        graph = _make_graph()
        assert graph.get_outgoing_edges("nodeB") == []

    def test_matches_backend_directly(self) -> None:
        """Public method must return the same result as _backend."""
        graph = _make_graph()
        assert graph.get_outgoing_edges("nodeA") == graph._backend.get_outgoing_edges("nodeA")


class TestNoDynamicWorkflowBackendAccess:
    """Verify dynamic_workflow.py no longer accesses graph._backend."""

    def test_no_backend_access_in_dynamic_workflow_source(self) -> None:
        """The source file must contain zero references to _backend."""
        from syntara.workflows.workflow_engine import dynamic_workflow

        source = inspect.getsource(dynamic_workflow)
        occurrences = source.count("._backend")
        assert occurrences == 0, f"Expected 0 references to ._backend in dynamic_workflow.py, found {occurrences}"


class TestGetPredecessorsPublicMethod:
    """Verify the pre-existing get_predecessors public method works correctly.

    This method existed before task 2.1 but was used to replace _backend
    access — confirm it still works.
    """

    def test_returns_predecessor_ids(self) -> None:
        graph = _make_graph()
        result = graph.get_predecessors("nodeB")
        assert result == ["nodeA"]

    def test_returns_empty_list_for_root_node(self) -> None:
        graph = _make_graph()
        assert graph.get_predecessors("trigger") == []

    def test_multiple_predecessors_for_convergence_node(self) -> None:
        """A node with multiple incoming edges returns all predecessors."""
        backend = InMemoryGraphBackend()
        backend.add_node("a", {"id": "a", "type": "action", "parameters": {}})
        backend.add_node("b", {"id": "b", "type": "action", "parameters": {}})
        backend.add_node("merge", {"id": "merge", "type": "action", "parameters": {}})
        backend.add_edge("a", "merge", None)
        backend.add_edge("b", "merge", None)
        graph = WorkflowGraph(backend)

        result = graph.get_predecessors("merge")
        assert sorted(result) == ["a", "b"]
