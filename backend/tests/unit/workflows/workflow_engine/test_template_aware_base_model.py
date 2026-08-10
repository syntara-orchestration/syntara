"""Unit tests for TemplateAwareBaseModel.

Tests that template expressions (${...}) bypass validation for all field types
while literal values are validated with full constraints.
"""

import pytest
from pydantic import Field, ValidationError

from syntara.workflows.workflow_engine.models.workflow_definition import (
    AgenticExecutorParameters,
    ScriptExecutorParameters,
    ScriptLanguage,
    TemplateAwareBaseModel,
)


class _IntModel(TemplateAwareBaseModel):
    """Minimal model with a constrained int field for testing TemplateAwareBaseModel."""

    count: int = Field(ge=1, le=3600)


class TestTemplateAwareBaseModel:
    """Test TemplateAwareBaseModel validation behavior."""

    def test_int_field_accepts_literal_template_and_rejects_invalid(self) -> None:
        """Test int field with constraints: accepts literal/template, rejects invalid."""
        # Literal value within range (ge=1, le=3600)
        model = _IntModel(count=50)
        assert model.count == 50

        # Template expression bypasses validation
        model = _IntModel(count="${input.count}")  # type: ignore[arg-type]
        assert model.count == "${input.count}"  # type: ignore[comparison-overlap]

        # Literal value exceeds maximum - rejected
        with pytest.raises(ValidationError) as exc_info:
            _IntModel(count=5000)
        assert "less than or equal to 3600" in str(exc_info.value)

    def test_string_field_accepts_template(self) -> None:
        """Test string field accepts template expressions."""
        config = ScriptExecutorParameters(language="${input.lang}", code="${input.script}")  # type: ignore[arg-type]
        assert config.language == "${input.lang}"
        assert config.code == "${input.script}"

    def test_multiple_fields_with_mixed_values(self) -> None:
        """Test multiple fields can mix literal and template values."""
        config = AgenticExecutorParameters(
            prompt="Analyze this data",  # Literal string
            agent="${input.agent}",  # Template string
        )
        assert config.prompt == "Analyze this data"
        assert config.agent == "${input.agent}"

        # Template in constrained int field bypasses validation
        model = _IntModel(count="${input.count}")  # type: ignore[arg-type]  # Would fail if literal > 3600
        assert model.count == "${input.count}"  # type: ignore[comparison-overlap]

    def test_mixed_template_expressions_in_single_value(self) -> None:
        """Test that values containing ${...} are treated as templates."""
        # Partial template (mixed with literal text)
        config = ScriptExecutorParameters(language=ScriptLanguage.BASH, code="echo ${input.message} and ${input.other}")
        assert config.code == "echo ${input.message} and ${input.other}"

    def test_malformed_template_string_rejected(self) -> None:
        """Test that malformed template strings are treated as literals and rejected."""
        # Missing closing brace - doesn't match template pattern, fails int validation
        with pytest.raises(ValidationError) as exc_info:
            _IntModel(count="${input.count")  # type: ignore[arg-type]
        assert "Input should be a valid integer" in str(exc_info.value)

    def test_invalid_type_applied_to_int_field_rejected(self) -> None:
        """Test that invalid types are rejected for int fields."""
        # List cannot be coerced to int - should be rejected
        with pytest.raises(ValidationError) as exc_info:
            _IntModel(count=["invalid"])  # type: ignore[arg-type]
        assert "Input should be a valid integer" in str(exc_info.value)
