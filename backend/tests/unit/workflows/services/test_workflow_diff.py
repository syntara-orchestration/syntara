"""Unit tests for workflow definition diffing (change summary generation).

Covers acceptance criteria for AAP-77452:
  AC1: Node added
  AC2: Node removed
  AC3: Node config modified
  AC4: Edge added/removed
"""

from typing import Any

from syntara.workflows.services.workflow_diff import generate_change_summary


def _make_definition(
    nodes: list[dict[str, Any]] | None = None,
    edges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a minimal workflow definition for testing."""
    return {
        "schema_version": "2.0.0",
        "name": "test-workflow",
        "description": "Test workflow",
        "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
        "nodes": nodes or [],
        "edges": edges or [],
    }


class TestGenerateChangeSummary:
    """Tests for the generate_change_summary function."""

    def test_no_changes(self) -> None:
        definition = _make_definition(
            nodes=[{"id": "n1", "type": "script", "parameters": {}}],
            edges=[{"from": "trigger_manual", "to": "n1"}],
        )
        assert generate_change_summary(definition, definition) is None

    def test_node_added(self) -> None:
        """AC1: Added node includes id and type."""
        old = _make_definition(nodes=[])
        new = _make_definition(
            nodes=[{"id": "http_node", "type": "http_request", "parameters": {"url": "https://example.com"}}],
        )
        result = generate_change_summary(old, new)
        assert result is not None
        assert {"id": "http_node", "type": "http_request"} in result["nodes_added"]

    def test_multiple_nodes_added(self) -> None:
        old = _make_definition(nodes=[])
        new = _make_definition(
            nodes=[
                {"id": "node_a", "type": "script", "parameters": {}},
                {"id": "node_b", "type": "approval", "parameters": {}},
            ],
        )
        result = generate_change_summary(old, new)
        assert result is not None
        assert {"id": "node_a", "type": "script"} in result["nodes_added"]
        assert {"id": "node_b", "type": "approval"} in result["nodes_added"]

    def test_node_removed(self) -> None:
        """AC2: Removed node includes id and type."""
        old = _make_definition(
            nodes=[{"id": "old_node", "type": "condition", "parameters": {}}],
        )
        new = _make_definition(nodes=[])
        result = generate_change_summary(old, new)
        assert result is not None
        assert {"id": "old_node", "type": "condition"} in result["nodes_removed"]

    def test_node_modified(self) -> None:
        """AC3: Modified node includes id and type."""
        old = _make_definition(
            nodes=[{"id": "api_call", "type": "http_request", "parameters": {"url": "https://old.example.com"}}],
        )
        new = _make_definition(
            nodes=[{"id": "api_call", "type": "http_request", "parameters": {"url": "https://new.example.com"}}],
        )
        result = generate_change_summary(old, new)
        assert result is not None
        assert {"id": "api_call", "type": "http_request"} in result["nodes_modified"]
        assert result["nodes_added"] == []
        assert result["nodes_removed"] == []

    def test_edge_added(self) -> None:
        """AC4: Added edge as 'from -> to' string."""
        old = _make_definition(
            nodes=[
                {"id": "n1", "type": "script", "parameters": {}},
                {"id": "n2", "type": "script", "parameters": {}},
            ],
            edges=[],
        )
        new = _make_definition(
            nodes=[
                {"id": "n1", "type": "script", "parameters": {}},
                {"id": "n2", "type": "script", "parameters": {}},
            ],
            edges=[{"from": "n1", "to": "n2"}],
        )
        result = generate_change_summary(old, new)
        assert result is not None
        assert "n1 -> n2" in result["edges_added"]

    def test_edge_removed(self) -> None:
        """AC4: Removed edge as 'from -> to' string."""
        old = _make_definition(
            nodes=[
                {"id": "n1", "type": "script", "parameters": {}},
                {"id": "n2", "type": "script", "parameters": {}},
            ],
            edges=[{"from": "n1", "to": "n2"}],
        )
        new = _make_definition(
            nodes=[
                {"id": "n1", "type": "script", "parameters": {}},
                {"id": "n2", "type": "script", "parameters": {}},
            ],
            edges=[],
        )
        result = generate_change_summary(old, new)
        assert result is not None
        assert "n1 -> n2" in result["edges_removed"]

    def test_combined_changes(self) -> None:
        old = _make_definition(
            nodes=[
                {"id": "keep", "type": "script", "parameters": {"code": "v1"}},
                {"id": "remove_me", "type": "wait", "parameters": {}},
            ],
            edges=[{"from": "trigger_manual", "to": "keep"}, {"from": "keep", "to": "remove_me"}],
        )
        new = _make_definition(
            nodes=[
                {"id": "keep", "type": "script", "parameters": {"code": "v2"}},
                {"id": "new_node", "type": "approval", "parameters": {}},
            ],
            edges=[{"from": "trigger_manual", "to": "keep"}, {"from": "keep", "to": "new_node"}],
        )
        result = generate_change_summary(old, new)
        assert result is not None
        assert {"id": "new_node", "type": "approval"} in result["nodes_added"]
        assert {"id": "remove_me", "type": "wait"} in result["nodes_removed"]
        assert {"id": "keep", "type": "script"} in result["nodes_modified"]
        assert "keep -> new_node" in result["edges_added"]
        assert "keep -> remove_me" in result["edges_removed"]

    def test_empty_definitions(self) -> None:
        assert generate_change_summary({}, {}) is None

    def test_node_with_missing_type(self) -> None:
        old = _make_definition(nodes=[])
        new = _make_definition(nodes=[{"id": "no_type_node"}])
        result = generate_change_summary(old, new)
        assert result is not None
        assert {"id": "no_type_node", "type": "unknown"} in result["nodes_added"]

    def test_results_are_sorted(self) -> None:
        old = _make_definition(nodes=[])
        new = _make_definition(
            nodes=[
                {"id": "z_node", "type": "script", "parameters": {}},
                {"id": "a_node", "type": "script", "parameters": {}},
            ],
        )
        result = generate_change_summary(old, new)
        assert result is not None
        assert result["nodes_added"][0]["id"] == "a_node"
        assert result["nodes_added"][1]["id"] == "z_node"

    def test_all_keys_present(self) -> None:
        old = _make_definition(nodes=[])
        new = _make_definition(nodes=[{"id": "n1", "type": "script", "parameters": {}}])
        result = generate_change_summary(old, new)
        assert result is not None
        assert set(result.keys()) == {"nodes_added", "nodes_removed", "nodes_modified", "edges_added", "edges_removed"}
