"""Abstract graph backend interface for workflow graphs."""

from abc import abstractmethod
from typing import Any, Protocol


class IGraphBackend(Protocol):
    """Abstract interface for graph operations - implementation agnostic.

    This interface allows WorkflowGraph to work with different graph
    implementations: simple in-memory (prototype), NetworkX (advanced),
    or custom high-performance implementations.
    """

    @abstractmethod
    def add_node(self, node_id: str, data: dict[str, Any]) -> None:
        """Add a node to the graph."""
        ...

    @abstractmethod
    def add_edge(self, from_node: str, to_node: str, data: dict[str, Any] | None = None) -> None:
        """Add a directed edge between nodes."""
        ...

    @abstractmethod
    def get_node_data(self, node_id: str) -> dict[str, Any]:
        """Get node attributes.

        Raises:
            KeyError: If node_id not found

        """
        ...

    @abstractmethod
    def get_successors(self, node_id: str) -> list[str]:
        """Get nodes directly reachable from this node (outgoing edges)."""
        ...

    @abstractmethod
    def get_predecessors(self, node_id: str) -> list[str]:
        """Get nodes that have edges pointing to this node (incoming edges)."""
        ...

    @abstractmethod
    def get_edge_data(self, from_node: str, to_node: str) -> dict[str, Any] | None:
        """Get edge attributes (or None if edge doesn't exist)."""
        ...

    @abstractmethod
    def get_all_nodes(self) -> list[str]:
        """Get all node IDs in the graph."""
        ...

    @abstractmethod
    def get_outgoing_edges(self, node_id: str) -> list[dict[str, Any]]:
        """Get all outgoing edges with their attributes.

        Returns:
            List of edge dicts with keys: from, to, from_port, to_port, etc.

        """
        ...

    @abstractmethod
    def has_path(self, from_node: str, to_node: str) -> bool:
        """Check if a path exists from from_node to to_node."""
        ...

    @abstractmethod
    def find_cycles(self) -> list[list[str]]:
        """Detect cycles in the graph.

        Returns:
            List of cycles, where each cycle is a list of node IDs

        """
        ...

    @abstractmethod
    def topological_sort(self) -> list[str]:
        """Return nodes in topological order (only valid for DAGs).

        Raises:
            ValueError: If graph contains cycles

        """
        ...


class InMemoryGraphBackend:
    """Simple in-memory graph backend for prototyping.

    Uses dictionaries for basic graph operations.
    For advanced features (cycle detection, topological sort), use NetworkXBackend.
    """

    def __init__(self) -> None:
        """Initialize in-memory graph backend."""
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: dict[str, list[tuple[str, dict[str, Any] | None]]] = {}
        self._reverse_edges: dict[str, list[str]] = {}

    def add_node(self, node_id: str, data: dict[str, Any]) -> None:
        """Add a node to the graph."""
        self._nodes[node_id] = data

    def add_edge(self, from_node: str, to_node: str, data: dict[str, Any] | None = None) -> None:
        """Add a directed edge between nodes."""
        if from_node not in self._edges:
            self._edges[from_node] = []
        self._edges[from_node].append((to_node, data))

        if to_node not in self._reverse_edges:
            self._reverse_edges[to_node] = []
        self._reverse_edges[to_node].append(from_node)

    def get_node_data(self, node_id: str) -> dict[str, Any]:
        """Get node attributes."""
        return self._nodes[node_id]

    def get_successors(self, node_id: str) -> list[str]:
        """Get nodes directly reachable from this node."""
        edges = self._edges.get(node_id, [])
        return [to_node for to_node, _ in edges]

    def get_predecessors(self, node_id: str) -> list[str]:
        """Get nodes that have edges pointing to this node."""
        return self._reverse_edges.get(node_id, [])

    def get_edge_data(self, from_node: str, to_node: str) -> dict[str, Any] | None:
        """Get edge attributes or None if edge doesn't exist."""
        edges = self._edges.get(from_node, [])
        for to, data in edges:
            if to == to_node:
                return data
        return None

    def get_all_nodes(self) -> list[str]:
        """Get all node IDs in the graph."""
        return list(self._nodes.keys())

    def has_path(self, from_node: str, to_node: str) -> bool:
        """Check if a path exists from from_node to to_node using DFS."""
        if from_node == to_node:
            return True

        visited = set()
        stack = [from_node]

        while stack:
            current = stack.pop()
            if current == to_node:
                return True
            if current in visited:
                continue
            visited.add(current)
            stack.extend(self.get_successors(current))

        return False

    def find_cycles(self) -> list[list[str]]:
        """Detect cycles in the graph using DFS-based algorithm.

        Returns:
            List of cycles, where each cycle is a list of node IDs forming the cycle.

        """
        cycles: list[list[str]] = []
        white = set(self._nodes.keys())  # unvisited
        gray: set[str] = set()  # in current DFS path
        path: list[str] = []

        def _dfs(node: str) -> None:
            white.discard(node)
            gray.add(node)
            path.append(node)

            for successor in self.get_successors(node):
                if successor in gray:
                    cycle_start = path.index(successor)
                    cycles.append(path[cycle_start:])
                elif successor in white:
                    _dfs(successor)

            path.pop()
            gray.discard(node)

        while white:
            _dfs(next(iter(white)))

        return cycles

    def topological_sort(self) -> list[str]:
        """Return nodes in topological order using DFS.

        Raises:
            ValueError: If graph contains cycles.

        """
        cycles = self.find_cycles()
        if cycles:
            cycle_desc = " -> ".join(cycles[0])
            msg = f"Graph contains a cycle: {cycle_desc}"
            raise ValueError(msg)

        visited: set[str] = set()
        order: list[str] = []

        def _dfs(node: str) -> None:
            visited.add(node)
            for successor in self.get_successors(node):
                if successor not in visited:
                    _dfs(successor)
            order.append(node)

        for node_id in self._nodes:
            if node_id not in visited:
                _dfs(node_id)

        order.reverse()
        return order

    def get_outgoing_edges(self, node_id: str) -> list[dict[str, Any]]:
        """Get all outgoing edges with their attributes."""
        edges = self._edges.get(node_id, [])
        result: list[dict[str, Any]] = []
        for to_node, edge_data in edges:
            edge_dict: dict[str, Any] = {
                "from": node_id,
                "to": to_node,
            }
            if edge_data:
                edge_dict.update(edge_data)
            result.append(edge_dict)
        return result
