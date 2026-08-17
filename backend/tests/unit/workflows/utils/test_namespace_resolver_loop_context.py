"""Unit tests for NamespaceResolver explicit loop context (Task 2.2).

Verifies that set_context(loop_node_id=...) replaces the old BFS-based
_find_upstream_loop, and that ${loop.item} / ${loop.index} resolve
correctly through the stored loop_node_id.
"""

from typing import Any

import pytest

from syntara.workflows.utils.namespace_resolver import NamespaceResolver


@pytest.fixture
def resolver() -> NamespaceResolver:
    """Create a NamespaceResolver with a loop namespace pre-loaded."""
    r = NamespaceResolver()
    # Simulate loop namespace structure: loop.{loop_node_id}.item / .index
    r.set_namespace(
        "loop",
        {
            "loop_1": {"item": "apple", "index": 0},
            "loop_2": {"item": "banana", "index": 1},
        },
    )
    return r


class TestSetContextLoopNodeId:
    """set_context must accept and store loop_node_id."""

    def test_set_context_stores_loop_node_id(self) -> None:
        r = NamespaceResolver()
        r.set_context(loop_node_id="loop_1")
        assert r._loop_node_id == "loop_1"

    def test_set_context_defaults_to_none(self) -> None:
        r = NamespaceResolver()
        r.set_context()
        assert r._loop_node_id is None

    def test_set_context_can_clear_loop_node_id(self) -> None:
        r = NamespaceResolver()
        r.set_context(loop_node_id="loop_1")
        r.set_context(loop_node_id=None)
        assert r._loop_node_id is None

    def test_set_context_overwrites_previous_value(self) -> None:
        r = NamespaceResolver()
        r.set_context(loop_node_id="loop_1")
        r.set_context(loop_node_id="loop_2")
        assert r._loop_node_id == "loop_2"

    def test_set_context_is_keyword_only(self) -> None:
        """loop_node_id must be passed as a keyword argument."""
        r = NamespaceResolver()
        with pytest.raises(TypeError):
            r.set_context("loop_1")  # type: ignore[misc]


class TestFindUpstreamLoopReturnsStoredValue:
    """_find_upstream_loop must return _loop_node_id directly."""

    def test_returns_none_when_no_context_set(self) -> None:
        r = NamespaceResolver()
        assert r._find_upstream_loop() is None

    def test_returns_loop_node_id_when_set(self) -> None:
        r = NamespaceResolver()
        r.set_context(loop_node_id="loop_42")
        assert r._find_upstream_loop() == "loop_42"

    def test_returns_none_after_clearing_context(self) -> None:
        r = NamespaceResolver()
        r.set_context(loop_node_id="loop_1")
        r.set_context(loop_node_id=None)
        assert r._find_upstream_loop() is None


class TestLoopItemResolution:
    """${loop.item} and ${loop.index} resolve via the stored loop_node_id."""

    def test_loop_item_resolves_with_context(self, resolver: NamespaceResolver) -> None:
        resolver.set_context(loop_node_id="loop_1")
        result = resolver.resolve_value("${loop.item}")
        assert result == "apple"

    def test_loop_index_resolves_with_context(self, resolver: NamespaceResolver) -> None:
        resolver.set_context(loop_node_id="loop_1")
        result = resolver.resolve_value("${loop.index}")
        assert result == 0

    def test_loop_item_resolves_to_different_loop(self, resolver: NamespaceResolver) -> None:
        """Changing loop_node_id should resolve to a different loop's data."""
        resolver.set_context(loop_node_id="loop_2")
        result = resolver.resolve_value("${loop.item}")
        assert result == "banana"

    def test_loop_index_resolves_to_different_loop(self, resolver: NamespaceResolver) -> None:
        resolver.set_context(loop_node_id="loop_2")
        result = resolver.resolve_value("${loop.index}")
        assert result == 1

    def test_loop_item_in_string_interpolation(self, resolver: NamespaceResolver) -> None:
        """${loop.item} inside a larger string should interpolate correctly."""
        resolver.set_context(loop_node_id="loop_1")
        result = resolver.resolve_value("item is ${loop.item}")
        # String values are NOT quoted - repr() removed since conditions use Tier 2
        assert result == "item is apple"

    def test_loop_item_in_dict_resolution(self, resolver: NamespaceResolver) -> None:
        """${loop.item} in a dict value should resolve during resolve_dict."""
        resolver.set_context(loop_node_id="loop_1")
        data: dict[str, Any] = {"current": "${loop.item}", "idx": "${loop.index}"}
        result = resolver.resolve_dict(data)
        assert result == {"current": "apple", "idx": 0}


class TestLoopResolutionWithoutContext:
    """${loop.*} when no loop_node_id is set should try direct namespace lookup."""

    def test_loop_item_without_context_raises_key_error(self) -> None:
        """When no loop_node_id is set, loop.item has no sub-namespace to find."""
        r = NamespaceResolver()
        r.set_namespace("loop", {"loop_1": {"item": "apple", "index": 0}})
        # No set_context → _find_upstream_loop returns None → no rewrite
        # So it tries loop.item directly, which doesn't exist
        with pytest.raises(KeyError):
            r.resolve_value("${loop.item}")

    def test_loop_without_namespace_raises_key_error(self) -> None:
        """When loop namespace itself doesn't exist, raise KeyError."""
        r = NamespaceResolver()
        r.set_context(loop_node_id="loop_1")
        with pytest.raises(KeyError, match="loop"):
            r.resolve_value("${loop.item}")


class TestGraphAndCurrentNodeRemoved:
    """The old _graph and _current_node fields should no longer exist."""

    def test_no_graph_attribute(self) -> None:
        r = NamespaceResolver()
        assert not hasattr(r, "_graph")

    def test_no_current_node_attribute(self) -> None:
        r = NamespaceResolver()
        assert not hasattr(r, "_current_node")

    def test_set_context_rejects_old_parameters(self) -> None:
        """set_context should not accept graph or current_node kwargs."""
        r = NamespaceResolver()
        with pytest.raises(TypeError):
            r.set_context(graph=None)  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            r.set_context(current_node="node_1")  # type: ignore[call-arg]


class TestLoopResolutionWithComplexData:
    """Loop items can be complex types (dicts, lists)."""

    def test_loop_item_resolves_to_dict(self) -> None:
        r = NamespaceResolver()
        r.set_namespace("loop", {"my_loop": {"item": {"name": "Alice", "age": 30}, "index": 0}})
        r.set_context(loop_node_id="my_loop")
        result = r.resolve_value("${loop.item}")
        assert result == {"name": "Alice", "age": 30}

    def test_loop_item_resolves_to_list(self) -> None:
        r = NamespaceResolver()
        r.set_namespace("loop", {"my_loop": {"item": [1, 2, 3], "index": 0}})
        r.set_context(loop_node_id="my_loop")
        result = r.resolve_value("${loop.item}")
        assert result == [1, 2, 3]

    def test_loop_item_nested_field_access(self) -> None:
        """${loop.item.name} should drill into the loop item's dict."""
        r = NamespaceResolver()
        r.set_namespace("loop", {"my_loop": {"item": {"name": "Alice"}, "index": 0}})
        r.set_context(loop_node_id="my_loop")
        result = r.resolve_value("${loop.item.name}")
        assert result == "Alice"


class TestLoopContextSwitching:
    """Simulate switching between different loop contexts (e.g., sequential loop nodes)."""

    def test_resolve_switches_with_context(self) -> None:
        r = NamespaceResolver()
        r.set_namespace(
            "loop",
            {
                "loop_a": {"item": "first", "index": 0},
                "loop_b": {"item": "second", "index": 1},
            },
        )

        r.set_context(loop_node_id="loop_a")
        assert r.resolve_value("${loop.item}") == "first"

        r.set_context(loop_node_id="loop_b")
        assert r.resolve_value("${loop.item}") == "second"

        # Clear context
        r.set_context(loop_node_id=None)
        with pytest.raises(KeyError):
            r.resolve_value("${loop.item}")
