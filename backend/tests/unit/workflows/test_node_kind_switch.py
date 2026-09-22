"""Tests for the node-kind kill switch helpers (ANSTRAT-1750, design 6b)."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import AsyncMock, patch

import pytest

from syntara.workflows import node_kind_switch
from syntara.workflows.node_kind_switch import (
    NODE_KIND_DISABLED_ERROR_CODE,
    disabled_nodes_in_definition,
    get_disabled_node_kinds,
    is_kind_switchable,
    next_disabled_kinds,
)
from syntara.workflows.node_kinds import NODE_KINDS


def _cache(value: Any) -> AsyncMock:  # noqa: ANN401
    cache = AsyncMock()
    cache.get_list = AsyncMock(return_value=value)
    return cache


class TestIsKindSwitchable:
    """Only trigger and action kinds may be switched off."""

    @pytest.mark.parametrize("kind", ["script", "http_request", "manual_trigger", "agentic"])
    def test_switchable_kinds(self, kind: str) -> None:
        assert is_kind_switchable(kind) is True

    @pytest.mark.parametrize("kind", ["condition", "converge", "loop", "switch", "wait", "permission_check"])
    def test_flow_control_is_never_switchable(self, kind: str) -> None:
        assert is_kind_switchable(kind) is False

    def test_unknown_kind_is_not_switchable(self) -> None:
        assert is_kind_switchable("not_a_kind") is False


class TestGetDisabledNodeKinds:
    """The setting is read through the Redis-backed settings cache."""

    async def test_empty_when_unset(self) -> None:
        with patch.object(node_kind_switch, "get_runtime_settings", return_value=_cache([])):
            assert await get_disabled_node_kinds() == frozenset()

    async def test_returns_configured_kinds(self) -> None:
        with patch.object(node_kind_switch, "get_runtime_settings", return_value=_cache(["script", "agentic"])):
            assert await get_disabled_node_kinds() == frozenset({"script", "agentic"})

    async def test_drops_unswitchable_and_unknown_entries(self) -> None:
        """A stale or hand-edited value cannot disable flow control."""
        stored = ["script", "condition", "permission_check", "not_a_kind", 7]
        with patch.object(node_kind_switch, "get_runtime_settings", return_value=_cache(stored)):
            assert await get_disabled_node_kinds() == frozenset({"script"})


class TestNextDisabledKinds:
    """Flipping one kind produces a registry-ordered list."""

    def test_disable_adds_the_kind(self) -> None:
        assert next_disabled_kinds([], "script", enabled=False) == ["script"]

    def test_enable_removes_the_kind(self) -> None:
        assert next_disabled_kinds(["script", "agentic"], "script", enabled=True) == ["agentic"]

    def test_disable_is_idempotent(self) -> None:
        assert next_disabled_kinds(["script"], "script", enabled=False) == ["script"]

    def test_enable_of_an_absent_kind_is_a_no_op(self) -> None:
        assert next_disabled_kinds(["agentic"], "script", enabled=True) == ["agentic"]

    def test_result_follows_registry_order(self) -> None:
        result = next_disabled_kinds(["script", "manual_trigger"], "http_request", enabled=False)
        order = [info.kind for info in NODE_KINDS]
        assert result == sorted(result, key=order.index)
        assert result == ["manual_trigger", "http_request", "script"]

    def test_unswitchable_entries_are_dropped(self) -> None:
        assert next_disabled_kinds(["condition"], "script", enabled=False) == ["script"]


class TestDisabledNodesInDefinition:
    """Locating the offending nodes inside a definition."""

    _DEFINITION: ClassVar[dict[str, Any]] = {
        "nodes": [
            {"id": "a", "type": "script"},
            {"id": "b", "type": "http_request"},
            {"id": "c", "type": "script"},
            "not-a-node",
        ]
    }

    def test_finds_every_matching_node(self) -> None:
        assert disabled_nodes_in_definition(self._DEFINITION, frozenset({"script"})) == [
            ("a", "script"),
            ("c", "script"),
        ]

    def test_empty_when_nothing_disabled(self) -> None:
        assert disabled_nodes_in_definition(self._DEFINITION, frozenset()) == []

    def test_empty_for_missing_definition(self) -> None:
        assert disabled_nodes_in_definition(None, frozenset({"script"})) == []


def test_error_code_is_stable() -> None:
    """The error code is a stable contract shared with launch and activity start."""
    assert NODE_KIND_DISABLED_ERROR_CODE == "node_kind_disabled"
