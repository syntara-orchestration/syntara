"""Unit tests for AgenticExecutorParameters prompt security validation.

These tests verify:
- Prompt length is NOT validated by the Pydantic model (done at runtime by the activity)
- Null byte detection in prompts
- Dead V1 code has been removed from agentic_activity module
"""

import pytest
from pydantic import ValidationError

from syntara.workflows.workflow_engine.models.workflow_definition import (
    AgenticExecutorParameters,
)


class TestPromptLengthValidation:
    """Tests for prompt length validation.

    Prompt length is validated at runtime by the agentic activity against
    the ``workflow_engine.max_prompt_length`` setting. The Pydantic model
    does NOT enforce a length limit — only the activity does.
    """

    def test_prompt_at_100k_accepted(self) -> None:
        """100KB prompt is accepted by the Pydantic model."""
        prompt = "a" * 100000
        config = AgenticExecutorParameters(prompt=prompt)
        assert config.prompt == prompt

    def test_prompt_over_100k_accepted_by_model(self) -> None:
        """Prompts over 100KB are accepted by Pydantic — length check is in the activity."""
        prompt = "a" * 200000
        config = AgenticExecutorParameters(prompt=prompt)
        assert config.prompt == prompt

    def test_prompt_well_under_max_length_accepted(self) -> None:
        """A short prompt should be accepted without issue."""
        config = AgenticExecutorParameters(prompt="Summarize this document")
        assert config.prompt == "Summarize this document"


class TestPromptNullByteDetection:
    """Tests for null byte detection in prompts."""

    def test_prompt_with_null_byte_rejected(self) -> None:
        """Prompt containing a null byte should raise ValidationError."""
        prompt = "Hello\0World"
        with pytest.raises(ValidationError) as exc_info:
            AgenticExecutorParameters(prompt=prompt)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "null" in errors[0]["msg"].lower()

    def test_prompt_with_null_byte_at_start_rejected(self) -> None:
        """Prompt starting with a null byte should be rejected."""
        prompt = "\0Some prompt text"
        with pytest.raises(ValidationError):
            AgenticExecutorParameters(prompt=prompt)

    def test_prompt_with_null_byte_at_end_rejected(self) -> None:
        """Prompt ending with a null byte should be rejected."""
        prompt = "Some prompt text\0"
        with pytest.raises(ValidationError):
            AgenticExecutorParameters(prompt=prompt)

    def test_prompt_with_multiple_null_bytes_rejected(self) -> None:
        """Prompt with multiple null bytes should be rejected."""
        prompt = "Hello\0World\0Again"
        with pytest.raises(ValidationError):
            AgenticExecutorParameters(prompt=prompt)

    def test_prompt_without_null_bytes_accepted(self) -> None:
        """Normal prompt without null bytes should be accepted."""
        config = AgenticExecutorParameters(prompt="Normal prompt with unicode: àéîõü")
        assert "àéîõü" in config.prompt

    def test_prompt_with_other_special_chars_accepted(self) -> None:
        """Prompt with tabs, newlines, and other whitespace should be accepted."""
        prompt = "Line 1\nLine 2\tTabbed\rCarriage return"
        config = AgenticExecutorParameters(prompt=prompt)
        assert config.prompt == prompt


class TestPromptValidationPriority:
    """Tests for how prompt validation interacts with other validation."""

    def test_prompt_with_null_byte_fails_regardless_of_length(self) -> None:
        """Null bytes should fail validation regardless of prompt length."""
        prompt = "a" * 200000 + "\0"
        with pytest.raises(ValidationError):
            AgenticExecutorParameters(prompt=prompt)

    def test_empty_string_prompt_accepted_by_security_validator(self) -> None:
        """Empty string passes security validation (no length issue, no null bytes)."""
        # The security validator itself doesn't reject empty strings
        config = AgenticExecutorParameters(prompt="")
        assert config.prompt == ""


class TestDeadV1CodeRemoval:
    """Tests verifying dead V1 code has been removed from agentic_activity."""

    def test_validate_input_data_function_removed(self) -> None:
        """_validate_input_data should no longer exist in agentic_activity module."""
        import syntara.workflows.workflow_engine.activities.agentic_activity as mod

        assert not hasattr(mod, "_validate_input_data"), "_validate_input_data should have been removed as dead V1 code"

    def test_validate_resolved_prompt_function_removed(self) -> None:
        """_validate_resolved_prompt should no longer exist in agentic_activity module."""
        import syntara.workflows.workflow_engine.activities.agentic_activity as mod

        assert not hasattr(mod, "_validate_resolved_prompt"), (
            "_validate_resolved_prompt should have been removed as dead V1 code"
        )

    def test_extract_config_function_removed(self) -> None:
        """_extract_config should no longer exist in agentic_activity module."""
        import syntara.workflows.workflow_engine.activities.agentic_activity as mod

        assert not hasattr(mod, "_extract_config"), "_extract_config should have been removed as dead V1 code"

    def test_resolve_parameter_templates_import_removed(self) -> None:
        """resolve_parameter_templates should not be imported in agentic_activity module."""
        import syntara.workflows.workflow_engine.activities.agentic_activity as mod

        assert not hasattr(mod, "resolve_parameter_templates"), (
            "resolve_parameter_templates import should have been removed"
        )


class TestAgenticExecutorParametersPromptValidatorIntegration:
    """Integration tests verifying the validator works with model_validate."""

    def test_long_prompt_accepted_via_model_validate(self) -> None:
        """Long prompts pass Pydantic validation — length check is in the activity."""
        config = AgenticExecutorParameters.model_validate({"timeout": 300, "prompt": "x" * 200000})
        assert len(config.prompt) == 200000

    def test_null_byte_validation_via_model_validate(self) -> None:
        """Null byte detection fires when using model_validate (dict input)."""
        with pytest.raises(ValidationError):
            AgenticExecutorParameters.model_validate({"timeout": 300, "prompt": "hello\0world"})

    def test_valid_prompt_with_all_fields_via_model_validate(self) -> None:
        """Full config with valid prompt passes validation through model_validate."""
        config = AgenticExecutorParameters.model_validate(
            {
                "prompt": "Analyze the following data",
                "agent": "analyzer",
                "timeout": 120,
                "file_ids": ["550e8400-e29b-41d4-a716-446655440000"],
            }
        )
        assert config.prompt == "Analyze the following data"
        assert config.agent == "analyzer"
