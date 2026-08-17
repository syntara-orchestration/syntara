"""Workflow definition diffing for automatic change summaries.

Compares two workflow definitions and produces a structured summary
of changes (nodes added/removed/modified, edges added/removed).
"""

from typing import Any


def _build_node_map(definition: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build a mapping of node id -> node dict from a workflow definition."""
    return {node["id"]: node for node in definition.get("nodes", []) if "id" in node}


def _build_edge_set(definition: dict[str, Any]) -> set[tuple[str, str]]:
    """Build a set of (from, to) tuples from a workflow definition's edges."""
    return {(edge["from"], edge["to"]) for edge in definition.get("edges", []) if "from" in edge and "to" in edge}


def generate_change_summary(
    old_definition: dict[str, Any] | None,
    new_definition: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Generate a structured summary of changes between two workflow definitions.

    Args:
        old_definition: The previous workflow definition dict.
        new_definition: The new workflow definition dict.

    Returns:
        A dict with nodes_added, nodes_removed, nodes_modified,
        edges_added, and edges_removed lists, or None if no changes.

    """
    if old_definition is None or new_definition is None:
        return None

    old_nodes = _build_node_map(old_definition)
    new_nodes = _build_node_map(new_definition)

    nodes_added = [
        {"id": node_id, "type": new_nodes[node_id].get("type", "unknown")}
        for node_id in sorted(new_nodes.keys() - old_nodes.keys())
    ]

    nodes_removed = [
        {"id": node_id, "type": old_nodes[node_id].get("type", "unknown")}
        for node_id in sorted(old_nodes.keys() - new_nodes.keys())
    ]

    nodes_modified = [
        {"id": node_id, "type": new_nodes[node_id].get("type", "unknown")}
        for node_id in sorted(old_nodes.keys() & new_nodes.keys())
        if old_nodes[node_id] != new_nodes[node_id]
    ]

    old_edges = _build_edge_set(old_definition)
    new_edges = _build_edge_set(new_definition)

    edges_added = [f"{from_id} -> {to_id}" for from_id, to_id in sorted(new_edges - old_edges)]
    edges_removed = [f"{from_id} -> {to_id}" for from_id, to_id in sorted(old_edges - new_edges)]

    if not any([nodes_added, nodes_removed, nodes_modified, edges_added, edges_removed]):
        return None

    return {
        "nodes_added": nodes_added,
        "nodes_removed": nodes_removed,
        "nodes_modified": nodes_modified,
        "edges_added": edges_added,
        "edges_removed": edges_removed,
    }
