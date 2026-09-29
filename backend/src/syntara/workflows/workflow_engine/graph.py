"""Workflow graph domain model for v2 workflows.

This module provides the domain model for workflow graphs, delegating
graph operations to a pluggable backend implementation.
"""

from typing import Any

from syntara.workflows.workflow_engine.graph_backend import IGraphBackend, InMemoryGraphBackend
from syntara.workflows.workflow_engine.models.workflow_definition import (
    NodeSettingsBase,
    NodeSettingsCof,
    NodeSettingsCofDisabled,
    NodeSettingsFull,
    NodeSettingsNoRetry,
    NodeType,
)

_NODE_SETTINGS_CLASS: dict[str, type[NodeSettingsBase]] = {
    NodeType.HTTP_REQUEST: NodeSettingsFull,
    NodeType.AAP_JOB_TEMPLATE: NodeSettingsFull,
    NodeType.AAP_WORKFLOW_JOB_TEMPLATE: NodeSettingsFull,
    NodeType.INTERNAL_ACTIVITY: NodeSettingsFull,
    NodeType.SCRIPT: NodeSettingsNoRetry,
    NodeType.AGENTIC: NodeSettingsNoRetry,
    NodeType.APPROVAL: NodeSettingsNoRetry,
    NodeType.WAIT: NodeSettingsCofDisabled,
    NodeType.CONVERGE: NodeSettingsCof,
    NodeType.LOOP: NodeSettingsCof,
    NodeType.CONDITION: NodeSettingsBase,
    NodeType.SWITCH: NodeSettingsBase,
}


def _parse_node_settings(node_type: str, raw: dict[str, Any] | None) -> NodeSettingsBase:
    """Instantiate the correct NodeSettings subclass for a node type."""
    cls = _NODE_SETTINGS_CLASS.get(node_type, NodeSettingsBase)
    return cls(**(raw or {}))


class ActivityNode:
    """Domain object representing an activity node in the workflow."""

    id: str
    name: str | None
    type: str
    parameters: dict[str, Any]
    outputs: dict[str, str] | None
    settings: NodeSettingsBase

    def __init__(
        self,
        node_id: str,
        node_type: str,
        parameters: dict[str, Any],
        name: str | None = None,
        outputs: dict[str, str] | None = None,
        settings: NodeSettingsBase | None = None,
    ) -> None:
        """Initialize an activity node.

        Args:
            node_id: Unique node identifier
            node_type: Type of the activity node
            parameters: Node parameters dictionary
            name: Human-readable display name (optional)
            outputs: Output extraction mapping (optional)
            settings: Node level overrides of general behaviors

        """
        self.id = node_id
        self.name = name
        self.type = node_type
        self.parameters = parameters
        self.outputs = outputs
        self.settings = settings if settings is not None else _parse_node_settings(node_type, None)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActivityNode":
        """Create ActivityNode from dictionary."""
        node_type = data["type"]
        return cls(
            node_id=data["id"],
            node_type=node_type,
            parameters=data.get("parameters", {}),
            name=data.get("name"),
            outputs=data.get("outputs"),
            settings=_parse_node_settings(node_type, data.get("settings")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result: dict[str, Any] = {"id": self.id, "type": self.type, "parameters": self.parameters}
        if self.name:
            result["name"] = self.name
        if self.outputs:
            result["outputs"] = self.outputs
        return result


class WorkflowGraph:
    """Domain model for workflow graph - backend agnostic.

    This class provides workflow-specific operations while delegating
    graph algorithms to a pluggable backend implementation.

    The graph structure is immutable once loaded - only execution state changes.
    """

    def __init__(self, backend: IGraphBackend) -> None:
        """Initialize graph with a backend implementation.

        Args:
            backend: Graph backend implementation (InMemory, NetworkX, etc.)

        """
        self._backend = backend
        self.metadata: dict[str, Any] = {}

    @classmethod
    def from_dict(cls, data: dict[str, Any], backend_type: str = "inmemory") -> "WorkflowGraph":
        """Create a WorkflowGraph from workflow definition.

        Args:
            data: Workflow definition with nodes and edges
            backend_type: Backend implementation to use ("inmemory" or "networkx")

        Returns:
            WorkflowGraph instance

        """
        backend = cls._create_backend(backend_type)
        graph = cls(backend)
        graph._build_from_dict(data)

        validation_errors = graph.validate_structure()
        if validation_errors:
            msg = "Workflow graph validation failed:\n" + "\n".join(validation_errors)
            raise ValueError(msg)

        return graph

    @staticmethod
    def _create_backend(backend_type: str) -> IGraphBackend:
        """Create backend for the specified type."""
        if backend_type == "inmemory":
            return InMemoryGraphBackend()
        if backend_type == "networkx":
            # Import here to avoid hard dependency
            from syntara.workflows.workflow_engine.graph_backend_nx import (  # type: ignore[import-untyped]  # noqa: PLC0415
                NetworkXBackend,
            )

            return NetworkXBackend()  # type: ignore[no-any-return]
        msg = f"Unknown backend type: {backend_type}"
        raise ValueError(msg)

    def _build_from_dict(self, data: dict[str, Any]) -> None:
        """Build graph from workflow definition JSON."""
        # Store metadata
        self.metadata = {
            "schema_version": data.get("schema_version"),
            "name": data.get("name"),
            "description": data.get("description"),
        }

        # Add trigger nodes (separate array in v2)
        for trigger in data.get("triggers", []):
            self._backend.add_node(trigger["id"], trigger)

        # Add execution and control flow nodes
        for node in data.get("nodes", []):
            self._backend.add_node(node["id"], node)

        # Add all edges, filtering out loop feedback edges (to_port="iterate")
        # Loop feedback edges create cycles and are removed - last node in iterate path automatically loops back
        for edge in data["edges"]:
            # Skip loop feedback edges - they can be safely removed
            if edge.get("to_port") == "iterate":
                continue

            # Extract edge attributes (from_port, to_port, etc.)
            edge_data = {k: v for k, v in edge.items() if k not in ["from", "to"]}
            self._backend.add_edge(edge["from"], edge["to"], edge_data or None)

    # High-level workflow operations

    def get_trigger_nodes(self) -> list[ActivityNode]:
        """Get all trigger nodes (workflow entry points).

        Trigger nodes are identified by their type ending with '_trigger'.
        """
        all_nodes = self._backend.get_all_nodes()
        trigger_nodes = []
        for node_id in all_nodes:
            node_data = self._backend.get_node_data(node_id)
            if node_data["type"].endswith("_trigger"):
                trigger_nodes.append(self._to_activity_node(node_id))
        return trigger_nodes

    def get_node(self, node_id: str) -> ActivityNode:
        """Get a specific node by ID.

        Args:
            node_id: Unique node identifier

        Returns:
            ActivityNode instance

        Raises:
            KeyError: If node_id not found

        """
        return self._to_activity_node(node_id)

    def get_next_activities(self, current_id: str) -> list[ActivityNode]:
        """Get activities that can follow the current one.

        Args:
            current_id: Current activity node ID

        Returns:
            List of successor ActivityNodes

        """
        successor_ids = self._backend.get_successors(current_id)
        return [self._to_activity_node(sid) for sid in successor_ids]

    def get_next_activities_by_port(self, current_id: str, from_port: str | None = None) -> list[ActivityNode]:
        """Get activities that follow via specific port.

        Used for control flow nodes that have multiple output ports (condition, loop).

        Args:
            current_id: Current activity node ID
            from_port: Port to follow (e.g., "true", "false", "iterate", "complete")
                       If None, returns all successors (for non-control-flow nodes)

        Returns:
            List of successor ActivityNodes connected via the specified port

        """
        outgoing_edges = self._backend.get_outgoing_edges(current_id)

        if from_port is None:
            # No port filtering - return all successors
            successor_ids = [e["to"] for e in outgoing_edges]
        else:
            # Filter by from_port
            successor_ids = [e["to"] for e in outgoing_edges if e.get("from_port") == from_port]

        return [self._to_activity_node(sid) for sid in successor_ids]

    def has_successors(self, node_id: str) -> bool:
        """Check if node has any successor nodes."""
        return len(self._backend.get_successors(node_id)) > 0

    def get_predecessors(self, node_id: str) -> list[str]:
        """Get node IDs that have edges pointing to this node.

        Args:
            node_id: Node to find predecessors for

        Returns:
            List of predecessor node IDs

        """
        return self._backend.get_predecessors(node_id)

    def get_successors(self, node_id: str) -> list[str]:
        """Get node IDs directly reachable from this node (outgoing edges).

        Args:
            node_id: Node to find successors for

        Returns:
            List of successor node IDs

        """
        return self._backend.get_successors(node_id)

    def get_outgoing_edges(self, node_id: str) -> list[dict[str, Any]]:
        """Get all outgoing edges with their attributes.

        Args:
            node_id: Node to get outgoing edges for

        Returns:
            List of edge dicts with keys: from, to, from_port, to_port, etc.

        """
        return self._backend.get_outgoing_edges(node_id)

    def get_all_nodes(self) -> list[ActivityNode]:
        """Get all nodes in the workflow."""
        node_ids = self._backend.get_all_nodes()
        return [self._to_activity_node(nid) for nid in node_ids]

    def has_forward_path(self, from_node: str, to_node: str, blocked: set[str]) -> bool:
        """Check if a forward path exists from from_node to to_node, avoiding blocked nodes.

        Args:
            from_node: Starting node
            to_node: Target node
            blocked: Set of node IDs to treat as impassable

        Returns:
            True if a path exists that does not pass through any blocked node

        """
        if from_node == to_node:
            return True
        visited: set[str] = set()
        stack = [from_node]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            for succ in self._backend.get_successors(current):
                if succ == to_node:
                    return True
                if succ not in blocked:
                    stack.append(succ)
        return False

    # Validation operations

    def validate_structure(self) -> list[str]:
        """Validate graph structure and return list of errors.

        Checks for:
        - Edges referencing non-existent nodes
        - At least one trigger node exists
        - Orphan nodes (no incoming or outgoing edges, excluding trigger nodes)

        Returns:
            List of validation error messages (empty if valid)

        """
        errors: list[str] = []
        all_node_ids = set(self._backend.get_all_nodes())

        # Check edges reference existing nodes
        for node_id in all_node_ids:
            for edge in self._backend.get_outgoing_edges(node_id):
                target = edge["to"]
                if target not in all_node_ids:
                    errors.append(f"Edge from '{node_id}' references non-existent node '{target}'")

        # Check at least one trigger node exists
        trigger_nodes = self.get_trigger_nodes()
        if not trigger_nodes:
            errors.append("Graph must contain at least one trigger node")

        # Check for orphan nodes (no incoming or outgoing edges, excluding triggers)
        trigger_ids = {t.id for t in trigger_nodes}
        for node_id in all_node_ids:
            if node_id in trigger_ids:
                continue
            has_incoming = len(self._backend.get_predecessors(node_id)) > 0
            has_outgoing = len(self._backend.get_successors(node_id)) > 0
            if not has_incoming and not has_outgoing:
                errors.append(f"Orphan node '{node_id}' has no incoming or outgoing edges")

        return errors

    def _to_activity_node(self, node_id: str) -> ActivityNode:
        """Convert backend node to domain ActivityNode."""
        data = self._backend.get_node_data(node_id)
        return ActivityNode.from_dict(data)
