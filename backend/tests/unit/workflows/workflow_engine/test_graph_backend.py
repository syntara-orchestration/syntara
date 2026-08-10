"""Tests for InMemoryGraphBackend (task 6.1).

Tests cover:
- add_node, add_edge, get_successors, get_predecessors
- get_edge_data, get_outgoing_edges, has_path
- find_cycles and topological_sort
"""

import pytest

from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _linear_backend() -> InMemoryGraphBackend:
    """A -> B -> C linear chain."""
    b = InMemoryGraphBackend()
    b.add_node("A", {"id": "A", "type": "action", "parameters": {}})
    b.add_node("B", {"id": "B", "type": "action", "parameters": {}})
    b.add_node("C", {"id": "C", "type": "action", "parameters": {}})
    b.add_edge("A", "B", {"from_port": "out"})
    b.add_edge("B", "C")
    return b


# ---------------------------------------------------------------------------
# add_node / get_node_data
# ---------------------------------------------------------------------------


class TestAddNode:
    """Tests for add_node and get_node_data."""

    def test_add_and_retrieve_node(self) -> None:
        b = InMemoryGraphBackend()
        b.add_node("n1", {"id": "n1", "type": "script", "parameters": {}})
        assert b.get_node_data("n1") == {"id": "n1", "type": "script", "parameters": {}}

    def test_get_nonexistent_node_raises(self) -> None:
        b = InMemoryGraphBackend()
        with pytest.raises(KeyError):
            b.get_node_data("missing")

    def test_overwrite_node_data(self) -> None:
        b = InMemoryGraphBackend()
        b.add_node("n1", {"id": "n1", "type": "v1"})
        b.add_node("n1", {"id": "n1", "type": "v2"})
        assert b.get_node_data("n1")["type"] == "v2"


# ---------------------------------------------------------------------------
# add_edge / get_successors / get_predecessors
# ---------------------------------------------------------------------------


class TestAddEdge:
    """Tests for add_edge, get_successors, get_predecessors."""

    def test_successors(self) -> None:
        b = _linear_backend()
        assert b.get_successors("A") == ["B"]
        assert b.get_successors("B") == ["C"]

    def test_predecessors(self) -> None:
        b = _linear_backend()
        assert b.get_predecessors("B") == ["A"]
        assert b.get_predecessors("C") == ["B"]

    def test_no_successors_for_leaf(self) -> None:
        b = _linear_backend()
        assert b.get_successors("C") == []

    def test_no_predecessors_for_root(self) -> None:
        b = _linear_backend()
        assert b.get_predecessors("A") == []

    def test_multiple_successors(self) -> None:
        b = InMemoryGraphBackend()
        b.add_node("A", {"id": "A", "type": "t", "parameters": {}})
        b.add_node("B", {"id": "B", "type": "t", "parameters": {}})
        b.add_node("C", {"id": "C", "type": "t", "parameters": {}})
        b.add_edge("A", "B")
        b.add_edge("A", "C")
        assert sorted(b.get_successors("A")) == ["B", "C"]

    def test_multiple_predecessors(self) -> None:
        b = InMemoryGraphBackend()
        b.add_node("A", {"id": "A", "type": "t", "parameters": {}})
        b.add_node("B", {"id": "B", "type": "t", "parameters": {}})
        b.add_node("C", {"id": "C", "type": "t", "parameters": {}})
        b.add_edge("A", "C")
        b.add_edge("B", "C")
        assert sorted(b.get_predecessors("C")) == ["A", "B"]

    def test_edge_with_data(self) -> None:
        b = InMemoryGraphBackend()
        b.add_node("A", {"id": "A", "type": "t", "parameters": {}})
        b.add_node("B", {"id": "B", "type": "t", "parameters": {}})
        b.add_edge("A", "B", {"from_port": "true"})
        assert b.get_successors("A") == ["B"]

    def test_edge_without_data(self) -> None:
        b = InMemoryGraphBackend()
        b.add_node("A", {"id": "A", "type": "t", "parameters": {}})
        b.add_node("B", {"id": "B", "type": "t", "parameters": {}})
        b.add_edge("A", "B")
        assert b.get_successors("A") == ["B"]


# ---------------------------------------------------------------------------
# get_edge_data
# ---------------------------------------------------------------------------


class TestGetEdgeData:
    """Tests for get_edge_data."""

    def test_returns_edge_data(self) -> None:
        b = _linear_backend()
        assert b.get_edge_data("A", "B") == {"from_port": "out"}

    def test_returns_none_for_edge_without_data(self) -> None:
        b = _linear_backend()
        assert b.get_edge_data("B", "C") is None

    def test_returns_none_for_nonexistent_edge(self) -> None:
        b = _linear_backend()
        assert b.get_edge_data("A", "C") is None

    def test_returns_none_for_reversed_direction(self) -> None:
        b = _linear_backend()
        assert b.get_edge_data("B", "A") is None


# ---------------------------------------------------------------------------
# get_outgoing_edges
# ---------------------------------------------------------------------------


class TestGetOutgoingEdges:
    """Tests for get_outgoing_edges."""

    def test_returns_edge_dicts(self) -> None:
        b = _linear_backend()
        edges = b.get_outgoing_edges("A")
        assert len(edges) == 1
        assert edges[0]["from"] == "A"
        assert edges[0]["to"] == "B"
        assert edges[0]["from_port"] == "out"

    def test_edge_without_data(self) -> None:
        b = _linear_backend()
        edges = b.get_outgoing_edges("B")
        assert len(edges) == 1
        assert edges[0] == {"from": "B", "to": "C"}

    def test_empty_for_leaf_node(self) -> None:
        b = _linear_backend()
        assert b.get_outgoing_edges("C") == []

    def test_empty_for_unknown_node(self) -> None:
        b = _linear_backend()
        assert b.get_outgoing_edges("nonexistent") == []

    def test_multiple_outgoing_edges(self) -> None:
        b = InMemoryGraphBackend()
        b.add_node("A", {"id": "A", "type": "t", "parameters": {}})
        b.add_node("B", {"id": "B", "type": "t", "parameters": {}})
        b.add_node("C", {"id": "C", "type": "t", "parameters": {}})
        b.add_edge("A", "B", {"from_port": "true"})
        b.add_edge("A", "C", {"from_port": "false"})
        edges = b.get_outgoing_edges("A")
        assert len(edges) == 2
        targets = {e["to"] for e in edges}
        assert targets == {"B", "C"}


# ---------------------------------------------------------------------------
# has_path
# ---------------------------------------------------------------------------


class TestHasPath:
    """Tests for has_path (DFS)."""

    def test_direct_path(self) -> None:
        b = _linear_backend()
        assert b.has_path("A", "B") is True

    def test_transitive_path(self) -> None:
        b = _linear_backend()
        assert b.has_path("A", "C") is True

    def test_no_reverse_path(self) -> None:
        b = _linear_backend()
        assert b.has_path("C", "A") is False

    def test_self_path(self) -> None:
        b = _linear_backend()
        assert b.has_path("A", "A") is True

    def test_no_path_between_disconnected(self) -> None:
        b = InMemoryGraphBackend()
        b.add_node("X", {"id": "X", "type": "t", "parameters": {}})
        b.add_node("Y", {"id": "Y", "type": "t", "parameters": {}})
        assert b.has_path("X", "Y") is False

    def test_path_in_diamond(self) -> None:
        b = InMemoryGraphBackend()
        for nid in ("A", "B", "C", "D"):
            b.add_node(nid, {"id": nid, "type": "t", "parameters": {}})
        b.add_edge("A", "B")
        b.add_edge("A", "C")
        b.add_edge("B", "D")
        b.add_edge("C", "D")
        assert b.has_path("A", "D") is True
        assert b.has_path("D", "A") is False


# ---------------------------------------------------------------------------
# get_all_nodes
# ---------------------------------------------------------------------------


class TestGetAllNodes:
    """Tests for get_all_nodes."""

    def test_returns_all_node_ids(self) -> None:
        b = _linear_backend()
        assert set(b.get_all_nodes()) == {"A", "B", "C"}

    def test_empty_graph(self) -> None:
        b = InMemoryGraphBackend()
        assert b.get_all_nodes() == []


# ---------------------------------------------------------------------------
# find_cycles
# ---------------------------------------------------------------------------


class TestFindCycles:
    """Tests for find_cycles."""

    def test_no_cycles_in_linear(self) -> None:
        b = _linear_backend()
        assert b.find_cycles() == []

    def test_detects_cycle(self) -> None:
        b = InMemoryGraphBackend()
        for nid in ("A", "B", "C"):
            b.add_node(nid, {"id": nid, "type": "t", "parameters": {}})
        b.add_edge("A", "B")
        b.add_edge("B", "C")
        b.add_edge("C", "A")
        cycles = b.find_cycles()
        assert len(cycles) >= 1

    def test_detects_self_loop(self) -> None:
        b = InMemoryGraphBackend()
        b.add_node("A", {"id": "A", "type": "t", "parameters": {}})
        b.add_edge("A", "A")
        cycles = b.find_cycles()
        assert len(cycles) >= 1
        assert cycles[0] == ["A"]

    def test_empty_graph(self) -> None:
        b = InMemoryGraphBackend()
        assert b.find_cycles() == []


# ---------------------------------------------------------------------------
# topological_sort
# ---------------------------------------------------------------------------


class TestTopologicalSort:
    """Tests for topological_sort."""

    def test_linear_order(self) -> None:
        b = _linear_backend()
        order = b.topological_sort()
        assert order.index("A") < order.index("B") < order.index("C")

    def test_returns_all_nodes(self) -> None:
        b = _linear_backend()
        assert set(b.topological_sort()) == {"A", "B", "C"}

    def test_raises_on_cycle(self) -> None:
        b = InMemoryGraphBackend()
        for nid in ("A", "B"):
            b.add_node(nid, {"id": nid, "type": "t", "parameters": {}})
        b.add_edge("A", "B")
        b.add_edge("B", "A")
        with pytest.raises(ValueError, match="cycle"):
            b.topological_sort()

    def test_empty_graph(self) -> None:
        b = InMemoryGraphBackend()
        assert b.topological_sort() == []

    def test_single_node(self) -> None:
        b = InMemoryGraphBackend()
        b.add_node("X", {"id": "X", "type": "t", "parameters": {}})
        assert b.topological_sort() == ["X"]

    def test_diamond_ordering(self) -> None:
        """A -> B, A -> C, B -> D, C -> D. A must come first, D last."""
        b = InMemoryGraphBackend()
        for nid in ("A", "B", "C", "D"):
            b.add_node(nid, {"id": nid, "type": "t", "parameters": {}})
        b.add_edge("A", "B")
        b.add_edge("A", "C")
        b.add_edge("B", "D")
        b.add_edge("C", "D")
        order = b.topological_sort()
        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("D")


# ---------------------------------------------------------------------------
# Edge cases — unknown nodes
# ---------------------------------------------------------------------------


class TestUnknownNodeEdgeCases:
    """Behavior when querying nodes not in the graph."""

    def test_get_successors_unknown_node_returns_empty(self) -> None:
        b = _linear_backend()
        assert b.get_successors("nonexistent") == []

    def test_get_predecessors_unknown_node_returns_empty(self) -> None:
        b = _linear_backend()
        assert b.get_predecessors("nonexistent") == []

    def test_has_path_from_unknown_returns_false(self) -> None:
        b = _linear_backend()
        assert b.has_path("nonexistent", "A") is False

    def test_find_cycles_detects_multiple_cycles(self) -> None:
        """Graph with two independent cycles."""
        b = InMemoryGraphBackend()
        for nid in ("A", "B", "C", "D"):
            b.add_node(nid, {"id": nid, "type": "t", "parameters": {}})
        b.add_edge("A", "B")
        b.add_edge("B", "A")  # cycle 1
        b.add_edge("C", "D")
        b.add_edge("D", "C")  # cycle 2
        cycles = b.find_cycles()
        assert len(cycles) >= 2
