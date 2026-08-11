"""Unit tests for NamespaceResolver.resolve_dict handling of lists.

Covers Task 1.2: resolve_dict must recursively resolve dicts nested inside
lists, nested lists of dicts, and mixed-type lists.
"""

from typing import Any

import pytest

from syntara.workflows.utils.namespace_resolver import NamespaceResolver


@pytest.fixture
def resolver() -> NamespaceResolver:
    """Create a NamespaceResolver with a trigger namespace pre-loaded."""
    r = NamespaceResolver()
    r.set_namespace("trigger", {"url": "https://example.com", "token": "abc123", "count": 5})
    return r


class TestResolveDictWithListOfDicts:
    """resolve_dict must recurse into dicts that appear inside list values."""

    def test_single_dict_in_list_is_resolved(self, resolver: NamespaceResolver) -> None:
        """A list containing one dict with a template should be resolved."""
        data: dict[str, Any] = {
            "items": [{"url": "${trigger.url}"}],
        }
        result = resolver.resolve_dict(data)
        assert result["items"] == [{"url": "https://example.com"}]

    def test_multiple_dicts_in_list_are_resolved(self, resolver: NamespaceResolver) -> None:
        """All dicts in a list should have their templates resolved."""
        data: dict[str, Any] = {
            "items": [
                {"url": "${trigger.url}"},
                {"token": "${trigger.token}"},
            ],
        }
        result = resolver.resolve_dict(data)
        assert result["items"] == [
            {"url": "https://example.com"},
            {"token": "abc123"},
        ]

    def test_dict_in_list_with_multiple_keys_resolved(self, resolver: NamespaceResolver) -> None:
        """A single dict in a list with multiple template keys should all resolve."""
        data: dict[str, Any] = {
            "items": [{"url": "${trigger.url}", "token": "${trigger.token}"}],
        }
        result = resolver.resolve_dict(data)
        assert result["items"] == [{"url": "https://example.com", "token": "abc123"}]

    def test_nested_dict_inside_list_dict_is_resolved(self, resolver: NamespaceResolver) -> None:
        """Dicts nested within list-dicts should also be resolved recursively."""
        data: dict[str, Any] = {
            "items": [{"parameters": {"endpoint": "${trigger.url}"}}],
        }
        result = resolver.resolve_dict(data)
        assert result["items"] == [{"parameters": {"endpoint": "https://example.com"}}]


class TestResolveDictWithNestedLists:
    """resolve_dict must handle lists nested within lists."""

    def test_list_of_lists_with_dicts(self, resolver: NamespaceResolver) -> None:
        """Dicts inside nested lists should be resolved."""
        data: dict[str, Any] = {
            "matrix": [[{"url": "${trigger.url}"}]],
        }
        result = resolver.resolve_dict(data)
        assert result["matrix"] == [[{"url": "https://example.com"}]]

    def test_deeply_nested_list_of_lists_of_dicts(self, resolver: NamespaceResolver) -> None:
        """Three levels of list nesting with a dict at the bottom."""
        data: dict[str, Any] = {
            "deep": [[[{"token": "${trigger.token}"}]]],
        }
        result = resolver.resolve_dict(data)
        assert result["deep"] == [[[{"token": "abc123"}]]]

    def test_list_of_lists_with_strings(self, resolver: NamespaceResolver) -> None:
        """Template strings inside nested lists should be resolved."""
        data: dict[str, Any] = {
            "matrix": [["${trigger.url}", "static"]],
        }
        result = resolver.resolve_dict(data)
        assert result["matrix"] == [["https://example.com", "static"]]


class TestResolveDictListWithMixedTypes:
    """Lists containing a mix of dicts, strings, and non-string scalars."""

    def test_mixed_list_of_dicts_strings_and_ints(self, resolver: NamespaceResolver) -> None:
        """Non-dict, non-string items should pass through unchanged."""
        data: dict[str, Any] = {
            "items": [
                {"url": "${trigger.url}"},
                "${trigger.token}",
                42,
                None,
            ],
        }
        result = resolver.resolve_dict(data)
        assert result["items"] == [
            {"url": "https://example.com"},
            "abc123",
            42,
            None,
        ]

    def test_empty_list_is_preserved(self, resolver: NamespaceResolver) -> None:
        """An empty list value should remain an empty list."""
        data: dict[str, Any] = {"items": []}
        result = resolver.resolve_dict(data)
        assert result["items"] == []

    def test_list_with_only_scalars_still_resolves_strings(self, resolver: NamespaceResolver) -> None:
        """A list with no dicts but with template strings should resolve those strings."""
        data: dict[str, Any] = {
            "tags": ["${trigger.url}", "fixed-tag", 99],
        }
        result = resolver.resolve_dict(data)
        assert result["tags"] == ["https://example.com", "fixed-tag", 99]


class TestResolveDictListWithNonTemplateValues:
    """Ensure non-template values in list dicts pass through unchanged."""

    def test_dict_in_list_with_no_templates(self, resolver: NamespaceResolver) -> None:
        """A dict in a list with no template strings should be returned as-is."""
        data: dict[str, Any] = {
            "items": [{"key": "plain_value", "count": 10}],
        }
        result = resolver.resolve_dict(data)
        assert result["items"] == [{"key": "plain_value", "count": 10}]

    def test_bool_values_in_list_dicts_preserved(self, resolver: NamespaceResolver) -> None:
        """Boolean values inside dicts within lists should not be altered."""
        data: dict[str, Any] = {
            "flags": [{"enabled": True, "label": "${trigger.token}"}],
        }
        result = resolver.resolve_dict(data)
        assert result["flags"] == [{"enabled": True, "label": "abc123"}]


class TestResolveDictListErrorPaths:
    """Error conditions when resolving templates in list items."""

    def test_unresolvable_template_in_list_dict_raises_key_error(self, resolver: NamespaceResolver) -> None:
        """A template referencing a missing namespace inside a list dict should raise."""
        data: dict[str, Any] = {
            "items": [{"url": "${nonexistent.value}"}],
        }
        with pytest.raises(KeyError, match="nonexistent"):
            resolver.resolve_dict(data)

    def test_unresolvable_template_string_in_list_raises_key_error(self, resolver: NamespaceResolver) -> None:
        """A bare template string in a list referencing a missing namespace should raise."""
        data: dict[str, Any] = {
            "items": ["${missing.path}"],
        }
        with pytest.raises(KeyError, match="missing"):
            resolver.resolve_dict(data)


class TestResolveListMethod:
    """Direct tests for the _resolve_list helper method."""

    def test_resolve_list_returns_new_list(self, resolver: NamespaceResolver) -> None:
        """_resolve_list should return a new list, not mutate the original."""
        original: list[Any] = [{"url": "${trigger.url}"}, "static"]
        result = resolver._resolve_list(original)
        assert result is not original
        assert original[0] == {"url": "${trigger.url}"}  # unchanged
        assert result[0] == {"url": "https://example.com"}

    def test_resolve_list_with_non_string_full_template(self, resolver: NamespaceResolver) -> None:
        """A full template that resolves to a non-string (int) should return the int."""
        data: dict[str, Any] = {
            "counts": ["${trigger.count}"],
        }
        result = resolver.resolve_dict(data)
        assert result["counts"] == [5]
        assert isinstance(result["counts"][0], int)
