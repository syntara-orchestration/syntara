"""Unit tests for nested Sub-workflow output schema path checks."""

from typing import Any

import pytest

from syntara.workflows.validators.workflow_subworkflows import _schema_allows_nested_path


@pytest.mark.parametrize("union_keyword", ["anyOf", "oneOf"])
def test_union_schema_does_not_shadow_all_of(union_keyword: str) -> None:
    schema: dict[str, Any] = {
        "type": "object",
        union_keyword: [{"type": "object"}],
        "allOf": [{"type": "object", "additionalProperties": False}],
    }

    assert not _schema_allows_nested_path(schema, ("undeclared",))


def test_array_path_is_allowed_for_object_or_array_union_type() -> None:
    schema: dict[str, Any] = {
        "type": ["object", "array"],
        "additionalProperties": False,
        "items": {"type": "string"},
    }

    assert _schema_allows_nested_path(schema, ("0",))


def test_deep_nested_schema_is_rejected_at_the_path_depth_limit() -> None:
    depth = 100
    schema: dict[str, Any] = {"type": "string"}
    for _ in range(depth):
        schema = {"type": "object", "properties": {"child": schema}, "additionalProperties": False}

    path = ("child",) * depth

    assert not _schema_allows_nested_path(schema, path)
