"""Contract tests for filter parser functionality.

These tests verify the FilterParser utility can parse bracket notation query
parameters into structured filter objects. Tests will fail until FilterParser
is implemented.
"""

from enum import Enum
from unittest.mock import MagicMock

import pytest

from syntara.core.exceptions import SafeValueError
from syntara.core.utils.filters import (
    Filter,
    FilterOperator,
    _convert_filter_value,
    _sanitize_like_value,
    matches_query_param,
    parse_filters,
)


class TestFilterParser:
    """Test filter parsing functionality."""

    def test_filter_parser_import(self) -> None:
        """Test that filter functions and related classes can be imported."""
        # This will fail until filter functions are implemented

        assert parse_filters is not None
        assert Filter is not None
        assert FilterOperator is not None

    def test_filter_operator_enum_values(self) -> None:
        """Test that FilterOperator enum has expected values."""
        # Check all required operators exist
        assert FilterOperator.EQ.value == "eq"
        assert FilterOperator.IN.value == "in"
        assert FilterOperator.CONTAINS.value == "contains"
        assert FilterOperator.STARTS_WITH.value == "starts_with"
        assert FilterOperator.GT.value == "gt"
        assert FilterOperator.GTE.value == "gte"
        assert FilterOperator.LT.value == "lt"
        assert FilterOperator.LTE.value == "lte"
        assert FilterOperator.ISNULL.value == "isnull"

    def test_filter_dataclass_structure(self) -> None:
        """Test that Filter dataclass has expected structure."""
        # Create a filter instance
        filter_obj = Filter(field="name", operator=FilterOperator.CONTAINS, value="test")

        assert filter_obj.field == "name"
        assert filter_obj.operator == FilterOperator.CONTAINS
        assert filter_obj.value == "test"

    def test_filter_parser_parse_method_exists(self) -> None:
        """Test that parse_filters function exists."""
        assert callable(parse_filters)

    def test_parse_simple_equality_filter(self) -> None:
        """Test parsing simple equality filter (shorthand syntax)."""
        params = {"name": "test-resource"}
        allowed_fields = ["name", "status"]

        filters = parse_filters(params, allowed_fields)

        assert len(filters) == 1
        assert filters[0].field == "name"
        assert filters[0].operator == FilterOperator.EQ
        assert filters[0].value == "test-resource"

    def test_parse_bracket_notation_filter(self) -> None:
        """Test parsing bracket notation filter with operator."""
        params = {"name[contains]": "auth"}
        allowed_fields = ["name", "status"]

        filters = parse_filters(params, allowed_fields)

        assert len(filters) == 1
        assert filters[0].field == "name"
        assert filters[0].operator == FilterOperator.CONTAINS
        assert filters[0].value == "auth"

    def test_parse_multiple_filters(self) -> None:
        """Test parsing multiple filters with different operators."""
        params = {"name[contains]": "service", "status": "active", "created_at[gte]": "2025-01-01T00:00:00Z"}
        allowed_fields = ["name", "status", "created_at"]

        filters = parse_filters(params, allowed_fields)

        assert len(filters) == 3

        # Find each filter by field name
        name_filter = next(f for f in filters if f.field == "name")
        assert name_filter.operator == FilterOperator.CONTAINS
        assert name_filter.value == "service"

        status_filter = next(f for f in filters if f.field == "status")
        assert status_filter.operator == FilterOperator.EQ
        assert status_filter.value == "active"

        created_filter = next(f for f in filters if f.field == "created_at")
        assert created_filter.operator == FilterOperator.GTE
        assert created_filter.value == "2025-01-01T00:00:00Z"

    def test_parse_all_operators(self) -> None:
        """Test parsing filters with all supported operators."""
        params = {
            "name[eq]": "exact",
            "name[in]": "val1,val2",
            "name[contains]": "substring",
            "name[starts_with]": "prefix",
            "created_at[gt]": "2025-01-01T00:00:00Z",
            "created_at[gte]": "2025-01-01T00:00:00Z",
            "created_at[lt]": "2025-12-31T23:59:59Z",
            "created_at[lte]": "2025-12-31T23:59:59Z",
            "status[isnull]": "true",
        }
        allowed_fields = ["name", "created_at", "status"]

        filters = parse_filters(params, allowed_fields)

        # 9 params but name[in]=val1,val2 splits into 2 filters → 10 total
        assert len(filters) == 10

        # Check each operator was parsed correctly
        operators_found = {f.operator for f in filters}
        expected_operators = {
            FilterOperator.EQ,
            FilterOperator.IN,
            FilterOperator.CONTAINS,
            FilterOperator.STARTS_WITH,
            FilterOperator.GT,
            FilterOperator.GTE,
            FilterOperator.LT,
            FilterOperator.LTE,
            FilterOperator.ISNULL,
        }
        assert operators_found == expected_operators

    def test_parse_isnull_true(self) -> None:
        """Test parsing isnull=true filter."""
        params = {"principal_id[isnull]": "true"}
        allowed_fields = ["principal_id"]

        filters = parse_filters(params, allowed_fields)

        assert len(filters) == 1
        assert filters[0].field == "principal_id"
        assert filters[0].operator == FilterOperator.ISNULL
        assert filters[0].value == "true"

    def test_parse_isnull_false(self) -> None:
        """Test parsing isnull=false filter."""
        params = {"group_id[isnull]": "false"}
        allowed_fields = ["group_id"]

        filters = parse_filters(params, allowed_fields)

        assert len(filters) == 1
        assert filters[0].field == "group_id"
        assert filters[0].operator == FilterOperator.ISNULL
        assert filters[0].value == "false"

    def test_parse_isnull_combined_with_other_filters(self) -> None:
        """Test parsing isnull alongside other filter operators."""
        params = {
            "principal_id[isnull]": "true",
            "role_name[contains]": "admin",
        }
        allowed_fields = ["principal_id", "role_name"]

        filters = parse_filters(params, allowed_fields)

        assert len(filters) == 2

        isnull_filter = next(f for f in filters if f.operator == FilterOperator.ISNULL)
        assert isnull_filter.field == "principal_id"
        assert isnull_filter.value == "true"

        contains_filter = next(f for f in filters if f.operator == FilterOperator.CONTAINS)
        assert contains_filter.field == "role_name"
        assert contains_filter.value == "admin"

    def test_parse_invalid_field_raises_error(self) -> None:
        """Test that invalid field names raise SafeValueError."""
        params = {"invalid_field": "value"}
        allowed_fields = ["name", "status"]

        with pytest.raises(SafeValueError, match="Invalid field"):
            parse_filters(params, allowed_fields)

    def test_parse_invalid_operator_raises_error(self) -> None:
        """Test that invalid operators raise SafeValueError."""
        params = {"name[invalid_op]": "value"}
        allowed_fields = ["name"]

        with pytest.raises(SafeValueError, match="Invalid operator"):
            parse_filters(params, allowed_fields)

    def test_parse_empty_params(self) -> None:
        """Test parsing empty parameters returns empty list."""
        filters = parse_filters({}, ["name", "status"])
        assert filters == []

    def test_parse_comma_separated_values(self) -> None:
        """Test parsing comma-separated values creates multiple filters."""
        params = {"status": "active,pending"}
        allowed_fields = ["status"]

        filters = parse_filters(params, allowed_fields)

        # Should create multiple filters for OR logic
        assert len(filters) == 2
        assert all(f.field == "status" for f in filters)
        assert all(f.operator == FilterOperator.EQ for f in filters)

        values = {f.value for f in filters}
        assert values == {"active", "pending"}

    def test_parse_comma_separated_values_with_bracket_notation(self) -> None:
        """Test logical OR with comma-separated values using bracket notation and various operators."""
        # Test OR logic with contains operator
        params = {"name[contains]": "service,api,worker"}
        allowed_fields = ["name"]

        filters = parse_filters(params, allowed_fields)

        # Should create 3 filters for OR logic: name contains "service" OR "api" OR "worker"
        assert len(filters) == 3
        assert all(f.field == "name" for f in filters)
        assert all(f.operator == FilterOperator.CONTAINS for f in filters)

        values = {f.value for f in filters}
        assert values == {"service", "api", "worker"}

    def test_parse_comma_separated_values_multiple_fields_and_operators(self) -> None:
        """Test OR logic with multiple fields using different operators."""
        params = {
            "status": "active,pending,draft",  # Shorthand: status=active OR pending OR draft
            "priority[gte]": "1,3,5",  # Bracket: priority >= 1 OR >= 3 OR >= 5
            "name[starts_with]": "test,demo",  # Bracket: name starts_with "test" OR "demo"
        }
        allowed_fields = ["status", "priority", "name"]

        filters = parse_filters(params, allowed_fields)

        # Should create 8 filters total (3 + 3 + 2)
        assert len(filters) == 8

        # Check status filters (shorthand equality)
        status_filters = [f for f in filters if f.field == "status"]
        assert len(status_filters) == 3
        assert all(f.operator == FilterOperator.EQ for f in status_filters)
        status_values = {f.value for f in status_filters}
        assert status_values == {"active", "pending", "draft"}

        # Check priority filters (bracket notation with gte)
        priority_filters = [f for f in filters if f.field == "priority"]
        assert len(priority_filters) == 3
        assert all(f.operator == FilterOperator.GTE for f in priority_filters)
        priority_values = {f.value for f in priority_filters}
        assert priority_values == {"1", "3", "5"}

        # Check name filters (bracket notation with starts_with)
        name_filters = [f for f in filters if f.field == "name"]
        assert len(name_filters) == 2
        assert all(f.operator == FilterOperator.STARTS_WITH for f in name_filters)
        name_values = {f.value for f in name_filters}
        assert name_values == {"test", "demo"}

    def test_parse_comma_separated_values_with_whitespace(self) -> None:
        """Test that comma-separated values handle whitespace correctly."""
        params = {
            "tags": "frontend, backend , api,  database  ",  # Mixed whitespace
            "type[eq]": " internal,external , hybrid ",  # Whitespace around values
        }
        allowed_fields = ["tags", "type"]

        filters = parse_filters(params, allowed_fields)

        # Should create 7 filters total (4 + 3), with trimmed values
        assert len(filters) == 7

        # Check tags filters (whitespace should be trimmed)
        tag_filters = [f for f in filters if f.field == "tags"]
        assert len(tag_filters) == 4
        tag_values = {f.value for f in tag_filters}
        assert tag_values == {"frontend", "backend", "api", "database"}

        # Check type filters (whitespace should be trimmed)
        type_filters = [f for f in filters if f.field == "type"]
        assert len(type_filters) == 3
        type_values = {f.value for f in type_filters}
        assert type_values == {"internal", "external", "hybrid"}

    def test_parse_bracket_notation_regex(self) -> None:
        """Test that bracket notation regex works correctly."""
        # Test various bracket notation formats
        test_cases = [
            ("name[eq]", "name", "eq"),
            ("created_at[gte]", "created_at", "gte"),
            ("field_name[contains]", "field_name", "contains"),
            ("id[starts_with]", "id", "starts_with"),
        ]

        for param_name, expected_field, expected_operator in test_cases:
            params = {param_name: "test_value"}
            allowed_fields = [expected_field]

            filters = parse_filters(params, allowed_fields)

            assert len(filters) == 1
            assert filters[0].field == expected_field
            assert filters[0].operator.value == expected_operator
            assert filters[0].value == "test_value"

    def test_parse_mixed_notation(self) -> None:
        """Test parsing mix of shorthand and bracket notation."""
        params = {
            "name": "exact_match",  # Shorthand
            "description[contains]": "keyword",  # Bracket notation
            "status[eq]": "active",  # Explicit equality
        }
        allowed_fields = ["name", "description", "status"]

        filters = parse_filters(params, allowed_fields)

        assert len(filters) == 3

        # Shorthand should become EQ
        name_filter = next(f for f in filters if f.field == "name")
        assert name_filter.operator == FilterOperator.EQ

        # Bracket notation should preserve operator
        desc_filter = next(f for f in filters if f.field == "description")
        assert desc_filter.operator == FilterOperator.CONTAINS

        status_filter = next(f for f in filters if f.field == "status")
        assert status_filter.operator == FilterOperator.EQ

    def test_parse_case_sensitive_operators(self) -> None:
        """Test that operator names are case-sensitive."""
        params = {"name[CONTAINS]": "value"}  # Wrong case
        allowed_fields = ["name"]

        with pytest.raises(SafeValueError, match="Invalid operator"):
            parse_filters(params, allowed_fields)

    def test_parse_field_validation(self) -> None:
        """Test field validation against allowed_fields list."""
        allowed_fields = ["name", "status", "created_at"]

        # Valid fields should work
        valid_params = {"name": "test", "status[eq]": "active", "created_at[gte]": "2025-01-01"}
        filters = parse_filters(valid_params, allowed_fields)
        assert len(filters) == 3

        # Invalid field should raise error
        invalid_params = {"unauthorized_field": "value"}
        with pytest.raises(SafeValueError, match="Invalid field: unauthorized_field"):
            parse_filters(invalid_params, allowed_fields)

    def test_parse_special_characters_in_values(self) -> None:
        """Test parsing filter values with special characters."""
        params = {
            "name[contains]": "app-v1.2.3",
            "path[starts_with]": "/api/v1/users",
            "description": "Test with spaces & symbols!",
        }
        allowed_fields = ["name", "path", "description"]

        filters = parse_filters(params, allowed_fields)

        assert len(filters) == 3

        # Values should be preserved exactly
        name_filter = next(f for f in filters if f.field == "name")
        assert name_filter.value == "app-v1.2.3"

        path_filter = next(f for f in filters if f.field == "path")
        assert path_filter.value == "/api/v1/users"

        desc_filter = next(f for f in filters if f.field == "description")
        assert desc_filter.value == "Test with spaces & symbols!"

    def test_parse_boolean_string_values(self) -> None:
        """Test parsing string representations of boolean values."""
        # Test various boolean string representations
        test_cases = [
            ("enabled[eq]", "true", "enabled", FilterOperator.EQ, "true"),
            ("is_active[eq]", "false", "is_active", FilterOperator.EQ, "false"),
            ("active", "1", "active", FilterOperator.EQ, "1"),
            ("disabled[eq]", "0", "disabled", FilterOperator.EQ, "0"),
            ("visible[eq]", "yes", "visible", FilterOperator.EQ, "yes"),
            ("hidden[eq]", "no", "hidden", FilterOperator.EQ, "no"),
            ("online[eq]", "on", "online", FilterOperator.EQ, "on"),
            ("offline[eq]", "off", "offline", FilterOperator.EQ, "off"),
        ]

        for param_notation, param_value, expected_field, expected_operator, expected_value in test_cases:
            params = {param_notation: param_value}
            allowed_fields = [expected_field]

            filters = parse_filters(params, allowed_fields)

            assert len(filters) == 1
            assert filters[0].field == expected_field
            assert filters[0].operator == expected_operator
            assert filters[0].value == expected_value

    def test_parse_boolean_case_insensitive_values(self) -> None:
        """Test parsing boolean values with different cases."""
        test_cases = [
            ("TRUE", "TRUE"),
            ("False", "False"),
            ("TrUe", "TrUe"),
            ("FALSE", "FALSE"),
        ]

        for input_value, expected_value in test_cases:
            params = {"enabled[eq]": input_value}
            allowed_fields = ["enabled"]

            filters = parse_filters(params, allowed_fields)

            assert len(filters) == 1
            assert filters[0].field == "enabled"
            assert filters[0].operator == FilterOperator.EQ
            # Parser should preserve the original string case
            assert filters[0].value == expected_value

    def test_parse_same_field_different_operators_produces_separate_filters(self) -> None:
        """Parse ``field[gte]=X&field[lte]=Y`` as two Filter objects with distinct operators.

        Range filtering (``created_at[gte]=...&created_at[lte]=...``) depends on
        the parser emitting one Filter per operator so ``apply_filters`` can
        AND them together (see TestLogicalANDFiltering in
        test_filter_parser_sqlalchemy.py).
        """
        params = {
            "created_at[gte]": "2025-01-02T00:00:00Z",
            "created_at[lte]": "2025-01-04T00:00:00Z",
        }
        allowed_fields = ["created_at"]

        filters = parse_filters(params, allowed_fields)

        assert len(filters) == 2
        assert {f.field for f in filters} == {"created_at"}
        assert {f.operator for f in filters} == {FilterOperator.GTE, FilterOperator.LTE}

        gte = next(f for f in filters if f.operator == FilterOperator.GTE)
        lte = next(f for f in filters if f.operator == FilterOperator.LTE)
        assert gte.value == "2025-01-02T00:00:00Z"
        assert lte.value == "2025-01-04T00:00:00Z"

    def test_parse_same_field_three_distinct_operators(self) -> None:
        """Parse three distinct operators on the same field as three Filter objects."""
        params = {
            "priority[gt]": "1",
            "priority[lt]": "10",
            "priority[eq]": "5",
        }
        allowed_fields = ["priority"]

        filters = parse_filters(params, allowed_fields)

        assert len(filters) == 3
        assert {f.operator for f in filters} == {
            FilterOperator.GT,
            FilterOperator.LT,
            FilterOperator.EQ,
        }
        assert all(f.field == "priority" for f in filters)

    def test_parse_same_field_same_operator_via_comma_separated(self) -> None:
        """Comma-separated values within a single bracket operator produce one Filter per value.

        Regression guard: the ``apply_filters`` grouping-by-(field, operator)
        must continue to recognise these as OR candidates within the same
        operator group.
        """
        params = {"status[eq]": "active,pending,draft"}
        allowed_fields = ["status"]

        filters = parse_filters(params, allowed_fields)

        assert len(filters) == 3
        assert all(f.field == "status" for f in filters)
        assert all(f.operator == FilterOperator.EQ for f in filters)
        assert {f.value for f in filters} == {"active", "pending", "draft"}

    def test_parse_in_operator_single_value(self) -> None:
        """Test that ``status[in]=pending`` produces a single IN filter."""
        params = {"status[in]": "pending"}
        allowed_fields = ["status"]

        filters = parse_filters(params, allowed_fields)

        assert len(filters) == 1
        assert filters[0].field == "status"
        assert filters[0].operator == FilterOperator.IN
        assert filters[0].value == "pending"

    def test_parse_in_operator_comma_separated(self) -> None:
        """Test that ``status[in]=pending,expired`` produces multiple IN filters for OR logic."""
        params = {"status[in]": "pending,expired"}
        allowed_fields = ["status"]

        filters = parse_filters(params, allowed_fields)

        assert len(filters) == 2
        assert all(f.field == "status" for f in filters)
        assert all(f.operator == FilterOperator.IN for f in filters)
        assert {f.value for f in filters} == {"pending", "expired"}

    def test_parse_in_operator_with_whitespace(self) -> None:
        """Test that ``status[in]=pending, expired , cancelled`` trims whitespace."""
        params = {"status[in]": "pending, expired , cancelled"}
        allowed_fields = ["status"]

        filters = parse_filters(params, allowed_fields)

        assert len(filters) == 3
        assert {f.value for f in filters} == {"pending", "expired", "cancelled"}

    def test_parse_in_operator_empty_value_skipped(self) -> None:
        """Test that ``field[in]=`` produces no filters (blank values are skipped)."""
        params = {"status[in]": ""}
        allowed_fields = ["status"]

        filters = parse_filters(params, allowed_fields)
        assert len(filters) == 0

    def test_parse_in_operator_trailing_comma_skips_blank(self) -> None:
        """Test that ``field[in]=pending,`` skips the trailing blank."""
        params = {"status[in]": "pending,"}
        allowed_fields = ["status"]

        filters = parse_filters(params, allowed_fields)
        assert len(filters) == 1
        assert filters[0].value == "pending"

    def test_parse_shorthand_empty_value_preserved(self) -> None:
        """Test that ``field=`` produces a filter for the empty string."""
        params = {"status": ""}
        allowed_fields = ["status"]

        filters = parse_filters(params, allowed_fields)
        assert len(filters) == 1
        assert filters[0].value == ""
        assert filters[0].operator == FilterOperator.EQ

    def test_parse_shorthand_trailing_comma_preserves_blank(self) -> None:
        """Test that ``field=active,`` preserves the trailing blank segment."""
        params = {"status": "active,"}
        allowed_fields = ["status"]

        filters = parse_filters(params, allowed_fields)
        assert len(filters) == 2
        assert filters[0].value == "active"
        assert filters[1].value == ""

    def test_parse_in_operator_with_other_filters(self) -> None:
        """Test ``[in]`` combined with other operators using AND logic between fields."""
        params = {
            "status[in]": "pending,expired",
            "name[contains]": "workflow",
        }
        allowed_fields = ["status", "name"]

        filters = parse_filters(params, allowed_fields)

        assert len(filters) == 3

        status_filters = [f for f in filters if f.field == "status"]
        assert len(status_filters) == 2
        assert all(f.operator == FilterOperator.IN for f in status_filters)

        name_filters = [f for f in filters if f.field == "name"]
        assert len(name_filters) == 1
        assert name_filters[0].operator == FilterOperator.CONTAINS


class MockStatus(str, Enum):
    """Mock enum for unit testing."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"


class TestFilterValueConversion:
    """Test the _convert_filter_value function for type conversion and validation."""

    def test_convert_filter_value_enum_valid(self) -> None:
        """Test converting valid enum values."""
        # Mock field attribute for enum field
        field_attr = MagicMock()
        field_attr.type.python_type = MockStatus
        field_attr.key = "status"

        # Test valid enum value
        result = _convert_filter_value("active", field_attr)
        assert result == MockStatus.ACTIVE
        assert isinstance(result, MockStatus)

        # Test another valid enum value
        result = _convert_filter_value("pending", field_attr)
        assert result == MockStatus.PENDING
        assert isinstance(result, MockStatus)

    def test_convert_filter_value_enum_invalid(self) -> None:
        """Test converting invalid enum values raises SafeValueError."""
        # Mock field attribute for enum field
        field_attr = MagicMock()
        field_attr.type.python_type = MockStatus
        field_attr.key = "status"

        # Test invalid enum value
        with pytest.raises(SafeValueError, match="Invalid value 'nonexistent' for field 'status'") as exc_info:
            _convert_filter_value("nonexistent", field_attr)

        error_message = str(exc_info.value)
        assert "Invalid value 'nonexistent' for field 'status'" in error_message
        assert "Valid values are:" in error_message
        assert "active" in error_message
        assert "inactive" in error_message
        assert "pending" in error_message

    def test_convert_filter_value_enum_case_sensitive(self) -> None:
        """Test that enum validation is case-sensitive."""
        # Mock field attribute for enum field
        field_attr = MagicMock()
        field_attr.type.python_type = MockStatus
        field_attr.key = "status"

        # Test case sensitivity - uppercase should fail
        with pytest.raises(SafeValueError, match="Invalid value 'ACTIVE' for field 'status'") as exc_info:
            _convert_filter_value("ACTIVE", field_attr)

        assert "Invalid value 'ACTIVE' for field 'status'" in str(exc_info.value)

        # Test case sensitivity - mixed case should fail
        with pytest.raises(SafeValueError, match="Invalid value 'Active' for field 'status'"):
            _convert_filter_value("Active", field_attr)

    def test_convert_filter_value_non_enum_passthrough(self) -> None:
        """Test that non-enum fields pass through unchanged."""
        # Mock field attribute for string field
        field_attr = MagicMock()
        field_attr.type.python_type = str
        field_attr.key = "name"

        # Should pass through unchanged
        result = _convert_filter_value("test_value", field_attr)
        assert result == "test_value"
        assert isinstance(result, str)

    def test_convert_filter_value_non_string_input(self) -> None:
        """Test that non-string input passes through unchanged."""
        # Mock field attribute for enum field
        field_attr = MagicMock()
        field_attr.type.python_type = MockStatus
        field_attr.key = "status"

        # Non-string input should pass through
        enum_value = MockStatus.ACTIVE
        result = _convert_filter_value(enum_value, field_attr)
        assert result == enum_value

        # Integer input should pass through
        result = _convert_filter_value(42, field_attr)
        assert result == 42

    def test_convert_filter_value_enum_error_message_format(self) -> None:
        """Test that enum validation error messages are properly formatted."""
        # Mock field attribute with unknown field name
        field_attr = MagicMock()
        field_attr.type.python_type = MockStatus
        field_attr.key = "test_field"

        with pytest.raises(SafeValueError, match="Invalid value 'invalid_value' for field 'test_field'") as exc_info:
            _convert_filter_value("invalid_value", field_attr)

        error_message = str(exc_info.value)

        # Should include field name
        assert "test_field" in error_message

        # Should include the invalid value
        assert "invalid_value" in error_message

        # Should list all valid values
        assert "active, inactive, pending" in error_message

    def test_convert_filter_value_enum_field_without_key(self) -> None:
        """Test enum validation when field attribute has no key."""
        # Mock field attribute without key
        field_attr = MagicMock()
        field_attr.type.python_type = MockStatus
        del field_attr.key  # Remove key attribute

        with pytest.raises(SafeValueError, match="Invalid value 'invalid' for field 'unknown'") as exc_info:
            _convert_filter_value("invalid", field_attr)

        error_message = str(exc_info.value)
        # Should fall back to "unknown" when no key is available
        assert "unknown" in error_message

    def test_convert_filter_value_enum_subclass_detection(self) -> None:
        """Test that enum subclass detection works correctly."""
        # Mock field attribute for non-enum class
        field_attr = MagicMock()
        field_attr.type.python_type = str  # Not an enum
        field_attr.key = "text_field"

        # Should not trigger enum validation
        result = _convert_filter_value("any_value", field_attr)
        assert result == "any_value"

        # Mock field attribute that fails isinstance check
        field_attr.type.python_type = None
        result = _convert_filter_value("any_value", field_attr)
        assert result == "any_value"


class TestSQLInjectionProtection:
    """Test SQL injection protection in filter values."""

    def test_sanitize_like_value_function_exists(self) -> None:
        """Test that _sanitize_like_value function exists."""
        assert callable(_sanitize_like_value)

    def test_sanitize_like_value_escapes_percent_wildcard(self) -> None:
        """Test that % wildcard is properly escaped."""
        # Test basic % escape
        result = _sanitize_like_value("test%value")
        assert result == "test\\%value"

        # Test multiple % characters
        result = _sanitize_like_value("%start%middle%end%")
        assert result == "\\%start\\%middle\\%end\\%"

        # Test SQL injection attempt with %
        injection_attempt = "'; DROP TABLE users; --"
        result = _sanitize_like_value(injection_attempt)
        assert result == injection_attempt  # Should pass through, only escapes % and _

    def test_sanitize_like_value_escapes_underscore_wildcard(self) -> None:
        """Test that _ wildcard is properly escaped."""
        # Test basic _ escape
        result = _sanitize_like_value("test_value")
        assert result == "test\\_value"

        # Test multiple _ characters
        result = _sanitize_like_value("_start_middle_end_")
        assert result == "\\_start\\_middle\\_end\\_"

        # Test combination of patterns
        result = _sanitize_like_value("file_name.txt")
        assert result == "file\\_name.txt"

    def test_sanitize_like_value_escapes_backslash(self) -> None:
        """Test that backslashes are properly escaped."""
        # Test basic backslash escape
        result = _sanitize_like_value("path\\to\\file")
        assert result == "path\\\\to\\\\file"

        # Test backslash with wildcards
        result = _sanitize_like_value("\\%_test")
        assert result == "\\\\\\%\\_test"

    def test_sanitize_like_value_combination_patterns(self) -> None:
        """Test sanitization of values with multiple special characters."""
        # Test all patterns together
        result = _sanitize_like_value("test\\_%value%_end")
        assert result == "test\\\\\\_\\%value\\%\\_end"

        # Test realistic SQL injection attempts
        injection_patterns = [
            "user%'; DROP TABLE--",
            "_admin' OR 1=1--",
            "\\'; DELETE FROM users WHERE 1=1; --",
            "%' UNION SELECT * FROM passwords--",
        ]

        for pattern in injection_patterns:
            result = _sanitize_like_value(pattern)
            # Should escape wildcards but leave other characters
            expected = pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            assert result == expected

    def test_sanitize_like_value_non_string_input(self) -> None:
        """Test that non-string values are converted to string first."""
        # Test integer
        result = _sanitize_like_value(123)
        assert result == "123"

        # Test float
        result = _sanitize_like_value(45.67)
        assert result == "45.67"

        # Test boolean
        result = _sanitize_like_value(True)  # noqa: FBT003
        assert result == "True"

    def test_sanitize_like_value_empty_string(self) -> None:
        """Test sanitization of empty string."""
        result = _sanitize_like_value("")
        assert result == ""

    def test_sanitize_like_value_only_wildcards(self) -> None:
        """Test sanitization of strings containing only wildcards."""
        result = _sanitize_like_value("%%%")
        assert result == "\\%\\%\\%"

        result = _sanitize_like_value("___")
        assert result == "\\_\\_\\_"

        result = _sanitize_like_value("%_%")
        assert result == "\\%\\_\\%"


class TestMalformedFilterSyntax:
    """Test handling of malformed filter syntax."""

    def test_malformed_bracket_notation_missing_closing(self) -> None:
        """Test malformed bracket notation with missing closing bracket."""
        params = {"name[contains": "value"}  # Missing ]
        allowed_fields = ["name"]

        # Should be treated as shorthand notation (field name is "name[contains")
        with pytest.raises(SafeValueError, match="Invalid field"):
            parse_filters(params, allowed_fields)

    def test_malformed_bracket_notation_missing_opening(self) -> None:
        """Test malformed bracket notation with missing opening bracket."""
        params = {"namecontains]": "value"}  # Missing [
        allowed_fields = ["name"]

        # Should be treated as shorthand notation (field name is "namecontains]")
        with pytest.raises(SafeValueError, match="Invalid field"):
            parse_filters(params, allowed_fields)

    def test_malformed_bracket_notation_empty_operator(self) -> None:
        """Test malformed bracket notation with empty operator."""
        params = {"name[]": "value"}  # Empty operator
        allowed_fields = ["name"]

        # Should fail due to empty operator
        with pytest.raises(SafeValueError, match="Invalid operator"):
            parse_filters(params, allowed_fields)

    def test_malformed_bracket_notation_nested_brackets(self) -> None:
        """Test malformed bracket notation with nested brackets."""
        params = {"name[contains[eq]]": "value"}  # Nested brackets
        allowed_fields = ["name"]

        # Should be treated as shorthand notation
        with pytest.raises(SafeValueError, match="Invalid field"):
            parse_filters(params, allowed_fields)

    def test_malformed_bracket_notation_multiple_brackets(self) -> None:
        """Test malformed bracket notation with multiple bracket pairs."""
        params = {"name[contains][eq]": "value"}  # Multiple bracket pairs
        allowed_fields = ["name"]

        # Should be treated as shorthand notation
        with pytest.raises(SafeValueError, match="Invalid field"):
            parse_filters(params, allowed_fields)

    def test_malformed_bracket_notation_spaces_in_operator(self) -> None:
        """Test bracket notation with spaces in operator."""
        params = {"name[contains value]": "test"}  # Space in operator
        allowed_fields = ["name"]

        # Should fail due to invalid operator
        with pytest.raises(SafeValueError, match="Invalid operator"):
            parse_filters(params, allowed_fields)

    def test_malformed_bracket_notation_special_chars_in_operator(self) -> None:
        """Test bracket notation with special characters in operator."""
        invalid_operators = [
            "name[con-tains]",  # Hyphen
            "name[con.tains]",  # Dot
            "name[con/tains]",  # Slash
            "name[con@tains]",  # At symbol
            "name[con#tains]",  # Hash
        ]
        allowed_fields = ["name"]

        for param_name in invalid_operators:
            params = {param_name: "value"}
            with pytest.raises(SafeValueError, match="Invalid operator"):
                parse_filters(params, allowed_fields)

    def test_malformed_field_name_patterns(self) -> None:
        """Test various malformed field name patterns."""
        malformed_patterns = [
            "[field]",  # Field name starting with bracket
            "field]",  # Field name ending with bracket
            "fie[ld",  # Field name with unmatched bracket
            "field[[",  # Field name with double brackets
            "field]]",  # Field name with double closing brackets
        ]
        allowed_fields = ["name", "status"]

        for pattern in malformed_patterns:
            params = {pattern: "value"}
            # Should fail due to invalid field name
            with pytest.raises(SafeValueError, match="Invalid field"):
                parse_filters(params, allowed_fields)

    def test_malformed_bracket_notation_unicode_operators(self) -> None:
        """Test bracket notation with unicode characters in operators."""
        params = {"name[contáins]": "value"}  # Unicode in operator
        allowed_fields = ["name"]

        with pytest.raises(SafeValueError, match="Invalid operator"):
            parse_filters(params, allowed_fields)

    def test_bracket_notation_regex_edge_cases(self) -> None:
        """Test edge cases for bracket notation regex pattern."""
        # Valid patterns that should work
        valid_patterns = {
            "field.with.dots[eq]": ("field.with.dots", "eq"),
            "field_with_underscores[contains]": ("field_with_underscores", "contains"),
            "fieldwithdigits123[starts_with]": ("fieldwithdigits123", "starts_with"),
        }

        for param_name, (expected_field, expected_operator) in valid_patterns.items():
            params = {param_name: "test"}
            allowed_fields = [expected_field]

            filters = parse_filters(params, allowed_fields)
            assert len(filters) == 1
            assert filters[0].field == expected_field
            assert filters[0].operator.value == expected_operator

        # Invalid patterns that should fail
        invalid_patterns = [
            "field name[eq]",  # Space in field name
            "field-name[eq]",  # Hyphen in field name
            "field/name[eq]",  # Slash in field name
            "123field[eq]",  # Field starting with number
        ]

        for param_name in invalid_patterns:
            params = {param_name: "test"}
            allowed_fields = ["field", "name"]

            # Should be treated as shorthand notation with invalid field
            with pytest.raises(SafeValueError, match="Invalid field"):
                parse_filters(params, allowed_fields)


class TestSensitiveFieldProtection:
    """Test that sensitive fields on the User model cannot be used as filter parameters.

    Guards against password hash leakage via query parameter filtering (AAP-71239).
    """

    def test_password_hash_not_in_filterable_fields(self) -> None:
        """Verify password_hash is excluded from User.__filterable_fields__."""
        from syntara.core.models.user import User

        assert "password_hash" not in User.__filterable_fields__

    def test_sensitive_fields_not_in_filterable_fields(self) -> None:
        """Verify all sensitive User fields are excluded from __filterable_fields__."""
        from syntara.core.models.user import User

        sensitive_fields = ["password_hash", "preferences", "authz_metadata", "token_version"]
        for field in sensitive_fields:
            assert field not in User.__filterable_fields__, f"Sensitive field '{field}' must not be filterable"

    def test_filter_password_hash_eq_rejected(self) -> None:
        """Filtering by password_hash with shorthand equality is rejected."""
        from syntara.core.models.user import User

        with pytest.raises(SafeValueError, match="Invalid field: password_hash"):
            parse_filters({"password_hash": "$argon2id$v=19$m=65536"}, User.__filterable_fields__)

    def test_filter_password_hash_starts_with_rejected(self) -> None:
        """Filtering by password_hash[starts_with] is rejected — the primary attack vector."""
        from syntara.core.models.user import User

        with pytest.raises(SafeValueError, match="Invalid field: password_hash"):
            parse_filters({"password_hash[starts_with]": "$argon2"}, User.__filterable_fields__)

    def test_filter_password_hash_contains_rejected(self) -> None:
        """Filtering by password_hash[contains] is rejected."""
        from syntara.core.models.user import User

        with pytest.raises(SafeValueError, match="Invalid field: password_hash"):
            parse_filters({"password_hash[contains]": "argon"}, User.__filterable_fields__)

    def test_filter_password_hash_all_operators_rejected(self) -> None:
        """Every filter operator is rejected for password_hash."""
        from syntara.core.models.user import User

        operators = ["eq", "in", "contains", "starts_with", "gt", "gte", "lt", "lte"]
        for op in operators:
            with pytest.raises(SafeValueError, match="Invalid field: password_hash"):
                parse_filters({f"password_hash[{op}]": "value"}, User.__filterable_fields__)


class TestMatchesQueryParam:
    """Test in-memory query param matching used by builtin policy/role filtering."""

    def test_in_operator_single_match(self) -> None:
        """Test that [in] matches when value is in the comma-separated list."""
        assert matches_query_param("global", "scope", {"scope[in]": "global,project"}) is True

    def test_in_operator_second_value_match(self) -> None:
        """Test that [in] matches the second value in the list."""
        assert matches_query_param("project", "scope", {"scope[in]": "global,project"}) is True

    def test_in_operator_no_match(self) -> None:
        """Test that [in] returns False when value is not in the list."""
        assert matches_query_param("namespace", "scope", {"scope[in]": "global,project"}) is False

    def test_in_operator_single_value(self) -> None:
        """Test that [in] works with a single value (no commas)."""
        assert matches_query_param("global", "scope", {"scope[in]": "global"}) is True
        assert matches_query_param("project", "scope", {"scope[in]": "global"}) is False

    def test_in_operator_whitespace_handling(self) -> None:
        """Test that [in] strips whitespace from comma-separated values."""
        assert matches_query_param("project", "scope", {"scope[in]": "global, project"}) is True

    def test_no_constraint_returns_true(self) -> None:
        """Test that missing param means no constraint (returns True)."""
        assert matches_query_param("anything", "scope", {}) is True

    def test_exact_match(self) -> None:
        """Test plain param=value exact matching."""
        assert matches_query_param("global", "scope", {"scope": "global"}) is True
        assert matches_query_param("project", "scope", {"scope": "global"}) is False

    def test_contains_operator(self) -> None:
        """Test [contains] operator."""
        assert matches_query_param("my-policy", "name", {"name[contains]": "poli"}) is True
        assert matches_query_param("my-role", "name", {"name[contains]": "poli"}) is False

    def test_startswith_operator(self) -> None:
        """Test [startswith] operator."""
        assert matches_query_param("admin-role", "name", {"name[startswith]": "admin"}) is True
        assert matches_query_param("user-role", "name", {"name[startswith]": "admin"}) is False
