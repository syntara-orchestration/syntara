"""Unit tests for ExecutionIncludeParams model validation."""

import pytest
from pydantic import ValidationError

from syntara.workflows.models.execution import ExecutionInclude
from syntara.workflows.models.query_params import ExecutionIncludeParams


class TestExecutionIncludeParamsValidation:
    """Test ExecutionIncludeParams validation logic."""

    def test_include_none_is_valid(self) -> None:
        """Test that None include value is valid."""
        params = ExecutionIncludeParams(include=None)
        assert params.include is None
        assert params.get_include_set() is None

    def test_include_empty_string_is_valid(self) -> None:
        """Test that empty string include value is valid."""
        params = ExecutionIncludeParams(include="")
        assert params.include == ""
        assert params.get_include_set() is None

    def test_single_valid_include_workflow_definition(self) -> None:
        """Test single valid include value: workflow_definition."""
        params = ExecutionIncludeParams(include="workflow_definition")
        assert params.include == "workflow_definition"

        include_set = params.get_include_set()
        assert include_set == {ExecutionInclude.WORKFLOW_DEFINITION}

    def test_single_valid_include_activities(self) -> None:
        """Test single valid include value: activities."""
        params = ExecutionIncludeParams(include="activities")
        assert params.include == "activities"

        include_set = params.get_include_set()
        assert include_set == {ExecutionInclude.ACTIVITIES}

    def test_multiple_valid_includes_comma_separated(self) -> None:
        """Test multiple valid include values: workflow_definition,activities."""
        params = ExecutionIncludeParams(include="workflow_definition,activities")
        assert params.include == "workflow_definition,activities"

        include_set = params.get_include_set()
        assert include_set == {ExecutionInclude.WORKFLOW_DEFINITION, ExecutionInclude.ACTIVITIES}

    def test_multiple_valid_includes_reverse_order(self) -> None:
        """Test multiple valid include values in reverse order: activities,workflow_definition."""
        params = ExecutionIncludeParams(include="activities,workflow_definition")
        assert params.include == "activities,workflow_definition"

        include_set = params.get_include_set()
        assert include_set == {ExecutionInclude.WORKFLOW_DEFINITION, ExecutionInclude.ACTIVITIES}

    def test_include_with_spaces_is_trimmed(self) -> None:
        """Test that include values with spaces are properly trimmed."""
        params = ExecutionIncludeParams(include=" workflow_definition , activities ")
        assert params.include == " workflow_definition , activities "

        include_set = params.get_include_set()
        assert include_set == {ExecutionInclude.WORKFLOW_DEFINITION, ExecutionInclude.ACTIVITIES}

    def test_invalid_include_value_raises_validation_error(self) -> None:
        """Test that invalid include value raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ExecutionIncludeParams(include="invalid_value")

        error = exc_info.value
        assert len(error.errors()) == 1
        assert error.errors()[0]["type"] == "value_error"
        assert "Invalid include values: invalid_value" in str(error)

    def test_partially_invalid_include_values_raises_validation_error(self) -> None:
        """Test that partially invalid include values raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ExecutionIncludeParams(include="workflow_definition,invalid_value")

        error = exc_info.value
        assert len(error.errors()) == 1
        assert error.errors()[0]["type"] == "value_error"
        assert "Invalid include values: invalid_value" in str(error)

    def test_duplicate_include_values_raise_validation_error(self) -> None:
        """Test that duplicate include values raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ExecutionIncludeParams(include="activities,activities")

        error = exc_info.value
        assert len(error.errors()) == 1
        assert error.errors()[0]["type"] == "value_error"
        assert "Duplicate include values are not allowed" in str(error)

    def test_duplicate_mixed_values_raise_validation_error(self) -> None:
        """Test that duplicate mixed include values raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ExecutionIncludeParams(include="workflow_definition,activities,workflow_definition")

        error = exc_info.value
        assert len(error.errors()) == 1
        assert error.errors()[0]["type"] == "value_error"
        assert "Duplicate include values are not allowed" in str(error)

    def test_validation_error_shows_valid_values(self) -> None:
        """Test that validation error shows all valid values."""
        with pytest.raises(ValidationError) as exc_info:
            ExecutionIncludeParams(include="bad_value")

        error_message = str(exc_info.value)
        assert "activities" in error_message
        assert "workflow_definition" in error_message
        assert "Valid values are:" in error_message


class TestExecutionIncludeParamsGetIncludeSet:
    """Test ExecutionIncludeParams.get_include_set() method."""

    def test_get_include_set_none_returns_none(self) -> None:
        """Test get_include_set returns None when include is None."""
        params = ExecutionIncludeParams(include=None)
        assert params.get_include_set() is None

    def test_get_include_set_empty_returns_none(self) -> None:
        """Test get_include_set returns None when include is empty."""
        params = ExecutionIncludeParams(include="")
        assert params.get_include_set() is None

    def test_get_include_set_single_value(self) -> None:
        """Test get_include_set with single value."""
        params = ExecutionIncludeParams(include="workflow_definition")
        include_set = params.get_include_set()

        assert isinstance(include_set, set)
        assert len(include_set) == 1
        assert ExecutionInclude.WORKFLOW_DEFINITION in include_set

    def test_get_include_set_multiple_values(self) -> None:
        """Test get_include_set with multiple values."""
        params = ExecutionIncludeParams(include="workflow_definition,activities")
        include_set = params.get_include_set()

        assert isinstance(include_set, set)
        assert len(include_set) == 2
        assert ExecutionInclude.WORKFLOW_DEFINITION in include_set
        assert ExecutionInclude.ACTIVITIES in include_set

    def test_get_include_set_returns_enum_instances(self) -> None:
        """Test that get_include_set returns actual ExecutionInclude enum instances."""
        params = ExecutionIncludeParams(include="activities")
        include_set = params.get_include_set()

        assert include_set is not None
        for item in include_set:
            assert isinstance(item, ExecutionInclude)
            assert item.value == "activities"


class TestExecutionIncludeParamsEdgeCases:
    """Test edge cases and special scenarios."""

    def test_single_comma_only_raises_validation_error(self) -> None:
        """Test that single comma raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ExecutionIncludeParams(include=",")

        error = exc_info.value
        assert len(error.errors()) == 1
        assert error.errors()[0]["type"] == "value_error"

    def test_multiple_commas_only_raises_validation_error(self) -> None:
        """Test that multiple commas only raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ExecutionIncludeParams(include=",,")

        error = exc_info.value
        assert len(error.errors()) == 1
        assert error.errors()[0]["type"] == "value_error"

    def test_trailing_comma_raises_validation_error(self) -> None:
        """Test that trailing comma raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ExecutionIncludeParams(include="activities,")

        error = exc_info.value
        assert len(error.errors()) == 1
        assert error.errors()[0]["type"] == "value_error"

    def test_leading_comma_raises_validation_error(self) -> None:
        """Test that leading comma raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ExecutionIncludeParams(include=",activities")

        error = exc_info.value
        assert len(error.errors()) == 1
        assert error.errors()[0]["type"] == "value_error"

    def test_case_sensitivity_invalid_values(self) -> None:
        """Test that include values are case-sensitive."""
        with pytest.raises(ValidationError) as exc_info:
            ExecutionIncludeParams(include="WORKFLOW_DEFINITION")

        error = exc_info.value
        assert len(error.errors()) == 1
        assert error.errors()[0]["type"] == "value_error"
        assert "Invalid include values: WORKFLOW_DEFINITION" in str(error)
