"""Tests for AgenticExecutorParameters configuration validation (AAP-66973).

Tests cover:
- tool_selections UUID format validation
- tool_selection_strategy + tool_selections cross-field coherence
- response_schema full JSON Schema Draft-07 validation ($ref SSRF, ReDoS)
- Error message quality (field paths, expected formats)
"""

import pytest
from pydantic import ValidationError

from syntara.workflows.workflow_engine.models.workflow_definition import AgenticExecutorParameters

VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"
VALID_UUID_2 = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"


class TestToolSelectionsUUIDValidation:
    """Validate that tool_selections entries must be valid UUIDs or template expressions."""

    def test_valid_uuids_accepted(self) -> None:
        config = AgenticExecutorParameters(
            prompt="test",
            tool_selection_strategy="SELECTED",
            tool_selections=[VALID_UUID, VALID_UUID_2],
        )
        assert config.tool_selections == [VALID_UUID, VALID_UUID_2]

    def test_invalid_uuid_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(
                prompt="test",
                tool_selection_strategy="SELECTED",
                tool_selections=["not-a-uuid"],
            )
        errors = exc_info.value.errors()
        assert any("tool_selections" in str(e["msg"]) for e in errors)

    def test_template_expression_bypasses_uuid_validation(self) -> None:
        config = AgenticExecutorParameters(
            prompt="test",
            tool_selection_strategy="SELECTED",
            tool_selections=["${input.tool_ids}"],
        )
        assert config.tool_selections == ["${input.tool_ids}"]

    def test_mixed_valid_and_invalid_uuids_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgenticExecutorParameters(
                prompt="test",
                tool_selection_strategy="SELECTED",
                tool_selections=[VALID_UUID, "bad-id"],
            )

    def test_error_message_includes_invalid_value(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(
                prompt="test",
                tool_selection_strategy="SELECTED",
                tool_selections=["definitely-not-valid"],
            )
        error_text = str(exc_info.value)
        assert "definitely-not-valid" in error_text


class TestToolSelectionStrategyCrossFieldValidation:
    """Validate coherence between tool_selection_strategy and tool_selections."""

    def test_selected_with_tools_passes(self) -> None:
        config = AgenticExecutorParameters(
            prompt="test",
            tool_selection_strategy="SELECTED",
            tool_selections=[VALID_UUID],
        )
        assert config.tool_selection_strategy == "SELECTED"
        assert len(config.tool_selections) == 1

    def test_selected_with_empty_tools_fails(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(
                prompt="test",
                tool_selection_strategy="SELECTED",
                tool_selections=[],
            )
        error_text = str(exc_info.value)
        assert "tool_selections" in error_text

    def test_none_strategy_with_empty_tools_passes(self) -> None:
        config = AgenticExecutorParameters(
            prompt="test",
            tool_selection_strategy="NONE",
            tool_selections=[],
        )
        assert config.tool_selection_strategy == "NONE"

    def test_all_strategy_with_empty_tools_passes(self) -> None:
        config = AgenticExecutorParameters(
            prompt="test",
            tool_selection_strategy="ALL",
            tool_selections=[],
        )
        assert config.tool_selection_strategy == "ALL"

    def test_none_strategy_with_tools_fails(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(
                prompt="test",
                tool_selection_strategy="NONE",
                tool_selections=[VALID_UUID],
            )
        error_text = str(exc_info.value)
        assert "tool_selections" in error_text

    def test_all_strategy_with_tools_fails(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(
                prompt="test",
                tool_selection_strategy="ALL",
                tool_selections=[VALID_UUID],
            )
        error_text = str(exc_info.value)
        assert "tool_selections" in error_text

    def test_no_strategy_with_no_tools_passes(self) -> None:
        config = AgenticExecutorParameters(prompt="test")
        assert config.tool_selection_strategy is None
        assert config.tool_selections == []

    def test_template_strategy_bypasses_cross_field_validation(self) -> None:
        config = AgenticExecutorParameters.model_validate(
            {
                "prompt": "test",
                "tool_selection_strategy": "${input.strategy}",
                "tool_selections": [],
            }
        )
        assert str(config.tool_selection_strategy) == "${input.strategy}"


class TestResponseSchemaJsonSchemaValidation:
    """Validate response_schema against JSON Schema Draft-07 with security checks."""

    def test_valid_object_schema_passes(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "score": {"type": "number"},
            },
            "required": ["summary"],
        }
        config = AgenticExecutorParameters(prompt="test", responseSchema=schema)
        assert config.response_schema == schema

    def test_valid_simple_schema_passes(self) -> None:
        config = AgenticExecutorParameters(prompt="test", responseSchema={"type": "string"})
        assert config.response_schema == {"type": "string"}

    def test_none_schema_passes(self) -> None:
        config = AgenticExecutorParameters(prompt="test", responseSchema=None)
        assert config.response_schema is None

    def test_template_expression_bypasses_validation(self) -> None:
        config = AgenticExecutorParameters(prompt="test", responseSchema="${input.schema}")
        assert config.response_schema == "${input.schema}"

    def test_schema_without_type_is_valid_draft07(self) -> None:
        """A schema without 'type' is valid per Draft-07 (matches anything)."""
        config = AgenticExecutorParameters(
            prompt="test",
            responseSchema={"properties": {"name": {"type": "string"}}},
        )
        assert config.response_schema is not None

    def test_empty_dict_is_valid_draft07(self) -> None:
        """An empty dict is valid JSON Schema per Draft-07 (matches anything)."""
        config = AgenticExecutorParameters(prompt="test", responseSchema={})
        assert config.response_schema == {}

    def test_schema_with_ref_rejected_ssrf(self) -> None:
        """$ref references must be rejected to prevent SSRF."""
        schema = {
            "type": "object",
            "properties": {
                "data": {"$ref": "https://evil.com/schema.json"},
            },
        }
        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(prompt="test", responseSchema=schema)
        error_text = str(exc_info.value)
        assert "$ref" in error_text or "ref" in error_text.lower()

    def test_schema_with_redos_pattern_rejected(self) -> None:
        """Regex patterns with nested quantifiers must be rejected (ReDoS prevention)."""
        schema = {
            "type": "object",
            "properties": {
                "email": {"type": "string", "pattern": "(a+)+$"},
            },
        }
        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(prompt="test", responseSchema=schema)
        error_text = str(exc_info.value)
        assert "quantifier" in error_text.lower() or "unsafe" in error_text.lower()

    def test_schema_with_invalid_structure_rejected(self) -> None:
        """Schema that fails Draft-07 meta-schema validation must be rejected."""
        schema = {
            "type": "invalid_type_value",
        }
        with pytest.raises(ValidationError):
            AgenticExecutorParameters(prompt="test", responseSchema=schema)

    def test_response_schema_error_includes_field_path(self) -> None:
        """Error from invalid schema includes 'response_schema' in the message."""
        schema_with_ref = {
            "type": "object",
            "properties": {"data": {"$ref": "https://evil.com/schema.json"}},
        }
        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(prompt="test", responseSchema=schema_with_ref)
        error_text = str(exc_info.value)
        assert "response_schema" in error_text


class TestErrorMessageQuality:
    """Verify error messages include field paths, expected formats, and invalid values."""

    def test_tool_selection_error_includes_field_and_value(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(
                prompt="test",
                tool_selection_strategy="SELECTED",
                tool_selections=["bad-value"],
            )
        error_text = str(exc_info.value)
        assert "bad-value" in error_text
        assert "tool_selections" in error_text

    def test_cross_field_error_names_both_fields(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(
                prompt="test",
                tool_selection_strategy="SELECTED",
                tool_selections=[],
            )
        error_text = str(exc_info.value)
        assert "tool_selections" in error_text
        assert "SELECTED" in error_text
