"""Tests for apply_output_mapping.

Tests cover:
- None config (no mapping, return full result)
- Empty config (suppress all executor fields)
- Field mappings (extract specific fields)
- Error paths
"""

from typing import Any

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.output_mapping import apply_output_mapping

# ---------------------------------------------------------------------------
# None config — no mapping
# ---------------------------------------------------------------------------


class TestOutputMappingNoneConfig:
    """When output_config is None, result is returned unchanged."""

    def test_returns_full_result(self) -> None:
        result: dict[str, Any] = {"return_code": 0, "stdout": "hello", "stderr": ""}
        mapped = apply_output_mapping(result, None)
        assert mapped == result

    def test_returns_same_dict_object(self) -> None:
        result: dict[str, Any] = {"data": "x"}
        mapped = apply_output_mapping(result, None)
        assert mapped is result


# ---------------------------------------------------------------------------
# Empty config — suppress all executor fields
# ---------------------------------------------------------------------------


class TestOutputMappingEmptyConfig:
    """When output_config is {}, all executor fields are suppressed."""

    def test_returns_empty_dict(self) -> None:
        result: dict[str, Any] = {"return_code": 0, "stdout": "hello"}
        mapped = apply_output_mapping(result, {})
        assert mapped == {}

    def test_original_fields_stripped(self) -> None:
        result: dict[str, Any] = {"a": 1, "b": 2}
        mapped = apply_output_mapping(result, {})
        assert "a" not in mapped
        assert "b" not in mapped


# ---------------------------------------------------------------------------
# Field mappings — extract specific fields
# ---------------------------------------------------------------------------


class TestOutputMappingFieldMappings:
    """When output_config has mappings, only mapped fields are returned."""

    def test_single_field_mapping(self) -> None:
        result: dict[str, Any] = {"response_code": 200, "body": "hello"}
        mapped = apply_output_mapping(result, {"code": "${result.response_code}"})
        assert mapped["code"] == 200
        assert "body" not in mapped
        assert "response_code" not in mapped

    def test_multiple_field_mappings(self) -> None:
        result: dict[str, Any] = {"a": 1, "b": 2, "c": 3}
        mapped = apply_output_mapping(result, {"x": "${result.a}", "y": "${result.b}"})
        assert mapped == {"x": 1, "y": 2}

    def test_nested_field_mapping(self) -> None:
        result: dict[str, Any] = {"output": {"nested": {"val": 42}}}
        mapped = apply_output_mapping(result, {"deep": "${result.output.nested.val}"})
        assert mapped == {"deep": 42}

    def test_string_interpolation_in_mapping(self) -> None:
        result: dict[str, Any] = {"code": 200}
        mapped = apply_output_mapping(result, {"msg": "status=${result.code}"})
        assert mapped["msg"] == "status=200"

    def test_null_field_resolves_to_none(self) -> None:
        """Fields set to None (partial failure data) resolve successfully."""
        result: dict[str, Any] = {"stdout": None, "stderr": "error msg"}
        mapped = apply_output_mapping(result, {"out": "${result.stdout}", "err": "${result.stderr}"})
        assert mapped["out"] is None
        assert mapped["err"] == "error msg"


# ---------------------------------------------------------------------------
# Error paths in field mappings
# ---------------------------------------------------------------------------


class TestOutputMappingErrors:
    """Error paths for apply_output_mapping."""

    def test_mapping_referencing_missing_field_raises(self) -> None:
        """Template referencing non-existent field raises ApplicationError."""
        result: dict[str, Any] = {"a": 1}
        with pytest.raises(ApplicationError) as exc_info:
            apply_output_mapping(result, {"x": "${result.nonexistent}"})
        assert exc_info.value.type == "OutputMappingError"
        assert exc_info.value.non_retryable is True
