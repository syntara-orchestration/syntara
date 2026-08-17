"""Unit tests for used_tools aggregation (AAP-66977 T072)."""

from __future__ import annotations

from types import SimpleNamespace

from syntara.agent_orchestrator.utils.used_tools import aggregate_used_tools


class TestAggregateUsedTools:
    """Tests for aggregate_used_tools counting tool calls across messages."""

    def test_empty_messages(self) -> None:
        assert aggregate_used_tools(None) == []
        assert aggregate_used_tools([]) == []

    def test_counts_tool_names_across_messages(self) -> None:
        messages = [
            SimpleNamespace(tool_calls=[{"name": "search", "id": "1"}, {"name": "search", "id": "2"}]),
            SimpleNamespace(tool_calls=[{"name": "fetch", "id": "3"}]),
            SimpleNamespace(tool_calls=None),
            SimpleNamespace(),  # no tool_calls attr
        ]
        assert aggregate_used_tools(messages) == [
            {"name": "fetch", "count": 1},
            {"name": "search", "count": 2},
        ]

    def test_supports_object_style_tool_calls(self) -> None:
        messages = [SimpleNamespace(tool_calls=[SimpleNamespace(name="lookup")])]
        assert aggregate_used_tools(messages) == [{"name": "lookup", "count": 1}]

    def test_ignores_blank_names(self) -> None:
        messages = [SimpleNamespace(tool_calls=[{"name": ""}, {"name": None}, {}])]
        assert aggregate_used_tools(messages) == []
