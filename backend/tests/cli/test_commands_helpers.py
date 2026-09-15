"""Tests for pure helper functions in orchestrator_cli.commands."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from orchestrator_cli.commands import (
    _build_body_data,
    _extract_body_fields,
    _extract_body_ref,
    _is_complex_field,
    _load_json_arg,
    _openapi_default,
    _openapi_to_click_type,
    _operationid_to_command,
    _resolve_ref,
    _snake,
)

# ---------------------------------------------------------------------------
# _snake
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("camelCase", "camel_case"),
        ("kebab-case", "kebab_case"),
        ("with spaces", "with_spaces"),
        ("ABCDef", "abc_def"),
        ("already_snake", "already_snake"),
    ],
)
def test_snake(name: str, expected: str) -> None:
    assert _snake(name) == expected


# ---------------------------------------------------------------------------
# _operationid_to_command
# ---------------------------------------------------------------------------


def test_operationid_to_command_strips_tag_suffix() -> None:
    """'list_workflows' with tag 'workflows' → 'list'."""
    assert _operationid_to_command("list_workflows", "workflows") == "list"


def test_operationid_to_command_strips_singular_infix() -> None:
    """'publish_workflow_version' with tag 'workflows' → 'publish-version'."""
    assert _operationid_to_command("publish_workflow_version", "workflows") == "publish-version"


def test_operationid_to_command_strips_tag_prefix() -> None:
    """'workflows_list' with tag 'workflows' → 'list'."""
    assert _operationid_to_command("workflows_list", "workflows") == "list"


# ---------------------------------------------------------------------------
# _openapi_to_click_type
# ---------------------------------------------------------------------------


def test_openapi_to_click_type_integer() -> None:
    assert _openapi_to_click_type({"type": "integer"}) is int


def test_openapi_to_click_type_boolean() -> None:
    assert _openapi_to_click_type({"type": "boolean"}) is bool


def test_openapi_to_click_type_anyof_skips_null_picks_concrete_type() -> None:
    assert _openapi_to_click_type({"anyOf": [{"type": "null"}, {"type": "integer"}]}) is int


def test_openapi_to_click_type_unknown_defaults_to_str() -> None:
    assert _openapi_to_click_type({}) is str


# ---------------------------------------------------------------------------
# _openapi_default
# ---------------------------------------------------------------------------


def test_openapi_default_returns_schema_default_when_optional() -> None:
    assert _openapi_default({"default": "foo"}, is_required=False) == "foo"


def test_openapi_default_returns_none_when_required() -> None:
    """Required fields must not receive a default — they must be supplied by the user."""
    assert _openapi_default({"default": "foo"}, is_required=True) is None


# ---------------------------------------------------------------------------
# _is_complex_field
# ---------------------------------------------------------------------------

_SPEC: dict[str, object] = {
    "components": {
        "schemas": {
            "StatusEnum": {"type": "string", "enum": ["active", "inactive"]},
            "MyModel": {"type": "object", "properties": {"id": {"type": "string"}}},
        }
    }
}


def test_is_complex_field_object_type() -> None:
    assert _is_complex_field({}, {"type": "object"}) is True


def test_is_complex_field_array_type() -> None:
    assert _is_complex_field({}, {"type": "array"}) is True


def test_is_complex_field_enum_ref_is_not_complex() -> None:
    """Enum $refs are scalar — they should render as a simple CLI option, not JSON."""
    assert _is_complex_field(_SPEC, {"$ref": "#/components/schemas/StatusEnum"}) is False


def test_is_complex_field_object_ref_is_complex() -> None:
    assert _is_complex_field(_SPEC, {"$ref": "#/components/schemas/MyModel"}) is True


def test_is_complex_field_untyped_field_is_complex() -> None:
    """Fields with no type, $ref, or anyOf accept arbitrary values and are treated as complex."""
    assert _is_complex_field({}, {}) is True


# ---------------------------------------------------------------------------
# _load_json_arg
# ---------------------------------------------------------------------------


def test_load_json_arg_parses_inline_json() -> None:
    assert _load_json_arg('{"key": "val"}') == {"key": "val"}


def test_load_json_arg_reads_from_file(tmp_path: Path) -> None:
    f = tmp_path / "data.json"
    f.write_text('{"from": "file"}')
    assert _load_json_arg(f"@{f}") == {"from": "file"}


def test_load_json_arg_raises_on_invalid_json() -> None:
    with pytest.raises(json.JSONDecodeError):
        _load_json_arg("not-json")


# ---------------------------------------------------------------------------
# _resolve_ref
# ---------------------------------------------------------------------------


def test_resolve_ref_returns_schema_name_and_node() -> None:
    spec = {"components": {"schemas": {"Foo": {"type": "string"}}}}
    name, node = _resolve_ref(spec, "#/components/schemas/Foo")
    assert name == "Foo"
    assert node == {"type": "string"}


# ---------------------------------------------------------------------------
# _extract_body_ref
# ---------------------------------------------------------------------------


def test_extract_body_ref_returns_none_when_no_request_body() -> None:
    assert _extract_body_ref({}) is None


def test_extract_body_ref_returns_ref_from_json_content() -> None:
    details = {"requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/MyModel"}}}}}
    assert _extract_body_ref(details) == "#/components/schemas/MyModel"


# ---------------------------------------------------------------------------
# _extract_body_fields
# ---------------------------------------------------------------------------

_BODY_SPEC: dict[str, object] = {
    "components": {
        "schemas": {
            "CreateBody": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "description": "The name"},
                    "status": {"$ref": "#/components/schemas/StatusEnum"},
                    "config": {"type": "object"},
                },
            },
            "StatusEnum": {"type": "string", "enum": ["active", "inactive"]},
        }
    }
}


def test_extract_body_fields_required_flag() -> None:
    fields = {f["name"]: f for f in _extract_body_fields(_BODY_SPEC, "#/components/schemas/CreateBody")}
    assert fields["name"]["required"] is True
    assert fields["status"]["required"] is False


def test_extract_body_fields_enum_ref_is_not_complex_and_lists_choices() -> None:
    fields = {f["name"]: f for f in _extract_body_fields(_BODY_SPEC, "#/components/schemas/CreateBody")}
    assert fields["status"]["is_complex"] is False
    assert "one of:" in fields["status"]["description"]
    assert "active" in fields["status"]["description"]


def test_extract_body_fields_object_is_complex() -> None:
    fields = {f["name"]: f for f in _extract_body_fields(_BODY_SPEC, "#/components/schemas/CreateBody")}
    assert fields["config"]["is_complex"] is True


# ---------------------------------------------------------------------------
# _build_body_data
# ---------------------------------------------------------------------------


def test_build_body_data_skips_path_params() -> None:
    """Fields that are also path params must not appear in the request body."""
    fields = [{"name": "id", "required": True, "is_complex": False}]
    result = _build_body_data({"id": "123"}, fields, ["id"], set(), {"id"})
    assert "id" not in result


def test_build_body_data_parses_complex_field_as_json() -> None:
    fields = [{"name": "config", "required": True, "is_complex": True}]
    result = _build_body_data({"config": '{"k": "v"}'}, fields, ["config"], {"config"}, set())
    assert result["config"] == {"k": "v"}


def test_build_body_data_omits_optional_field_when_none() -> None:
    fields = [{"name": "tag", "required": False, "is_complex": False}]
    result = _build_body_data({"tag": None}, fields, ["tag"], set(), set())
    assert "tag" not in result


def test_build_body_data_includes_optional_field_when_set() -> None:
    fields = [{"name": "tag", "required": False, "is_complex": False}]
    result = _build_body_data({"tag": "prod"}, fields, ["tag"], set(), set())
    assert result["tag"] == "prod"
