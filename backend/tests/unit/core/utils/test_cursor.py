"""Tests for cursor utilities.

This module provides comprehensive tests for cursor-based pagination
and sorting functionality, including encoding/decoding, validation,
and data manipulation functions.
"""

import base64
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from syntara.core.exceptions import SafeValueError
from syntara.core.utils.cursor import (
    CursorData,
    PaginationDirection,
    SortDirection,
    column_python_type,
    create_cursor_data,
    decode_cursor,
    deserialize_column_sort_value,
    deserialize_sort_value,
    encode_cursor,
    extract_keyset_from_cursor,
    extract_pagination_from_cursor,
    extract_sort_from_cursor,
    get_pagination_direction,
    serialize_sort_value,
)


class TestPaginationDirection:
    """Tests for PaginationDirection enum."""

    def test_pagination_direction_string_behavior(self) -> None:
        """Test that PaginationDirection behaves like a string."""
        # Enum str() returns the full representation, but value works like string
        assert PaginationDirection.NEXT.value == "next"
        assert PaginationDirection.PREV.value == "prev"


class TestSortDirection:
    """Tests for SortDirection enum."""

    def test_sort_direction_string_behavior(self) -> None:
        """Test that SortDirection behaves like a string."""
        # Enum str() returns the full representation, but value works like string
        assert SortDirection.ASC.value == "asc"
        assert SortDirection.DESC.value == "desc"


class TestCreateCursorData:
    """Tests for create_cursor_data function."""

    def test_create_empty_cursor_data(self) -> None:
        """Test creating cursor data with no parameters."""
        cursor = create_cursor_data()
        assert cursor["direction"] == "next"  # Default direction
        assert len(cursor) == 1  # Only direction field

    def test_create_cursor_data_with_resource_id(self) -> None:
        """Test creating cursor data with resource ID."""
        resource_id = uuid4()
        cursor = create_cursor_data(resource_id=resource_id)

        assert cursor["id"] == str(resource_id)
        assert cursor["direction"] == "next"
        assert "sort_direction" not in cursor  # No sort field means no sort direction

    def test_create_cursor_data_with_string_resource_id(self) -> None:
        """Test creating cursor data with string resource ID."""
        resource_id = "550e8400-e29b-41d4-a716-446655440000"
        cursor = create_cursor_data(resource_id=resource_id)

        assert cursor["id"] == resource_id
        assert cursor["direction"] == "next"

    def test_create_cursor_data_with_datetime(self) -> None:
        """Test creating cursor data with datetime."""
        now = datetime.now(UTC)
        cursor = create_cursor_data(created_at=now)

        assert cursor["created_at"] == now.isoformat()
        assert cursor["direction"] == "next"

    def test_create_cursor_data_with_string_datetime(self) -> None:
        """Test creating cursor data with string datetime."""
        dt_string = "2025-01-01T12:00:00.000000"
        cursor = create_cursor_data(created_at=dt_string)

        assert cursor["created_at"] == dt_string
        assert cursor["direction"] == "next"

    def test_create_cursor_data_with_sort_field(self) -> None:
        """Test creating cursor data with sort field."""
        cursor = create_cursor_data(sort_field="name")

        assert cursor["sort_field"] == "name"
        assert cursor["sort_direction"] == "desc"  # Default sort direction
        assert cursor["direction"] == "next"

    def test_create_cursor_data_with_custom_sort_direction(self) -> None:
        """Test creating cursor data with custom sort direction."""
        cursor = create_cursor_data(sort_field="created_at", sort_direction=SortDirection.ASC)

        assert cursor["sort_field"] == "created_at"
        assert cursor["sort_direction"] == "asc"
        assert cursor["direction"] == "next"

    def test_create_cursor_data_with_prev_direction(self) -> None:
        """Test creating cursor data with prev direction."""
        cursor = create_cursor_data(direction=PaginationDirection.PREV)

        assert cursor["direction"] == "prev"

    def test_create_cursor_data_complete(self) -> None:
        """Test creating cursor data with all parameters."""
        resource_id = uuid4()
        now = datetime.now(UTC)

        cursor = create_cursor_data(
            resource_id=resource_id,
            created_at=now,
            direction=PaginationDirection.PREV,
            sort_field="name",
            sort_direction=SortDirection.ASC,
        )

        assert cursor["id"] == str(resource_id)
        assert cursor["created_at"] == now.isoformat()
        assert cursor["direction"] == "prev"
        assert cursor["sort_field"] == "name"
        assert cursor["sort_direction"] == "asc"

    def test_create_cursor_data_sort_direction_without_field(self) -> None:
        """Test that sort_direction is not included without sort_field."""
        cursor = create_cursor_data(sort_direction=SortDirection.ASC)

        assert "sort_field" not in cursor
        assert "sort_direction" not in cursor  # Should not be included
        assert cursor["direction"] == "next"


class TestEncodeCursor:
    """Tests for encode_cursor function."""

    def test_encode_empty_cursor(self) -> None:
        """Test encoding empty cursor data."""
        cursor_data: CursorData = {}
        encoded = encode_cursor(cursor_data)

        # Should be valid base64
        decoded_bytes = base64.b64decode(encoded.encode("ascii"))
        decoded_json = json.loads(decoded_bytes.decode("utf-8"))
        assert decoded_json == {}

    def test_encode_cursor_with_data(self) -> None:
        """Test encoding cursor with data."""
        cursor_data: CursorData = {"id": "550e8400-e29b-41d4-a716-446655440000", "direction": "next"}
        encoded = encode_cursor(cursor_data)

        # Verify it can be decoded back
        decoded_bytes = base64.b64decode(encoded.encode("ascii"))
        decoded_json = json.loads(decoded_bytes.decode("utf-8"))
        assert decoded_json == cursor_data

    def test_encode_cursor_sorts_keys(self) -> None:
        """Test that encode_cursor sorts keys for consistency."""
        cursor_data: CursorData = {"direction": "next", "id": "uuid", "created_at": "2025-01-01T12:00:00"}
        encoded = encode_cursor(cursor_data)

        # Decode and verify keys are in sorted order
        decoded_bytes = base64.b64decode(encoded.encode("ascii"))
        json_str = decoded_bytes.decode("utf-8")

        # JSON with sorted keys should have consistent ordering
        expected_json = json.dumps(cursor_data, sort_keys=True)
        assert json_str == expected_json

    def test_encode_cursor_deterministic(self) -> None:
        """Test that encoding the same data produces the same result."""
        cursor_data: CursorData = {"id": "test", "direction": "next"}

        encoded1 = encode_cursor(cursor_data)
        encoded2 = encode_cursor(cursor_data)

        assert encoded1 == encoded2


class TestDecodeCursor:
    """Tests for decode_cursor function."""

    def test_decode_valid_cursor(self) -> None:
        """Test decoding a valid cursor."""
        cursor_data: CursorData = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "direction": "next",
            "created_at": "2025-01-01T12:00:00",
        }

        # Encode then decode
        encoded = encode_cursor(cursor_data)
        decoded = decode_cursor(encoded)

        assert decoded == cursor_data

    def test_decode_empty_cursor(self) -> None:
        """Test decoding an empty cursor."""
        cursor_data: CursorData = {}

        encoded = encode_cursor(cursor_data)
        decoded = decode_cursor(encoded)

        assert decoded == {}

    def test_decode_cursor_filters_invalid_fields(self) -> None:
        """Test that decode_cursor filters out invalid fields."""
        # Create cursor with extra fields manually
        raw_data = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "direction": "next",
            "invalid_field": "should_be_filtered",
            "another_invalid": 123,
        }

        # Manually encode
        cursor_json = json.dumps(raw_data, sort_keys=True)
        cursor_bytes = cursor_json.encode("utf-8")
        encoded = base64.b64encode(cursor_bytes).decode("ascii")

        # Decode should filter out invalid fields
        decoded = decode_cursor(encoded)

        assert decoded["id"] == "550e8400-e29b-41d4-a716-446655440000"
        assert decoded["direction"] == "next"
        assert "invalid_field" not in decoded
        assert "another_invalid" not in decoded

    def test_decode_cursor_filters_non_string_values(self) -> None:
        """Test that decode_cursor filters out non-string values."""
        # Create cursor with non-string values
        raw_data = {
            "id": 123,  # Should be string
            "direction": "next",
            "created_at": None,  # Should be string
            "sort_field": "name",
        }

        # Manually encode
        cursor_json = json.dumps(raw_data, sort_keys=True)
        cursor_bytes = cursor_json.encode("utf-8")
        encoded = base64.b64encode(cursor_bytes).decode("ascii")

        # Decode should filter out non-string values
        decoded = decode_cursor(encoded)

        assert "id" not in decoded  # Filtered out because it's not a string
        assert decoded["direction"] == "next"  # String value preserved
        assert "created_at" not in decoded  # Filtered out because it's None
        assert decoded["sort_field"] == "name"  # String value preserved

    def test_decode_invalid_base64(self) -> None:
        """Test decoding invalid base64 raises SafeValueError."""
        invalid_cursor = "not-valid-base64!"

        with pytest.raises(SafeValueError, match="Invalid cursor format"):
            decode_cursor(invalid_cursor)

    def test_decode_invalid_json(self) -> None:
        """Test decoding invalid JSON raises JSONDecodeError."""
        # Valid base64 but invalid JSON
        invalid_json = "not valid json"
        cursor_bytes = invalid_json.encode("utf-8")
        encoded = base64.b64encode(cursor_bytes).decode("ascii")

        with pytest.raises(json.JSONDecodeError):
            decode_cursor(encoded)

    def test_decode_cursor_too_large(self) -> None:
        """Test that overly large cursor raises SafeValueError."""
        # Create a cursor that exceeds the size limit
        large_data = {"id": "x" * 10000}  # Very large cursor
        cursor_json = json.dumps(large_data)
        cursor_bytes = cursor_json.encode("utf-8")
        encoded = base64.b64encode(cursor_bytes).decode("ascii")

        with pytest.raises(SafeValueError, match=r"Cursor.*too large"):
            decode_cursor(encoded)

    def test_decode_deeply_nested_json(self) -> None:
        """Test that deeply nested JSON triggers size limit validation."""
        # Create deeply nested structure that would exceed size limits
        nested: dict[str, Any] = {}
        current = nested
        for i in range(1000):  # Very deep nesting
            current[f"level_{i}"] = {}
            current = current[f"level_{i}"]

        cursor_json = json.dumps(nested)
        cursor_bytes = cursor_json.encode("utf-8")
        encoded = base64.b64encode(cursor_bytes).decode("ascii")

        # Size limit validation triggers before deep nesting validation
        with pytest.raises(SafeValueError, match="Cursor too large"):
            decode_cursor(encoded)

    def test_decode_non_dict_json(self) -> None:
        """Test decoding JSON that's not a dictionary."""
        # Valid JSON but not a dict
        json_list = json.dumps(["not", "a", "dict"])
        cursor_bytes = json_list.encode("utf-8")
        encoded = base64.b64encode(cursor_bytes).decode("ascii")

        # Should return empty CursorData for non-dict JSON
        decoded = decode_cursor(encoded)
        assert decoded == {}

    def test_decode_malformed_cursor_raises_exception(self) -> None:
        """Test that malformed cursor strings raise appropriate exceptions."""
        # Test cursor with invalid characters that can't be base64 decoded
        malformed_cursor = "invalid_base64!!!!"

        with pytest.raises(SafeValueError, match="Invalid cursor format"):
            decode_cursor(malformed_cursor)


class TestGetPaginationDirection:
    """Tests for get_pagination_direction function."""

    def test_get_pagination_direction_none_cursor(self) -> None:
        """Test getting pagination direction from None cursor."""
        direction = get_pagination_direction(None)
        assert direction == PaginationDirection.NEXT

    def test_get_pagination_direction_next(self) -> None:
        """Test getting NEXT pagination direction."""
        cursor_data: CursorData = {"direction": "next"}
        cursor = encode_cursor(cursor_data)

        direction = get_pagination_direction(cursor)
        assert direction == PaginationDirection.NEXT

    def test_get_pagination_direction_prev(self) -> None:
        """Test getting PREV pagination direction."""
        cursor_data: CursorData = {"direction": "prev"}
        cursor = encode_cursor(cursor_data)

        direction = get_pagination_direction(cursor)
        assert direction == PaginationDirection.PREV

    def test_get_pagination_direction_missing_field(self) -> None:
        """Test getting pagination direction when field is missing."""
        cursor_data: CursorData = {"id": "test"}  # No direction field
        cursor = encode_cursor(cursor_data)

        direction = get_pagination_direction(cursor)
        assert direction == PaginationDirection.NEXT  # Default

    def test_get_pagination_direction_invalid_value(self) -> None:
        """Test getting pagination direction with invalid value."""
        # Create cursor with invalid direction manually
        raw_data = {"direction": "invalid"}
        cursor_json = json.dumps(raw_data)
        cursor_bytes = cursor_json.encode("utf-8")
        cursor = base64.b64encode(cursor_bytes).decode("ascii")

        direction = get_pagination_direction(cursor)
        assert direction == PaginationDirection.NEXT  # Default for invalid

    def test_get_pagination_direction_invalid_cursor(self) -> None:
        """Test getting pagination direction from invalid cursor."""
        invalid_cursor = "invalid-cursor"

        direction = get_pagination_direction(invalid_cursor)
        assert direction == PaginationDirection.NEXT  # Default on error


class TestExtractSortFromCursor:
    """Tests for extract_sort_from_cursor function."""

    def test_extract_sort_with_sort_data(self) -> None:
        """Test extracting sort information from cursor with sort data."""
        cursor_data: CursorData = {"sort_field": "name", "sort_direction": "asc"}

        field, direction = extract_sort_from_cursor(cursor_data)

        assert field == "name"
        assert direction == SortDirection.ASC

    def test_extract_sort_missing_fields(self) -> None:
        """Test extracting sort information when fields are missing."""
        cursor_data: CursorData = {"id": "test"}

        field, direction = extract_sort_from_cursor(cursor_data)

        assert field == "created_at"  # Default field
        assert direction == SortDirection.DESC  # Default direction

    def test_extract_sort_missing_direction(self) -> None:
        """Test extracting sort when only field is present."""
        cursor_data: CursorData = {"sort_field": "name"}

        field, direction = extract_sort_from_cursor(cursor_data)

        assert field == "name"
        assert direction == SortDirection.DESC  # Default direction

    def test_extract_sort_invalid_direction(self) -> None:
        """Test extracting sort with invalid direction."""
        cursor_data: CursorData = {"sort_field": "name", "sort_direction": "invalid"}

        field, direction = extract_sort_from_cursor(cursor_data)

        assert field == "name"
        assert direction == SortDirection.DESC  # Default for invalid

    def test_extract_sort_desc_direction(self) -> None:
        """Test extracting sort with DESC direction."""
        cursor_data: CursorData = {"sort_field": "created_at", "sort_direction": "desc"}

        field, direction = extract_sort_from_cursor(cursor_data)

        assert field == "created_at"
        assert direction == SortDirection.DESC


class TestExtractPaginationFromCursor:
    """Tests for extract_pagination_from_cursor function."""

    def test_extract_pagination_complete_data(self) -> None:
        """Test extracting pagination from complete cursor data."""
        cursor_data: CursorData = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "created_at": "2025-01-01T12:00:00.000000",
            "direction": "next",
        }

        resource_id, created_at, direction = extract_pagination_from_cursor(cursor_data)

        assert resource_id == "550e8400-e29b-41d4-a716-446655440000"
        assert created_at == "2025-01-01T12:00:00.000000"
        assert direction == PaginationDirection.NEXT

    def test_extract_pagination_missing_fields(self) -> None:
        """Test extracting pagination when fields are missing."""
        cursor_data: CursorData = {}

        resource_id, created_at, direction = extract_pagination_from_cursor(cursor_data)

        assert resource_id is None
        assert created_at is None
        assert direction == PaginationDirection.NEXT  # Default

    def test_extract_pagination_prev_direction(self) -> None:
        """Test extracting pagination with PREV direction."""
        cursor_data: CursorData = {"direction": "prev"}

        resource_id, created_at, direction = extract_pagination_from_cursor(cursor_data)

        assert resource_id is None
        assert created_at is None
        assert direction == PaginationDirection.PREV

    def test_extract_pagination_invalid_direction(self) -> None:
        """Test extracting pagination with invalid direction."""
        cursor_data: CursorData = {"direction": "invalid"}

        resource_id, created_at, direction = extract_pagination_from_cursor(cursor_data)

        assert resource_id is None
        assert created_at is None
        assert direction == PaginationDirection.NEXT  # Default for invalid

    def test_extract_pagination_partial_data(self) -> None:
        """Test extracting pagination with partial data."""
        cursor_data: CursorData = {"id": "test-id", "direction": "prev"}

        resource_id, created_at, direction = extract_pagination_from_cursor(cursor_data)

        assert resource_id == "test-id"
        assert created_at is None
        assert direction == PaginationDirection.PREV


class TestCursorIntegration:
    """Integration tests for cursor functionality."""

    def test_encode_decode_roundtrip(self) -> None:
        """Test that encoding and decoding produces the same result."""
        original_data: CursorData = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "created_at": "2025-01-01T12:00:00.000000",
            "direction": "prev",
            "sort_field": "name",
            "sort_direction": "asc",
        }

        # Encode then decode
        encoded = encode_cursor(original_data)
        decoded = decode_cursor(encoded)

        assert decoded == original_data

    def test_create_encode_decode_roundtrip(self) -> None:
        """Test full workflow: create -> encode -> decode."""
        # Create cursor data
        cursor_data = create_cursor_data(
            resource_id="550e8400-e29b-41d4-a716-446655440000",
            created_at=datetime.fromisoformat("2025-01-01T12:00:00"),
            direction=PaginationDirection.PREV,
            sort_field="name",
            sort_direction=SortDirection.ASC,
        )

        # Encode
        encoded = encode_cursor(cursor_data)

        # Decode
        decoded = decode_cursor(encoded)

        # Verify data integrity
        assert decoded["id"] == "550e8400-e29b-41d4-a716-446655440000"
        assert decoded["created_at"] == "2025-01-01T12:00:00"
        assert decoded["direction"] == "prev"
        assert decoded["sort_field"] == "name"
        assert decoded["sort_direction"] == "asc"

    def test_extract_functions_consistency(self) -> None:
        """Test that extract functions work consistently with cursor data."""
        cursor_data: CursorData = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "created_at": "2025-01-01T12:00:00.000000",
            "direction": "prev",
            "sort_field": "name",
            "sort_direction": "asc",
        }

        # Extract pagination info
        resource_id, created_at, direction = extract_pagination_from_cursor(cursor_data)
        assert resource_id == "550e8400-e29b-41d4-a716-446655440000"
        assert created_at == "2025-01-01T12:00:00.000000"
        assert direction == PaginationDirection.PREV

        # Extract sort info
        sort_field, sort_direction = extract_sort_from_cursor(cursor_data)
        assert sort_field == "name"
        assert sort_direction == SortDirection.ASC

    def test_create_cursor_data_structure(self) -> None:
        """Test that created cursor data has correct structure."""
        cursor_data = create_cursor_data(
            resource_id="test-id",
            direction=PaginationDirection.NEXT,
            sort_field="name",
            sort_direction=SortDirection.DESC,
        )

        assert cursor_data["id"] == "test-id"
        assert cursor_data["direction"] == "next"
        assert cursor_data["sort_field"] == "name"
        assert cursor_data["sort_direction"] == "desc"

    def test_extract_functions_integration(self) -> None:
        """Test that extraction functions work together."""
        cursor_data: CursorData = {"id": "test-id", "direction": "next", "sort_field": "name", "sort_direction": "asc"}

        # Should extract correctly
        resource_id, created_at, direction = extract_pagination_from_cursor(cursor_data)
        assert resource_id == "test-id"
        assert created_at is None
        assert direction == PaginationDirection.NEXT

        sort_field, sort_direction = extract_sort_from_cursor(cursor_data)
        assert sort_field == "name"
        assert sort_direction == SortDirection.ASC


class TestSerializeSortValue:
    """Tests for serialize_sort_value function."""

    def test_serialize_none(self) -> None:
        assert serialize_sort_value(None) == ""

    def test_serialize_string(self) -> None:
        assert serialize_sort_value("hello") == "hello"

    def test_serialize_int(self) -> None:
        assert serialize_sort_value(42) == "42"

    def test_serialize_bool(self) -> None:
        true_val = True
        false_val = False
        assert serialize_sort_value(true_val) == "true"
        assert serialize_sort_value(false_val) == "false"

    def test_serialize_datetime(self) -> None:
        dt = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert serialize_sort_value(dt) == dt.isoformat()

    def test_serialize_uuid(self) -> None:
        uid = uuid4()
        assert serialize_sort_value(uid) == str(uid)


class TestDeserializeSortValue:
    """Tests for deserialize_sort_value (inverse of serialize_sort_value)."""

    def test_deserialize_datetime(self) -> None:
        dt = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert deserialize_sort_value(dt.isoformat(), datetime) == dt

    def test_deserialize_datetime_z_suffix(self) -> None:
        result = deserialize_sort_value("2025-01-15T10:30:00Z", datetime)
        assert result == datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

    def test_deserialize_datetime_empty(self) -> None:
        assert deserialize_sort_value("", datetime) is None

    def test_deserialize_uuid(self) -> None:
        uid = uuid4()
        assert deserialize_sort_value(str(uid), UUID) == uid

    def test_deserialize_uuid_empty(self) -> None:
        assert deserialize_sort_value("", UUID) is None

    def test_deserialize_bool(self) -> None:
        assert deserialize_sort_value("true", bool) is True
        assert deserialize_sort_value("false", bool) is False

    def test_deserialize_bool_case_insensitive(self) -> None:
        assert deserialize_sort_value("TRUE", bool) is True
        assert deserialize_sort_value("False", bool) is False

    def test_invalid_bool_raises_safe_value_error(self) -> None:
        with pytest.raises(SafeValueError, match=r"^Invalid cursor format: invalid boolean: garbage$") as exc_info:
            deserialize_sort_value("garbage", bool)
        # Ensure we do not double-wrap (SafeValueError is a ValueError subclass).
        assert str(exc_info.value).count("Invalid cursor format") == 1

    def test_deserialize_int(self) -> None:
        assert deserialize_sort_value("42", int) == 42

    def test_deserialize_int_empty(self) -> None:
        assert deserialize_sort_value("", int) is None

    def test_deserialize_string_passthrough(self) -> None:
        assert deserialize_sort_value("alice", str) == "alice"
        assert deserialize_sort_value("alice", None) == "alice"

    def test_roundtrip_datetime(self) -> None:
        dt = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        assert deserialize_sort_value(serialize_sort_value(dt), datetime) == dt

    def test_invalid_datetime_raises_safe_value_error(self) -> None:
        with pytest.raises(SafeValueError, match="Invalid cursor format"):
            deserialize_sort_value("not-a-datetime", datetime)

    def test_invalid_uuid_raises_safe_value_error(self) -> None:
        with pytest.raises(SafeValueError, match="Invalid cursor format"):
            deserialize_sort_value("not-a-uuid", UUID)

    def test_invalid_int_raises_safe_value_error(self) -> None:
        with pytest.raises(SafeValueError, match="Invalid cursor format"):
            deserialize_sort_value("not-an-int", int)


class TestColumnPythonType:
    """Tests for column_python_type / deserialize_column_sort_value helpers."""

    def test_returns_python_type_for_datetime_column(self) -> None:
        from syntara.workflows.models.workflow import Workflow

        assert column_python_type(Workflow.updated_at) is datetime

    def test_missing_python_type_returns_none(self) -> None:
        from sqlalchemy import String, TypeDecorator, column

        class _NoPythonType(TypeDecorator[str]):
            impl = String
            cache_ok = True

            @property
            def python_type(self) -> type:
                raise NotImplementedError

        assert column_python_type(column("name", _NoPythonType())) is None

    def test_deserialize_column_sort_value_datetime(self) -> None:
        from syntara.workflows.models.workflow import Workflow

        dt = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert deserialize_column_sort_value(dt.isoformat(), Workflow.updated_at) == dt

    def test_deserialize_column_sort_value_string_fallback(self) -> None:
        from sqlalchemy import String, TypeDecorator, column

        class _NoPythonType(TypeDecorator[str]):
            impl = String
            cache_ok = True

            @property
            def python_type(self) -> type:
                raise NotImplementedError

        assert deserialize_column_sort_value("alice", column("name", _NoPythonType())) == "alice"


class TestCreateCursorDataSortValue:
    """Tests for sort_value parameter in create_cursor_data."""

    def test_sort_value_included(self) -> None:
        cursor = create_cursor_data(sort_field="name", sort_value="alice")
        assert cursor["sort_value"] == "alice"
        assert cursor["sort_field"] == "name"

    def test_sort_value_not_included_when_none(self) -> None:
        cursor = create_cursor_data(sort_field="name")
        assert "sort_value" not in cursor

    def test_sort_value_roundtrip(self) -> None:
        cursor = create_cursor_data(
            resource_id="abc",
            created_at="2025-01-01T00:00:00",
            sort_field="name",
            sort_value="bob",
        )
        encoded = encode_cursor(cursor)
        decoded = decode_cursor(encoded)
        assert decoded["sort_value"] == "bob"

    def test_sort_value_empty_string(self) -> None:
        """Empty string is the sentinel for NULL sort values."""
        cursor = create_cursor_data(sort_field="name", sort_value="")
        assert cursor["sort_value"] == ""
        encoded = encode_cursor(cursor)
        decoded = decode_cursor(encoded)
        assert decoded["sort_value"] == ""


class TestFilterToCursorDataSortValue:
    """Tests that _filter_to_cursor_data accepts sort_value."""

    def test_sort_value_preserved_on_decode(self) -> None:
        raw = {"id": "x", "direction": "next", "sort_value": "alice"}
        encoded = base64.b64encode(json.dumps(raw).encode()).decode()
        decoded = decode_cursor(encoded)
        assert decoded.get("sort_value") == "alice"

    def test_non_string_sort_value_filtered(self) -> None:
        raw = {"sort_value": 123}
        encoded = base64.b64encode(json.dumps(raw).encode()).decode()
        decoded = decode_cursor(encoded)
        assert "sort_value" not in decoded


class TestExtractKeysetFromCursor:
    """Tests for extract_keyset_from_cursor function."""

    def test_full_keyset(self) -> None:
        cursor: CursorData = {
            "id": "uid-1",
            "created_at": "2025-01-01T00:00:00",
            "direction": "next",
            "sort_field": "name",
            "sort_value": "alice",
        }
        sf, sv, rid, cat, direction = extract_keyset_from_cursor(cursor)
        assert sf == "name"
        assert sv == "alice"
        assert rid == "uid-1"
        assert cat == "2025-01-01T00:00:00"
        assert direction == PaginationDirection.NEXT

    def test_old_cursor_without_sort_value(self) -> None:
        cursor: CursorData = {
            "id": "uid-1",
            "created_at": "2025-01-01T00:00:00",
            "direction": "prev",
        }
        sf, sv, rid, _cat, direction = extract_keyset_from_cursor(cursor)
        assert sf is None
        assert sv is None
        assert rid == "uid-1"
        assert direction == PaginationDirection.PREV

    def test_empty_cursor(self) -> None:
        cursor: CursorData = {}
        sf, sv, rid, cat, direction = extract_keyset_from_cursor(cursor)
        assert sf is None
        assert sv is None
        assert rid is None
        assert cat is None
        assert direction == PaginationDirection.NEXT
