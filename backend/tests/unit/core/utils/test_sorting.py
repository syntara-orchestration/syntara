"""Contract tests for sort parameter parsing functionality.

These tests verify the sort parsing functions can parse ±field syntax into
field name and direction tuples. Tests will fail until sort parsing functions are implemented.
"""

import pytest

from syntara.core.exceptions import SafeValueError
from syntara.core.utils.cursor import CursorData, SortDirection, extract_sort_from_cursor
from syntara.core.utils.sorting import apply_sorting, parse_sort


class TestSortParsing:
    """Test sort parameter parsing functionality."""

    def test_sort_functions_import(self) -> None:
        """Test that parse_sort and SortDirection can be imported."""
        # This will fail until sort parsing functions are implemented

        assert parse_sort is not None
        assert SortDirection is not None

    def test_sort_direction_enum_values(self) -> None:
        """Test that SortDirection enum has expected values."""
        assert SortDirection.ASC == "asc"  # type: ignore[comparison-overlap]
        assert SortDirection.DESC == "desc"  # type: ignore[unreachable]

    def test_parse_sort_function_exists(self) -> None:
        """Test that parse_sort function exists."""
        assert callable(parse_sort)

    def test_parse_ascending_sort(self) -> None:
        """Test parsing ascending sort (no prefix)."""
        field, direction = parse_sort(sort_param="name", allowed_fields=["name", "created_at"])

        assert field == "name"
        assert direction == SortDirection.ASC

    def test_parse_descending_sort(self) -> None:
        """Test parsing descending sort (- prefix)."""
        field, direction = parse_sort(sort_param="-created_at", allowed_fields=["name", "created_at"])

        assert field == "created_at"
        assert direction == SortDirection.DESC

    def test_parse_none_sort_uses_defaults(self) -> None:
        """Test parsing None sort parameter uses default values."""
        field, direction = parse_sort(
            sort_param=None,
            allowed_fields=["name", "created_at"],
            default_field="created_at",
            default_direction=SortDirection.DESC,
        )

        assert field == "created_at"
        assert direction == SortDirection.DESC

    def test_parse_empty_sort_uses_defaults(self) -> None:
        """Test parsing empty sort parameter uses default values."""
        field, direction = parse_sort(
            sort_param="",
            allowed_fields=["id", "name", "created_at"],
            default_field="id",
            default_direction=SortDirection.ASC,
        )

        assert field == "id"
        assert direction == SortDirection.ASC

    def test_parse_invalid_field_raises_error(self) -> None:
        """Test that invalid field names raise SafeValueError."""
        with pytest.raises(SafeValueError, match="Invalid field"):
            parse_sort(sort_param="invalid_field", allowed_fields=["name", "created_at"])

    def test_parse_invalid_field_with_prefix_raises_error(self) -> None:
        """Test that invalid field names with prefix raise SafeValueError."""
        with pytest.raises(SafeValueError, match="Invalid field"):
            parse_sort(sort_param="-invalid_field", allowed_fields=["name", "created_at"])

    def test_parse_all_allowed_fields(self) -> None:
        """Test parsing sort for all allowed fields."""
        allowed_fields = ["id", "name", "created_at", "updated_at", "status"]

        for field in allowed_fields:
            # Test ascending
            parsed_field, direction = parse_sort(sort_param=field, allowed_fields=allowed_fields)
            assert parsed_field == field
            assert direction == SortDirection.ASC

            # Test descending
            parsed_field, direction = parse_sort(sort_param=f"-{field}", allowed_fields=allowed_fields)
            assert parsed_field == field
            assert direction == SortDirection.DESC

    def test_parse_field_with_underscores(self) -> None:
        """Test parsing field names with underscores."""
        field, direction = parse_sort(
            sort_param="created_at", allowed_fields=["created_at", "updated_at", "deleted_at"]
        )

        assert field == "created_at"
        assert direction == SortDirection.ASC

        field, direction = parse_sort(
            sort_param="-updated_at", allowed_fields=["created_at", "updated_at", "deleted_at"]
        )

        assert field == "updated_at"
        assert direction == SortDirection.DESC

    def test_parse_return_type_annotation(self) -> None:
        """Test that parse method returns correctly typed tuple."""
        result = parse_sort(sort_param="name", allowed_fields=["name"])

        # Should be a tuple of (str, SortDirection)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], SortDirection)

    def test_default_parameters(self) -> None:
        """Test default parameter values work correctly."""
        # Test with minimal parameters (should use built-in defaults)
        field, direction = parse_sort(sort_param=None, allowed_fields=["created_at"])

        # Should use default values specified in method signature
        assert field == "created_at"  # Assuming this is the default
        assert direction == SortDirection.DESC  # Assuming this is the default

    def test_custom_default_field(self) -> None:
        """Test custom default field parameter."""
        field, _ = parse_sort(sort_param=None, allowed_fields=["id", "name", "priority"], default_field="priority")

        assert field == "priority"

    def test_custom_default_direction(self) -> None:
        """Test custom default direction parameter."""
        _, direction = parse_sort(
            sort_param=None, allowed_fields=["name"], default_field="name", default_direction=SortDirection.ASC
        )

        assert direction == SortDirection.ASC

    def test_case_sensitivity(self) -> None:
        """Test that field names are case-sensitive."""
        allowed_fields = ["name", "Name", "NAME"]

        # Each case should be treated as different field
        field, _ = parse_sort("name", allowed_fields)
        assert field == "name"

        field, _ = parse_sort("Name", allowed_fields)
        assert field == "Name"

        field, _ = parse_sort("NAME", allowed_fields)
        assert field == "NAME"

        # Wrong case should fail
        with pytest.raises(SafeValueError):
            parse_sort("nAmE", allowed_fields)

    def test_multiple_dash_prefix_handling(self) -> None:
        """Test handling of multiple dash prefixes."""
        # Double dash should still be treated as descending
        field, direction = parse_sort(sort_param="--name", allowed_fields=["name", "-name"])

        # Should strip one dash and treat as descending
        assert field == "-name"  # Field name is "-name"
        assert direction == SortDirection.DESC

    def test_field_name_edge_cases(self) -> None:
        """Test edge cases for field names."""
        # Field names with special characters
        allowed_fields = ["field-with-dashes", "field.with.dots", "field_with_underscores"]

        for field_name in allowed_fields:
            # Ascending
            field, direction = parse_sort(field_name, allowed_fields)
            assert field == field_name
            assert direction == SortDirection.ASC

            # Descending
            field, direction = parse_sort(f"-{field_name}", allowed_fields)
            assert field == field_name
            assert direction == SortDirection.DESC

    def test_whitespace_handling(self) -> None:
        """Test handling of whitespace in sort parameters."""
        # Whitespace should be preserved in field names
        allowed_fields = ["name", " name ", "field with spaces"]

        for field_name in allowed_fields:
            field, direction = parse_sort(field_name, allowed_fields)
            assert field == field_name
            assert direction == SortDirection.ASC

    def test_numeric_field_names(self) -> None:
        """Test field names that start with or contain numbers."""
        allowed_fields = ["field1", "2nd_field", "version_1_2_3"]

        for field_name in allowed_fields:
            field, direction = parse_sort(field_name, allowed_fields)
            assert field == field_name
            assert direction == SortDirection.ASC

            field, direction = parse_sort(f"-{field_name}", allowed_fields)
            assert field == field_name
            assert direction == SortDirection.DESC

    def test_apply_sorting_function_exists(self) -> None:
        """Test that apply_sorting function exists."""
        assert callable(apply_sorting)

    def test_extract_sort_from_cursor_function_exists(self) -> None:
        """Test that extract_sort_from_cursor function exists."""
        assert callable(extract_sort_from_cursor)

    def test_extract_sort_from_cursor_with_both_fields(self) -> None:
        """Test extracting sort from cursor data with both fields present."""
        cursor_data: CursorData = {"sort_field": "name", "sort_direction": "asc"}

        field, direction = extract_sort_from_cursor(cursor_data)

        assert field == "name"
        assert direction == SortDirection.ASC

    def test_extract_sort_from_cursor_with_desc_direction(self) -> None:
        """Test extracting sort from cursor data with descending direction."""
        cursor_data: CursorData = {"sort_field": "created_at", "sort_direction": "desc"}

        field, direction = extract_sort_from_cursor(cursor_data)

        assert field == "created_at"
        assert direction == SortDirection.DESC

    def test_extract_sort_from_cursor_missing_sort_field(self) -> None:
        """Test extracting sort from cursor data missing sort_field (uses default)."""
        cursor_data: CursorData = {"sort_direction": "asc"}

        field, direction = extract_sort_from_cursor(cursor_data)

        assert field == "created_at"  # Default value
        assert direction == SortDirection.ASC

    def test_extract_sort_from_cursor_missing_sort_direction(self) -> None:
        """Test extracting sort from cursor data missing sort_direction (uses default)."""
        cursor_data: CursorData = {"sort_field": "name"}

        field, direction = extract_sort_from_cursor(cursor_data)

        assert field == "name"
        assert direction == SortDirection.DESC  # Default value

    def test_extract_sort_from_cursor_empty_dict(self) -> None:
        """Test extracting sort from empty cursor data (uses all defaults)."""
        cursor_data: CursorData = {}

        field, direction = extract_sort_from_cursor(cursor_data)

        assert field == "created_at"  # Default value
        assert direction == SortDirection.DESC  # Default value

    def test_extract_sort_from_cursor_invalid_direction(self) -> None:
        """Test extracting sort from cursor data with invalid direction (uses default)."""
        cursor_data: CursorData = {"sort_field": "name", "sort_direction": "invalid"}

        field, direction = extract_sort_from_cursor(cursor_data)

        assert field == "name"
        assert direction == SortDirection.DESC  # Default fallback for invalid direction

    def test_cursor_data_type_structure(self) -> None:
        """Test that CursorData type can be used correctly."""
        # This test ensures the CursorData TypedDict works as expected
        cursor_data: CursorData = {"sort_field": "test_field", "sort_direction": "asc"}

        # Should be able to access fields
        assert cursor_data["sort_field"] == "test_field"
        assert cursor_data["sort_direction"] == "asc"

        # Should be able to use with get() method
        assert cursor_data.get("sort_field") == "test_field"
        assert cursor_data.get("sort_direction") == "asc"
        assert cursor_data.get("nonexistent_field", "default") == "default"
