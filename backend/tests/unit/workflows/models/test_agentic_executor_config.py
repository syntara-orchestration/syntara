"""Unit tests for AgenticExecutorParameters file_ids validation.

Tests for AAP-60786 - Agentic Activity file_ids Integration.

These tests verify:
- file_ids field accepts valid UUIDs
- file_ids field enforces max_length=10 constraint
- file_ids field rejects invalid UUIDs
- file_ids field allows template expressions (bypass UUID validation)
- file_ids uses correct alias (fileIds) for API compatibility
"""

import uuid

import pytest
from pydantic import ValidationError

from syntara.workflows.workflow_engine.models.workflow_definition import (
    TEMPLATE_PATTERN,
    AgenticExecutorParameters,
)


def generate_valid_uuid() -> str:
    """Generate a valid UUID string."""
    return str(uuid.uuid4())


def generate_valid_uuids(count: int) -> list[str]:
    """Generate a list of valid UUID strings."""
    return [generate_valid_uuid() for _ in range(count)]


class TestAgenticExecutorParametersFileIds:
    """Test suite for AgenticExecutorParameters file_ids field validation."""

    # ==========================================================================
    # Valid Cases
    # ==========================================================================

    def test_file_ids_empty_list_default(self) -> None:
        """Test that file_ids defaults to empty list when not provided."""
        config = AgenticExecutorParameters(prompt="Test prompt")

        assert config.file_ids == []

    def test_file_ids_single_valid_uuid(self) -> None:
        """Test that a single valid UUID is accepted."""
        file_id = generate_valid_uuid()
        config = AgenticExecutorParameters(prompt="Test prompt", file_ids=[file_id])

        assert config.file_ids == [file_id]

    def test_file_ids_multiple_valid_uuids(self) -> None:
        """Test that multiple valid UUIDs are accepted."""
        file_ids = generate_valid_uuids(5)
        config = AgenticExecutorParameters(prompt="Test prompt", file_ids=file_ids)

        assert config.file_ids == file_ids

    def test_file_ids_max_length_boundary_10(self) -> None:
        """Test that exactly 10 file_ids (max boundary) is accepted."""
        file_ids = generate_valid_uuids(10)
        config = AgenticExecutorParameters(prompt="Test prompt", file_ids=file_ids)

        assert len(config.file_ids) == 10
        assert config.file_ids == file_ids

    def test_file_ids_uuid_variants_accepted(self) -> None:
        """Test that various UUID formats are accepted."""
        # Standard UUID v4
        uuid_v4 = str(uuid.uuid4())
        # UUID with uppercase (should work since uuid.UUID() normalizes)
        uuid_upper = "550E8400-E29B-41D4-A716-446655440000"
        # UUID with lowercase
        uuid_lower = "550e8400-e29b-41d4-a716-446655440001"

        config = AgenticExecutorParameters(
            prompt="Test",
            file_ids=[uuid_v4, uuid_upper, uuid_lower],
        )

        assert len(config.file_ids) == 3

    # ==========================================================================
    # Template Expression Bypass
    # ==========================================================================

    def test_file_ids_template_expression_bypass(self) -> None:
        """Test that template expressions bypass UUID validation."""
        template = "${input.document_id}"
        config = AgenticExecutorParameters(prompt="Test prompt", file_ids=[template])

        assert config.file_ids == [template]

    def test_file_ids_complex_template_expression(self) -> None:
        """Test that complex template expressions are allowed."""
        templates = [
            "${input.files}",
            "${workflow.vars.document_ids[0]}",
            "${outputs.previous_task.file_id}",
        ]
        config = AgenticExecutorParameters(prompt="Test", file_ids=templates)

        assert config.file_ids == templates

    def test_file_ids_mixed_uuids_and_templates(self) -> None:
        """Test that mixed UUIDs and template expressions are allowed."""
        file_ids = [
            generate_valid_uuid(),
            "${input.file1}",
            generate_valid_uuid(),
            "${input.file2}",
        ]
        config = AgenticExecutorParameters(prompt="Test", file_ids=file_ids)

        assert config.file_ids == file_ids

    def test_template_pattern_matches_expected_formats(self) -> None:
        """Test that TEMPLATE_PATTERN matches expected template formats."""
        valid_templates = [
            "${input.field}",
            "${workflow.vars.count}",
            "${outputs.task1.result}",
            "${secrets.api_key}",
            "${input.nested.deeply.value}",
        ]

        for template in valid_templates:
            assert TEMPLATE_PATTERN.search(template) is not None, f"Should match: {template}"

        invalid_templates = [
            "not a template",
            "$input.field",  # Missing braces
            "{input.field}",  # Missing $
            "$(input.field)",  # Wrong brackets
        ]

        for template in invalid_templates:
            assert TEMPLATE_PATTERN.search(template) is None, f"Should not match: {template}"

    # ==========================================================================
    # Invalid Cases
    # ==========================================================================

    def test_file_ids_invalid_uuid_format_rejected(self) -> None:
        """Test that invalid UUID format is rejected with clear error message."""
        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(prompt="Test", file_ids=["not-a-valid-uuid"])

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "Invalid UUID format for file_ids" in str(errors[0]["msg"])
        assert "not-a-valid-uuid" in str(errors[0]["msg"])

    def test_file_ids_exceeds_max_length_rejected(self) -> None:
        """Test that more than 10 file_ids is rejected."""
        file_ids = generate_valid_uuids(11)

        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(prompt="Test", file_ids=file_ids)

        errors = exc_info.value.errors()
        assert any("at most 10" in str(e).lower() or "too_long" in str(e) for e in errors)

    def test_file_ids_empty_string_rejected(self) -> None:
        """Test that empty string is rejected as invalid UUID."""
        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(prompt="Test", file_ids=[""])

        errors = exc_info.value.errors()
        assert "Invalid UUID format for file_ids" in str(errors[0]["msg"])

    def test_file_ids_partial_uuid_rejected(self) -> None:
        """Test that partial UUID is rejected."""
        partial_uuid = "550e8400-e29b-41d4"  # Missing parts

        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(prompt="Test", file_ids=[partial_uuid])

        errors = exc_info.value.errors()
        assert "Invalid UUID format for file_ids" in str(errors[0]["msg"])

    def test_file_ids_uuid_with_invalid_chars_rejected(self) -> None:
        """Test that UUID with invalid characters is rejected."""
        invalid_uuid = "550e8400-e29b-41d4-a716-44665544000g"  # 'g' is invalid

        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(prompt="Test", file_ids=[invalid_uuid])

        errors = exc_info.value.errors()
        assert "Invalid UUID format for file_ids" in str(errors[0]["msg"])

    def test_file_ids_whitespace_only_rejected(self) -> None:
        """Test that whitespace-only string is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(prompt="Test", file_ids=["   "])

        errors = exc_info.value.errors()
        assert "Invalid UUID format for file_ids" in str(errors[0]["msg"])

    def test_file_ids_mixed_valid_invalid_all_rejected(self) -> None:
        """Test that list with any invalid UUID is rejected."""
        file_ids = [
            generate_valid_uuid(),
            "invalid-uuid",  # This should cause rejection
            generate_valid_uuid(),
        ]

        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(prompt="Test", file_ids=file_ids)

        errors = exc_info.value.errors()
        assert "Invalid UUID format for file_ids" in str(errors[0]["msg"])
        assert "invalid-uuid" in str(errors[0]["msg"])

    # ==========================================================================
    # API Alias (fileIds) Compatibility
    # ==========================================================================

    def test_file_ids_snake_case_accepted(self) -> None:
        """Test that file_ids (snake_case) is accepted in input."""
        file_ids = generate_valid_uuids(3)

        # Using snake_case in input
        config = AgenticExecutorParameters.model_validate(
            {
                "prompt": "Test",
                "file_ids": file_ids,
            }
        )

        assert config.file_ids == file_ids

    def test_file_ids_serializes_as_snake_case(self) -> None:
        """Test that file_ids serializes to snake_case when using by_alias."""
        file_ids = generate_valid_uuids(2)
        config = AgenticExecutorParameters(prompt="Test", file_ids=file_ids)

        # Serialize with by_alias=True (for API responses)
        serialized = config.model_dump(mode="json", by_alias=True)

        assert "file_ids" in serialized
        assert serialized["file_ids"] == file_ids

    def test_file_ids_serializes_without_alias(self) -> None:
        """Test that file_ids serializes to file_ids when not using alias."""
        file_ids = generate_valid_uuids(2)
        config = AgenticExecutorParameters(prompt="Test", file_ids=file_ids)

        # Serialize without by_alias (Python-style)
        serialized = config.model_dump()

        assert "file_ids" in serialized
        assert serialized["file_ids"] == file_ids


class TestAgenticExecutorParametersIntegration:
    """Integration tests for AgenticExecutorParameters with other fields."""

    def test_full_config_with_file_ids(self) -> None:
        """Test complete configuration with all fields including file_ids."""
        file_ids = generate_valid_uuids(3)

        config = AgenticExecutorParameters(
            prompt="Analyze the documents and provide a summary",
            agent="document-analyzer",
            file_ids=file_ids,
        )

        assert config.prompt == "Analyze the documents and provide a summary"
        assert config.agent == "document-analyzer"
        assert config.file_ids == file_ids

    def test_config_from_workflow_yaml_format(self) -> None:
        """Test config parsing from workflow YAML-like dict."""
        yaml_config = {
            "prompt": "Process these files",
            "agent": "file-processor",
            "file_ids": [
                "550e8400-e29b-41d4-a716-446655440000",
                "${input.additional_file}",
            ],
        }

        config = AgenticExecutorParameters.model_validate(yaml_config)

        assert config.prompt == "Process these files"
        assert len(config.file_ids) == 2
        assert config.file_ids[0] == "550e8400-e29b-41d4-a716-446655440000"
        assert config.file_ids[1] == "${input.additional_file}"
