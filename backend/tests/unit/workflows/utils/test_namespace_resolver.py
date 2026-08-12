"""Tests for NamespaceResolver core functionality (task 6.1).

Tests cover:
- resolve_value with single and multiple templates
- resolve_dict with nested dicts, lists, and lists-of-dicts
- _lookup_path with dotted paths
- Loop namespace resolution via set_context
"""

from typing import Any

import pytest

from syntara.workflows.utils.namespace_resolver import NamespaceResolver

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def resolver() -> NamespaceResolver:
    """Resolver with trigger and node1 namespaces loaded."""
    r = NamespaceResolver()
    r.set_namespace("trigger", {"url": "https://api.example.com", "method": "POST", "count": 3})
    r.set_namespace("node1", {"output": {"status": "ok", "items": [1, 2, 3]}})
    return r


# ---------------------------------------------------------------------------
# resolve_value — single template
# ---------------------------------------------------------------------------


class TestResolveValueSingle:
    """resolve_value with a single template expression."""

    def test_full_template_returns_typed_value(self, resolver: NamespaceResolver) -> None:
        assert resolver.resolve_value("${trigger.count}") == 3
        assert isinstance(resolver.resolve_value("${trigger.count}"), int)

    def test_full_template_returns_string(self, resolver: NamespaceResolver) -> None:
        assert resolver.resolve_value("${trigger.url}") == "https://api.example.com"

    def test_full_template_returns_dict(self, resolver: NamespaceResolver) -> None:
        result = resolver.resolve_value("${node1.output}")
        assert result == {"status": "ok", "items": [1, 2, 3]}

    def test_full_template_returns_list(self, resolver: NamespaceResolver) -> None:
        result = resolver.resolve_value("${node1.output.items}")
        assert result == [1, 2, 3]

    def test_non_string_passthrough(self, resolver: NamespaceResolver) -> None:
        assert resolver.resolve_value(42) == 42
        assert resolver.resolve_value(None) is None
        bool_value = True
        assert resolver.resolve_value(bool_value) is bool_value

    def test_no_template_string_passthrough(self, resolver: NamespaceResolver) -> None:
        assert resolver.resolve_value("plain text") == "plain text"


# ---------------------------------------------------------------------------
# resolve_value — multiple templates
# ---------------------------------------------------------------------------


class TestResolveValueMultiple:
    """resolve_value with multiple template expressions in one string."""

    def test_two_templates_in_string(self, resolver: NamespaceResolver) -> None:
        result = resolver.resolve_value("${trigger.method} ${trigger.url}")
        # String values are NOT quoted - repr() removed since conditions use Tier 2
        assert result == "POST https://api.example.com"

    def test_template_with_surrounding_text(self, resolver: NamespaceResolver) -> None:
        result = resolver.resolve_value("Send ${trigger.method} to ${trigger.url}")
        # String values are NOT quoted - repr() removed since conditions use Tier 2
        assert result == "Send POST to https://api.example.com"

    def test_non_string_coerced_to_str_in_mixed(self, resolver: NamespaceResolver) -> None:
        result = resolver.resolve_value("count=${trigger.count}")
        assert result == "count=3"

    def test_missing_namespace_raises(self, resolver: NamespaceResolver) -> None:
        with pytest.raises(KeyError, match="unknown"):
            resolver.resolve_value("${unknown.field}")

    def test_string_template_in_mixed_expression(self, resolver: NamespaceResolver) -> None:
        """String values in mixed expressions are converted with str() (no quotes).

        NOTE: Conditions don't use resolve_value() - they use safe_eval_with_namespace().
        This test verifies resolve_value() behavior for non-condition use cases (e.g., output mappings).
        """
        resolver.set_namespace("trigger", {"status": "completed"})

        # Template within comparison expression
        result = resolver.resolve_value('${trigger.status} == "completed"')

        # str() conversion (no repr() quoting)
        assert result == 'completed == "completed"'

    def test_numeric_template_in_condition_no_quotes(self, resolver: NamespaceResolver) -> None:
        """Numeric values should not be quoted."""
        resolver.set_namespace("input", {"age": 25})

        result = resolver.resolve_value("${input.age} >= 18")

        # Numbers should remain unquoted
        assert result == "25 >= 18"

    def test_boolean_template_in_condition(self, resolver: NamespaceResolver) -> None:
        """Boolean values should remain as True/False strings."""
        resolver.set_namespace("config", {"enabled": True})

        result = resolver.resolve_value("${config.enabled} == True")

        assert result == "True == True"


# ---------------------------------------------------------------------------
# resolve_dict — nested dicts
# ---------------------------------------------------------------------------


class TestResolveDictNested:
    """resolve_dict with nested dictionary structures."""

    def test_flat_dict(self, resolver: NamespaceResolver) -> None:
        data: dict[str, Any] = {"url": "${trigger.url}", "method": "${trigger.method}"}
        result = resolver.resolve_dict(data)
        assert result == {"url": "https://api.example.com", "method": "POST"}

    def test_nested_dict(self, resolver: NamespaceResolver) -> None:
        data: dict[str, Any] = {"parameters": {"endpoint": "${trigger.url}"}}
        result = resolver.resolve_dict(data)
        assert result == {"parameters": {"endpoint": "https://api.example.com"}}

    def test_deeply_nested_dict(self, resolver: NamespaceResolver) -> None:
        data: dict[str, Any] = {"a": {"b": {"c": "${trigger.url}"}}}
        result = resolver.resolve_dict(data)
        assert result == {"a": {"b": {"c": "https://api.example.com"}}}

    def test_mixed_template_and_static(self, resolver: NamespaceResolver) -> None:
        data: dict[str, Any] = {"url": "${trigger.url}", "static": "hello", "num": 42}
        result = resolver.resolve_dict(data)
        assert result == {"url": "https://api.example.com", "static": "hello", "num": 42}

    def test_returns_new_dict(self, resolver: NamespaceResolver) -> None:
        data: dict[str, Any] = {"url": "${trigger.url}"}
        result = resolver.resolve_dict(data)
        assert result is not data


# ---------------------------------------------------------------------------
# resolve_dict — lists and lists-of-dicts
# ---------------------------------------------------------------------------


class TestResolveDictLists:
    """resolve_dict with lists containing templates."""

    def test_list_of_strings(self, resolver: NamespaceResolver) -> None:
        data: dict[str, Any] = {"urls": ["${trigger.url}", "static"]}
        result = resolver.resolve_dict(data)
        assert result["urls"] == ["https://api.example.com", "static"]

    def test_list_of_dicts(self, resolver: NamespaceResolver) -> None:
        data: dict[str, Any] = {
            "items": [
                {"url": "${trigger.url}"},
                {"method": "${trigger.method}"},
            ],
        }
        result = resolver.resolve_dict(data)
        assert result["items"] == [
            {"url": "https://api.example.com"},
            {"method": "POST"},
        ]

    def test_nested_list_of_lists(self, resolver: NamespaceResolver) -> None:
        data: dict[str, Any] = {"matrix": [["${trigger.url}"]]}
        result = resolver.resolve_dict(data)
        assert result["matrix"] == [["https://api.example.com"]]

    def test_empty_dict(self, resolver: NamespaceResolver) -> None:
        assert resolver.resolve_dict({}) == {}


# ---------------------------------------------------------------------------
# _lookup_path — dotted paths
# ---------------------------------------------------------------------------


class TestLookupPath:
    """Tests for _lookup_path with dotted namespace paths."""

    def test_single_level(self, resolver: NamespaceResolver) -> None:
        result = resolver._lookup_path("trigger.url")
        assert result == "https://api.example.com"

    def test_two_level_path(self, resolver: NamespaceResolver) -> None:
        result = resolver._lookup_path("node1.output.status")
        assert result == "ok"

    def test_three_level_path(self, resolver: NamespaceResolver) -> None:
        """Access list via dotted path on dict."""
        result = resolver._lookup_path("node1.output.items")
        assert result == [1, 2, 3]

    def test_missing_namespace_raises(self, resolver: NamespaceResolver) -> None:
        with pytest.raises(KeyError, match="Namespace"):
            resolver._lookup_path("unknown.field")

    def test_missing_key_in_namespace_raises(self, resolver: NamespaceResolver) -> None:
        with pytest.raises(KeyError):
            resolver._lookup_path("trigger.nonexistent")


# ---------------------------------------------------------------------------
# Loop namespace resolution via set_context
# ---------------------------------------------------------------------------


class TestLoopResolution:
    """Loop namespace resolution using set_context."""

    def test_loop_item_resolves_with_context(self) -> None:
        r = NamespaceResolver()
        r.set_namespace("loop", {"my_loop": {"item": "apple", "index": 0}})
        r.set_context(loop_node_id="my_loop")
        assert r.resolve_value("${loop.item}") == "apple"

    def test_loop_index_resolves_with_context(self) -> None:
        r = NamespaceResolver()
        r.set_namespace("loop", {"my_loop": {"item": "apple", "index": 2}})
        r.set_context(loop_node_id="my_loop")
        assert r.resolve_value("${loop.index}") == 2

    def test_loop_without_context_uses_direct_path(self) -> None:
        r = NamespaceResolver()
        r.set_namespace("loop", {"item": "direct_value"})
        # No set_context → no rewrite, so loop.item resolves directly
        assert r.resolve_value("${loop.item}") == "direct_value"

    def test_loop_context_switching(self) -> None:
        r = NamespaceResolver()
        r.set_namespace(
            "loop",
            {
                "loop_a": {"item": "first"},
                "loop_b": {"item": "second"},
            },
        )
        r.set_context(loop_node_id="loop_a")
        assert r.resolve_value("${loop.item}") == "first"
        r.set_context(loop_node_id="loop_b")
        assert r.resolve_value("${loop.item}") == "second"

    def test_loop_in_resolve_dict(self) -> None:
        r = NamespaceResolver()
        r.set_namespace("loop", {"lp": {"item": {"name": "test"}, "index": 0}})
        r.set_context(loop_node_id="lp")
        data: dict[str, Any] = {"current": "${loop.item}", "idx": "${loop.index}"}
        result = r.resolve_dict(data)
        assert result == {"current": {"name": "test"}, "idx": 0}


# ---------------------------------------------------------------------------
# Namespace management
# ---------------------------------------------------------------------------


class TestNamespaceManagement:
    """Tests for set_namespace, has_namespace, remove_namespace, get_namespace."""

    def test_has_namespace(self) -> None:
        r = NamespaceResolver()
        r.set_namespace("ns", {"key": "val"})
        assert r.has_namespace("ns") is True
        assert r.has_namespace("other") is False

    def test_remove_namespace(self) -> None:
        r = NamespaceResolver()
        r.set_namespace("ns", {"key": "val"})
        r.remove_namespace("ns")
        assert r.has_namespace("ns") is False

    def test_remove_nonexistent_namespace_no_error(self) -> None:
        r = NamespaceResolver()
        r.remove_namespace("nope")  # should not raise

    def test_get_namespace(self) -> None:
        r = NamespaceResolver()
        r.set_namespace("ns", {"key": "val"})
        assert r.get_namespace("ns") == {"key": "val"}

    def test_get_nonexistent_namespace_raises(self) -> None:
        r = NamespaceResolver()
        with pytest.raises(KeyError):
            r.get_namespace("missing")

    def test_get_all_namespaces(self) -> None:
        r = NamespaceResolver()
        r.set_namespace("a", {"x": 1})
        r.set_namespace("b", {"y": 2})
        all_ns = r.get_all_namespaces()
        assert set(all_ns.keys()) == {"a", "b"}


# ---------------------------------------------------------------------------
# Edge cases and error paths
# ---------------------------------------------------------------------------


class TestNamespaceResolverEdgeCases:
    """Edge cases and unhappy paths for NamespaceResolver."""

    def test_namespace_only_resolution(self) -> None:
        """${trigger} with no dot returns the entire namespace dict."""
        r = NamespaceResolver()
        r.set_namespace("trigger", {"url": "http://test.com", "method": "GET"})
        result = r.resolve_value("${trigger}")
        assert result == {"url": "http://test.com", "method": "GET"}

    def test_resolve_value_empty_string(self) -> None:
        r = NamespaceResolver()
        assert r.resolve_value("") == ""

    def test_resolve_dict_preserves_non_template_types(self) -> None:
        """Non-string values (int, bool, None) pass through resolve_dict."""
        r = NamespaceResolver()
        data: dict[str, Any] = {"a": 42, "b": True, "c": None, "d": [1, 2]}
        result = r.resolve_dict(data)
        assert result == {"a": 42, "b": True, "c": None, "d": [1, 2]}

    def test_loop_context_reset_to_none(self) -> None:
        """Clearing loop context reverts to direct path resolution."""
        r = NamespaceResolver()
        r.set_namespace("loop", {"my_loop": {"item": "apple"}, "item": "direct"})
        r.set_context(loop_node_id="my_loop")
        assert r.resolve_value("${loop.item}") == "apple"
        r.set_context(loop_node_id=None)
        assert r.resolve_value("${loop.item}") == "direct"

    def test_missing_key_deep_in_path_raises(self) -> None:
        """KeyError when intermediate key is missing in a multi-level path."""
        r = NamespaceResolver()
        r.set_namespace("node", {"output": {"a": 1}})
        with pytest.raises(KeyError):
            r._lookup_path("node.output.nonexistent")

    def test_set_namespace_overwrites(self) -> None:
        """Setting the same namespace twice replaces the old data."""
        r = NamespaceResolver()
        r.set_namespace("ns", {"old": True})
        r.set_namespace("ns", {"new": True})
        assert r.get_namespace("ns") == {"new": True}


# ---------------------------------------------------------------------------
# String edge cases for repr() quoting
# ---------------------------------------------------------------------------


class TestStringReprEdgeCases:
    """Test str() behavior for edge cases in string template resolution.

    NOTE: These tests verify resolve_value() behavior which uses str() conversion.
    Conditions use safe_eval_with_namespace() and don't call resolve_value().
    """

    def test_string_with_single_quote(self) -> None:
        """Strings containing single quotes are converted with str() (no escaping)."""
        r = NamespaceResolver()
        r.set_namespace("data", {"message": "it's working"})

        result = r.resolve_value('${data.message} == "it\'s working"')

        # str() conversion (no repr() quoting)
        assert result == "it's working == \"it's working\""

    def test_string_with_double_quote_in_expression(self) -> None:
        """Strings containing double quotes are converted with str() (no escaping)."""
        r = NamespaceResolver()
        r.set_namespace("data", {"greeting": 'say "hello"'})

        # When embedded in expression, str() conversion is used
        result = r.resolve_value("prefix ${data.greeting} suffix")

        # str() conversion (no repr() quoting)
        assert result == 'prefix say "hello" suffix'

    def test_string_with_newline_in_expression(self) -> None:
        """Strings with newlines are converted with str() (preserves actual newline)."""
        r = NamespaceResolver()
        r.set_namespace("data", {"multiline": "line1\nline2"})

        # When embedded in expression, str() conversion preserves newlines
        result = r.resolve_value("text: ${data.multiline}")

        # str() preserves actual newline character
        assert result == "text: line1\nline2"

    def test_string_with_backslash_in_expression(self) -> None:
        """Strings with backslashes are converted with str() (preserves backslashes)."""
        r = NamespaceResolver()
        r.set_namespace("data", {"path": "path\\to\\file"})

        # When embedded in expression, str() conversion preserves backslashes
        result = r.resolve_value("path: ${data.path}")

        # str() preserves actual backslash characters
        assert result == "path: path\\to\\file"

    def test_empty_string_in_expression(self) -> None:
        """Empty strings are converted with str() (no quoting)."""
        r = NamespaceResolver()
        r.set_namespace("data", {"empty": ""})

        result = r.resolve_value('${data.empty} == ""')

        # str() conversion of empty string (no repr() quoting)
        assert result == ' == ""'

    def test_string_with_tab_in_expression(self) -> None:
        """Strings with tabs are converted with str() (preserves actual tab)."""
        r = NamespaceResolver()
        r.set_namespace("data", {"tabbed": "col1\tcol2"})

        # When embedded in expression, str() conversion preserves tabs
        result = r.resolve_value("data: ${data.tabbed}")

        # str() preserves actual tab character
        assert result == "data: col1\tcol2"

    def test_full_template_returns_raw_string(self) -> None:
        """Full template ${var} returns raw value, not repr()."""
        r = NamespaceResolver()
        r.set_namespace("data", {"message": "it's working"})

        # Full template returns the raw string value
        result = r.resolve_value("${data.message}")

        # Returns raw string, not quoted
        assert result == "it's working"


# ---------------------------------------------------------------------------
# Non-string types in expressions
# ---------------------------------------------------------------------------


class TestNonStringTypesInExpressions:
    """Test how non-string types are handled in template resolution."""

    def test_list_full_template_returns_raw_list(self) -> None:
        """Full template ${var} with list returns the raw list object."""
        r = NamespaceResolver()
        r.set_namespace("data", {"items": [1, 2, 3]})

        # Full template returns typed value
        result = r.resolve_value("${data.items}")

        # Returns the list itself, not a string
        assert result == [1, 2, 3]
        assert isinstance(result, list)

    def test_list_in_embedded_expression(self) -> None:
        """Lists embedded in expressions are converted with str()."""
        r = NamespaceResolver()
        r.set_namespace("data", {"items": [1, 2, 3]})

        # Embedded in text, converted to string
        result = r.resolve_value("items: ${data.items}")

        assert result == "items: [1, 2, 3]"

    def test_dict_full_template_returns_raw_dict(self) -> None:
        """Full template ${var} with dict returns the raw dict object."""
        r = NamespaceResolver()
        r.set_namespace("data", {"parameters": {"key": "value"}})

        # Full template returns typed value
        result = r.resolve_value("${data.parameters}")

        # Returns the dict itself, not a string
        assert result == {"key": "value"}
        assert isinstance(result, dict)

    def test_dict_in_embedded_expression(self) -> None:
        """Dicts embedded in expressions are converted with str()."""
        r = NamespaceResolver()
        r.set_namespace("data", {"parameters": {"key": "value"}})

        # Embedded in text, converted to string
        result = r.resolve_value("parameters: ${data.parameters}")

        assert result == "parameters: {'key': 'value'}"

    def test_none_in_expression(self) -> None:
        """None should be converted to string 'None' in expressions."""
        r = NamespaceResolver()
        r.set_namespace("data", {"empty": None})

        result = r.resolve_value("${data.empty} is None")

        assert result == "None is None"

    def test_boolean_true_in_expression(self) -> None:
        """Boolean True should be converted to 'True' string in expressions."""
        r = NamespaceResolver()
        r.set_namespace("data", {"flag": True})

        result = r.resolve_value("${data.flag} is True")

        assert result == "True is True"

    def test_boolean_false_in_expression(self) -> None:
        """Boolean False should be converted to 'False' string in expressions."""
        r = NamespaceResolver()
        r.set_namespace("data", {"flag": False})

        result = r.resolve_value("${data.flag} is False")

        assert result == "False is False"

    def test_float_in_expression(self) -> None:
        """Float values should be converted to string without quotes in expressions."""
        r = NamespaceResolver()
        r.set_namespace("data", {"score": 98.5})

        result = r.resolve_value("${data.score} > 90.0")

        assert result == "98.5 > 90.0"

    def test_zero_in_expression(self) -> None:
        """Zero should be handled correctly in expressions."""
        r = NamespaceResolver()
        r.set_namespace("data", {"count": 0})

        result = r.resolve_value("${data.count} == 0")

        assert result == "0 == 0"


# ---------------------------------------------------------------------------
# Complex nested structures
# ---------------------------------------------------------------------------


class TestNestedStructuresInExpressions:
    """Test nested data structures in template resolution."""

    def test_list_of_strings_full_template(self) -> None:
        """Full template with list returns the raw list."""
        r = NamespaceResolver()
        r.set_namespace("data", {"tags": ["active", "verified"]})

        # Full template returns typed value
        result = r.resolve_value("${data.tags}")

        # Returns the list itself
        assert result == ["active", "verified"]
        assert isinstance(result, list)

    def test_list_of_strings_in_embedded_expression(self) -> None:
        """List embedded in expression converts to string."""
        r = NamespaceResolver()
        r.set_namespace("data", {"tags": ["active", "verified"]})

        # Embedded in text
        result = r.resolve_value("tags: ${data.tags}")

        # String representation includes inner quotes
        assert result == "tags: ['active', 'verified']"

    def test_nested_dict_full_template(self) -> None:
        """Full template with nested dict returns the raw dict."""
        r = NamespaceResolver()
        r.set_namespace("data", {"user": {"name": "admin", "level": 5}})

        # Full template returns typed value
        result = r.resolve_value("${data.user}")

        # Returns the dict itself
        assert result == {"name": "admin", "level": 5}
        assert isinstance(result, dict)

    def test_nested_dict_in_embedded_expression(self) -> None:
        """Nested dict embedded in expression converts to string."""
        r = NamespaceResolver()
        r.set_namespace("data", {"user": {"name": "admin", "level": 5}})

        # Embedded in text
        result = r.resolve_value("user: ${data.user}")

        # Note: dict key order may vary
        assert "user: {" in result
        assert "'name': 'admin'" in result
        assert "'level': 5" in result

    def test_mixed_type_list_full_template(self) -> None:
        """Full template with mixed-type list returns the raw list."""
        r = NamespaceResolver()
        r.set_namespace("data", {"mixed": [1, "two", True, None]})

        # Full template returns typed value
        result = r.resolve_value("${data.mixed}")

        # Returns the list itself
        assert result == [1, "two", True, None]
        assert isinstance(result, list)


class TestGetNamespace:
    """Test get_namespace method for retrieving a specific namespace."""

    def test_returns_specific_namespace(self) -> None:
        r = NamespaceResolver()
        r.set_namespace("input", {"age": 25})
        r.set_namespace("fetch_user", {"role": "admin"})

        namespace = r.get_namespace("input")

        assert namespace == {"age": 25}

    def test_raises_key_error_for_missing_namespace(self) -> None:
        r = NamespaceResolver()

        with pytest.raises(KeyError):
            r.get_namespace("nonexistent")


class TestGetCompleteNamespace:
    """Test get_complete_namespace method for context-aware evaluation."""

    def test_returns_all_namespaces(self) -> None:
        r = NamespaceResolver()
        r.set_namespace("input", {"age": 25})
        r.set_namespace("fetch_user", {"role": "admin"})

        namespace = r.get_complete_namespace()

        assert namespace == {
            "input": {"age": 25},
            "fetch_user": {"role": "admin"},
        }

    def test_exposes_loop_context_when_set(self) -> None:
        r = NamespaceResolver()
        r.set_namespace(
            "loop",
            {
                "loop_1": {"item": "apple", "index": 0},
                "loop_2": {"item": "banana", "index": 1},
            },
        )

        # Set loop context
        r.set_context(loop_node_id="loop_1")
        namespace = r.get_complete_namespace()

        # 'loop' namespace should contain data for loop_1
        assert namespace["loop"] == {"item": "apple", "index": 0}

    def test_no_loop_context_when_not_set(self) -> None:
        r = NamespaceResolver()
        r.set_namespace("input", {"value": 42})
        r.set_namespace(
            "loop",
            {
                "loop_1": {"item": "apple", "index": 0},
            },
        )

        # No loop context set
        namespace = r.get_complete_namespace()

        # 'loop' namespace contains the full structure (not flattened)
        assert namespace["loop"] == {"loop_1": {"item": "apple", "index": 0}}

    def test_returns_copy_not_reference(self) -> None:
        r = NamespaceResolver()
        r.set_namespace("input", {"age": 25})

        namespace1 = r.get_complete_namespace()
        namespace2 = r.get_complete_namespace()

        # Modifying one shouldn't affect the other
        namespace1["input"]["age"] = 30
        assert namespace2["input"]["age"] == 25
