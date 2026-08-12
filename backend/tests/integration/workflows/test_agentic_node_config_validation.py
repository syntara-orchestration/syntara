"""Integration tests for agentic node configuration validation (AAP-66973 T050/T051).

Tests validate that invalid agentic node configurations are caught at definition
time with clear error messages, preventing silent runtime failures.

T050: Invalid tool selection error handling
T051: Malformed schema error handling

These are contract-level tests — no database or Temporal required. They test
the full validation path through JSON Schema and Pydantic model validation.
"""

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from pydantic import ValidationError
from referencing import Registry
from referencing.jsonschema import DRAFT202012

from syntara.workflows.workflow_engine.models.workflow_definition import AgenticExecutorParameters

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "src" / "syntara" / "schemas" / "workflows" / "v2"
VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture
def agentic_schema() -> dict[str, Any]:
    """Load the agentic node JSON schema with $ref resolution."""
    schema_path = SCHEMA_DIR / "executors" / "agentic.schema.json"
    common_path = SCHEMA_DIR / "common-definitions.schema.json"
    with schema_path.open() as f:
        schema: dict[str, Any] = json.load(f)
    with common_path.open() as f:
        common: dict[str, Any] = json.load(f)
    common_id = common.get("$id", "../common-definitions.schema.json")
    resource = DRAFT202012.create_resource(common)
    registry: Registry[Any] = Registry().with_resource(common_id, resource)
    schema["_registry"] = registry
    return schema


def _validate_params(config: dict[str, Any], schema: dict[str, Any]) -> None:
    """Validate a config dict against the agentic parameterSchema."""
    registry = schema.pop("_registry", Registry())
    try:
        validator = jsonschema.Draft202012Validator(schema["parameterSchema"], registry=registry)
        validator.validate(config)
    finally:
        schema["_registry"] = registry


class TestInvalidToolSelectionErrorHandling:
    """T050: Integration tests for invalid tool selection error handling."""

    def test_selected_strategy_with_empty_tools_rejected_by_pydantic(self) -> None:
        """Pydantic cross-field validation rejects SELECTED with no tools."""
        with pytest.raises(ValidationError, match=r"tool_selections.*must not be empty"):
            AgenticExecutorParameters(
                prompt="test",
                tool_selection_strategy="SELECTED",
                tool_selections=[],
            )

    def test_none_strategy_with_tools_rejected_by_pydantic(self) -> None:
        """Pydantic cross-field validation rejects NONE with tool selections."""
        with pytest.raises(ValidationError, match=r"tool_selections.*must be empty"):
            AgenticExecutorParameters(
                prompt="test",
                tool_selection_strategy="NONE",
                tool_selections=[VALID_UUID],
            )

    def test_all_strategy_with_tools_rejected_by_pydantic(self) -> None:
        """Pydantic cross-field validation rejects ALL with tool selections."""
        with pytest.raises(ValidationError, match=r"tool_selections.*must be empty"):
            AgenticExecutorParameters(
                prompt="test",
                tool_selection_strategy="ALL",
                tool_selections=[VALID_UUID],
            )

    def test_invalid_tool_uuid_rejected_with_index(self) -> None:
        """Invalid tool UUID error includes the array index and value."""
        with pytest.raises(ValidationError, match=r"tool_selections\[1\].*bad-id") as exc_info:
            AgenticExecutorParameters(
                prompt="test",
                tool_selection_strategy="SELECTED",
                tool_selections=[VALID_UUID, "bad-id"],
            )
        assert "bad-id" in str(exc_info.value)

    def test_selected_strategy_requires_tools_in_json_schema(self, agentic_schema: dict[str, Any]) -> None:
        """JSON Schema enforces tool_selections when strategy is SELECTED."""
        config = {"prompt": "test", "tool_selection_strategy": "SELECTED"}
        with pytest.raises(jsonschema.ValidationError):
            _validate_params(config, agentic_schema)

    def test_valid_selected_config_accepted(self) -> None:
        """Valid SELECTED config with tool UUIDs passes all validation."""
        config = AgenticExecutorParameters(
            prompt="test",
            tool_selection_strategy="SELECTED",
            tool_selections=[VALID_UUID],
        )
        assert config.tool_selection_strategy == "SELECTED"
        assert config.tool_selections == [VALID_UUID]


class TestMalformedSchemaErrorHandling:
    """T051: Integration tests for malformed schema error handling."""

    def test_schema_with_ref_rejected_with_clear_message(self) -> None:
        """$ref in response_schema produces actionable error (SSRF prevention)."""
        with pytest.raises(ValidationError, match=r"response_schema.*\$ref") as exc_info:
            AgenticExecutorParameters(
                prompt="test",
                responseSchema={
                    "type": "object",
                    "properties": {"data": {"$ref": "https://evil.com/schema.json"}},
                },
            )
        error_msg = str(exc_info.value)
        assert "response_schema" in error_msg
        assert "$ref" in error_msg

    def test_schema_with_redos_rejected_with_clear_message(self) -> None:
        """ReDoS-vulnerable pattern produces actionable error."""
        with pytest.raises(ValidationError, match=r"response_schema.*unsafe|quantifier") as exc_info:
            AgenticExecutorParameters(
                prompt="test",
                responseSchema={
                    "type": "object",
                    "properties": {"email": {"type": "string", "pattern": "(a+)+$"}},
                },
            )
        error_msg = str(exc_info.value)
        assert "response_schema" in error_msg

    def test_invalid_schema_structure_rejected(self) -> None:
        """Schema with invalid Draft-07 type value is rejected."""
        with pytest.raises(ValidationError, match="response_schema"):
            AgenticExecutorParameters(
                prompt="test",
                responseSchema={"type": "not_a_valid_type"},
            )

    def test_valid_schema_accepted(self) -> None:
        """Valid JSON Schema passes all validation layers."""
        schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "score": {"type": "number", "minimum": 0, "maximum": 100},
            },
            "required": ["summary"],
        }
        config = AgenticExecutorParameters(prompt="test", responseSchema=schema)
        assert config.response_schema == schema

    def test_error_message_includes_schema_detail(self) -> None:
        """Error from invalid schema includes specific validation failure."""
        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(
                prompt="test",
                responseSchema={"type": "not_a_valid_type"},
            )
        error_msg = str(exc_info.value)
        assert "response_schema" in error_msg
        assert "not_a_valid_type" in error_msg or "Invalid JSON Schema" in error_msg


class TestEndToEndConfigValidation:
    """End-to-end validation: invalid configs produce clear, actionable errors."""

    def test_multiple_validation_errors_caught(self) -> None:
        """Config with multiple issues is caught at the first validation failure."""
        with pytest.raises(ValidationError):
            AgenticExecutorParameters(
                prompt="bad\0prompt",
                tool_selection_strategy="SELECTED",
                tool_selections=[],
                responseSchema={"$ref": "https://evil.com"},
            )

    def test_valid_full_config_passes(self) -> None:
        """Complete valid agentic config passes all validation."""
        config = AgenticExecutorParameters(
            prompt="Analyze the data and provide insights",
            agent="data-analyzer",
            credential_id=VALID_UUID,
            tool_selection_strategy="SELECTED",
            tool_selections=[VALID_UUID],
            responseSchema={
                "type": "object",
                "properties": {
                    "analysis": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["analysis"],
            },
        )
        assert config.prompt == "Analyze the data and provide insights"
        assert config.tool_selection_strategy == "SELECTED"
        assert config.response_schema is not None
