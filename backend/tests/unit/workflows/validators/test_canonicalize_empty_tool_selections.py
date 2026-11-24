"""Tests for canonicalize_empty_tool_selections.

Covers the syntactic pre-pass that rewrites agentic nodes stuck with
tool_selection_strategy="SELECTED" and no tool_selections (e.g. because no MCP
tools were available to pick) to the canonical "NONE" form, before schema
findings are collected.
"""

from typing import Any

from syntara.workflows.validators.workflow_definition import canonicalize_empty_tool_selections


def _definition(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "name": "test-workflow",
        "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
        "nodes": nodes,
        "edges": [],
    }


def _agentic_node(parameters: dict[str, Any], *, node_id: str = "agent_1") -> dict[str, Any]:
    return {"id": node_id, "type": "agentic", "name": "Task Agent", "parameters": parameters}


class TestCanonicalizesSelectedWithNoSelections:
    """SELECTED with missing or empty tool_selections is rewritten to NONE."""

    def test_missing_tool_selections_key_rewritten_to_none(self) -> None:
        definition = _definition([_agentic_node({"prompt": "test", "tool_selection_strategy": "SELECTED"})])

        changed = canonicalize_empty_tool_selections(definition)

        params = definition["nodes"][0]["parameters"]
        assert changed is True
        assert params["tool_selection_strategy"] == "NONE"
        assert "tool_selections" not in params

    def test_empty_tool_selections_list_rewritten_to_none(self) -> None:
        definition = _definition(
            [_agentic_node({"prompt": "test", "tool_selection_strategy": "SELECTED", "tool_selections": []})]
        )

        changed = canonicalize_empty_tool_selections(definition)

        params = definition["nodes"][0]["parameters"]
        assert changed is True
        assert params["tool_selection_strategy"] == "NONE"
        assert "tool_selections" not in params

    def test_mutates_definition_in_place(self) -> None:
        definition = _definition([_agentic_node({"prompt": "test", "tool_selection_strategy": "SELECTED"})])
        node_params = definition["nodes"][0]["parameters"]

        canonicalize_empty_tool_selections(definition)

        # Same dict object was mutated, not replaced.
        assert definition["nodes"][0]["parameters"] is node_params
        assert node_params["tool_selection_strategy"] == "NONE"


class TestLeavesCoherentConfigsUntouched:
    """Already-coherent strategy/selections combinations are never modified."""

    def test_selected_with_selections_untouched(self) -> None:
        definition = _definition(
            [
                _agentic_node(
                    {
                        "prompt": "test",
                        "tool_selection_strategy": "SELECTED",
                        "tool_selections": ["11111111-1111-1111-1111-111111111111"],
                    }
                )
            ]
        )

        changed = canonicalize_empty_tool_selections(definition)

        params = definition["nodes"][0]["parameters"]
        assert changed is False
        assert params["tool_selection_strategy"] == "SELECTED"
        assert params["tool_selections"] == ["11111111-1111-1111-1111-111111111111"]

    def test_all_strategy_untouched(self) -> None:
        definition = _definition([_agentic_node({"prompt": "test", "tool_selection_strategy": "ALL"})])

        changed = canonicalize_empty_tool_selections(definition)

        assert changed is False
        assert definition["nodes"][0]["parameters"]["tool_selection_strategy"] == "ALL"

    def test_none_strategy_untouched(self) -> None:
        definition = _definition([_agentic_node({"prompt": "test", "tool_selection_strategy": "NONE"})])

        changed = canonicalize_empty_tool_selections(definition)

        assert changed is False
        assert definition["nodes"][0]["parameters"]["tool_selection_strategy"] == "NONE"

    def test_absent_strategy_untouched(self) -> None:
        definition = _definition([_agentic_node({"prompt": "test"})])

        changed = canonicalize_empty_tool_selections(definition)

        assert changed is False
        assert "tool_selection_strategy" not in definition["nodes"][0]["parameters"]

    def test_template_strategy_untouched_even_with_no_selections(self) -> None:
        """Template expressions resolve at runtime — don't guess their value at save time."""
        definition = _definition([_agentic_node({"prompt": "test", "tool_selection_strategy": "${input.strategy}"})])

        changed = canonicalize_empty_tool_selections(definition)

        params = definition["nodes"][0]["parameters"]
        assert changed is False
        assert params["tool_selection_strategy"] == "${input.strategy}"
        assert "tool_selections" not in params

    def test_non_agentic_node_untouched(self) -> None:
        """Scoped to agentic nodes — coincidental same-named fields elsewhere are ignored."""
        definition = _definition(
            [
                {
                    "id": "n1",
                    "type": "script",
                    "name": "Step 1",
                    "parameters": {
                        "language": "python",
                        "code": "print(1)",
                        "tool_selection_strategy": "SELECTED",
                    },
                }
            ]
        )

        changed = canonicalize_empty_tool_selections(definition)

        assert changed is False
        assert definition["nodes"][0]["parameters"]["tool_selection_strategy"] == "SELECTED"


class TestMultipleNodesAndEdgeCases:
    """Only broken nodes change; malformed/missing shapes don't crash."""

    def test_only_broken_nodes_among_several_are_changed(self) -> None:
        definition = _definition(
            [
                _agentic_node({"prompt": "a", "tool_selection_strategy": "SELECTED"}, node_id="agent_1"),
                _agentic_node(
                    {
                        "prompt": "b",
                        "tool_selection_strategy": "SELECTED",
                        "tool_selections": ["11111111-1111-1111-1111-111111111111"],
                    },
                    node_id="agent_2",
                ),
                _agentic_node({"prompt": "c", "tool_selection_strategy": "NONE"}, node_id="agent_3"),
            ]
        )

        changed = canonicalize_empty_tool_selections(definition)

        nodes_by_id = {n["id"]: n["parameters"] for n in definition["nodes"]}
        assert changed is True
        assert nodes_by_id["agent_1"]["tool_selection_strategy"] == "NONE"
        assert "tool_selections" not in nodes_by_id["agent_1"]
        assert nodes_by_id["agent_2"]["tool_selection_strategy"] == "SELECTED"
        assert nodes_by_id["agent_2"]["tool_selections"] == ["11111111-1111-1111-1111-111111111111"]
        assert nodes_by_id["agent_3"]["tool_selection_strategy"] == "NONE"

    def test_no_nodes_key_does_not_crash(self) -> None:
        definition: dict[str, Any] = {"schema_version": "2.0.0", "name": "x", "triggers": [], "edges": []}

        changed = canonicalize_empty_tool_selections(definition)

        assert changed is False

    def test_empty_nodes_list_does_not_crash(self) -> None:
        definition = _definition([])

        changed = canonicalize_empty_tool_selections(definition)

        assert changed is False

    def test_node_with_missing_parameters_does_not_crash(self) -> None:
        definition = _definition([{"id": "agent_1", "type": "agentic", "name": "Task Agent"}])

        changed = canonicalize_empty_tool_selections(definition)

        assert changed is False

    def test_returns_false_when_nothing_to_change(self) -> None:
        definition = _definition([_agentic_node({"prompt": "test"})])

        assert canonicalize_empty_tool_selections(definition) is False
