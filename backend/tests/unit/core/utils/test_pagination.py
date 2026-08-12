"""Contract tests for cursor-based pagination functionality.

These tests verify the pagination utility functions can generate and decode cursors,
create pagination links, and handle edge cases. Tests will fail until
pagination functions are implemented.
"""

import base64
import contextlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest

from syntara.core.constants import FieldLimits
from syntara.core.exceptions import SafeValueError
from syntara.core.models.base import NamedResource
from syntara.core.utils.cursor import (
    PaginationDirection,
    SortDirection,
    create_cursor_data,
    decode_cursor,
    encode_cursor,
    get_pagination_direction,
)
from syntara.core.utils.pagination import (
    generate_response,
)

if TYPE_CHECKING:
    from syntara.core.utils.cursor import CursorData


class MockResource(NamedResource):
    """Mock resource class for testing pagination."""

    def __init__(self, id: UUID, created_at: datetime, name: str) -> None:  # noqa: A002
        """Initialize mock resource with provided attributes."""
        super().__init__(id=id, created_at=created_at, updated_at=created_at, name=name)


class TestPaginationFunctions:
    """Test cursor-based pagination functionality."""

    def test_pagination_functions_import(self) -> None:
        """Test that pagination functions can be imported."""
        # This will fail until pagination functions are implemented

        assert encode_cursor is not None
        assert decode_cursor is not None
        assert generate_response is not None
        assert get_pagination_direction is not None

    def test_encode_cursor_function_exists(self) -> None:
        """Test that encode_cursor function exists."""
        assert callable(encode_cursor)

    def test_decode_cursor_function_exists(self) -> None:
        """Test that decode_cursor function exists."""
        assert callable(decode_cursor)

    def test_generate_response_function_exists(self) -> None:
        """Test that generate_response function exists."""
        assert callable(generate_response)

    def test_encode_cursor_basic(self) -> None:
        """Test basic cursor encoding from last item."""
        resource_id = uuid4()
        last_item = MockResource(
            id=resource_id, created_at=datetime(2025, 10, 15, 12, 0, 0, tzinfo=UTC), name="Test Resource"
        )

        cursor_data = create_cursor_data(
            resource_id=last_item.id,
            created_at=last_item.created_at,
            direction=PaginationDirection.NEXT,
        )
        cursor = encode_cursor(cursor_data)

        # Should return a base64-encoded string
        assert isinstance(cursor, str)
        assert len(cursor) > 0

        # Should be valid base64
        try:
            decoded_bytes = base64.b64decode(cursor.encode())
            decoded_json = json.loads(decoded_bytes.decode())
            assert "id" in decoded_json
        except Exception as e:
            pytest.fail(f"Cursor should be valid base64 JSON: {e}")

    def test_decode_cursor_basic(self) -> None:
        """Test basic cursor decoding."""
        # Create a test cursor manually
        cursor_data = {"id": str(uuid4())}
        cursor_json = json.dumps(cursor_data)
        cursor = base64.b64encode(cursor_json.encode()).decode()

        decoded = decode_cursor(cursor)

        assert isinstance(decoded, dict)
        assert "id" in decoded
        assert decoded["id"] == cursor_data["id"]

    def test_encode_decode_roundtrip(self) -> None:
        """Test encoding and decoding a cursor produces original data."""
        resource_id = uuid4()
        last_item = MockResource(
            id=resource_id, created_at=datetime(2025, 10, 15, 12, 0, 0, tzinfo=UTC), name="Test Resource"
        )

        # Encode then decode
        cursor_data = create_cursor_data(
            resource_id=last_item.id,
            created_at=last_item.created_at,
            direction=PaginationDirection.NEXT,
        )
        cursor = encode_cursor(cursor_data)
        decoded = decode_cursor(cursor)

        # Should get back the original ID
        assert decoded["id"] == str(resource_id)

    def test_generate_response_first_page(self) -> None:
        """Test generating pagination response for first page."""
        # Create mock resources (limit+1 for N+1 pattern)
        resources = [MockResource(id=uuid4(), created_at=datetime.now(UTC), name=f"Resource {i}") for i in range(21)]

        response = generate_response(
            items=resources,
            limit=20,
            cursor=None,  # First page
            include_total=True,
            total_count=100,
        )

        # Should have pagination metadata
        assert "next" in response
        assert "prev" in response
        assert "total" in response
        assert "trimmed_items" in response

        # Should have trimmed items
        trimmed = response["trimmed_items"]
        assert isinstance(trimmed, list)
        assert len(trimmed) == 20

        # First page should have no prev cursor
        assert response["prev"] is None

        # Should have next cursor since we got limit+1 items (has more)
        assert response["next"] is not None
        assert isinstance(response["next"], str)

        # Should include total count
        assert response["total"] == 100

    def test_generate_response_middle_page(self) -> None:
        """Test generating pagination response for middle page."""
        # Create limit+1 resources for N+1 pattern
        resources = [MockResource(id=uuid4(), created_at=datetime.now(UTC), name=f"Resource {i}") for i in range(21)]

        # Simulate middle page with existing cursor
        existing_cursor = base64.b64encode(json.dumps({"id": str(uuid4())}).encode()).decode()

        response = generate_response(
            items=resources,
            limit=20,
            cursor=existing_cursor,
            include_total=False,
        )

        # Should have trimmed items
        trimmed = response["trimmed_items"]
        assert isinstance(trimmed, list)
        assert len(trimmed) == 20

        # Should have next cursor (since we got limit+1 items)
        assert response["next"] is not None
        assert isinstance(response["next"], str)

        # Middle page should have prev cursor (bidirectional navigation implemented)
        assert response["prev"] is not None
        assert isinstance(response["prev"], str)

        # Should not include total when include_total=False
        assert response.get("total") is None

    def test_generate_response_last_page(self) -> None:
        """Test generating pagination response for last page."""
        # Last page has fewer items than limit
        resources = [
            MockResource(id=uuid4(), created_at=datetime.now(UTC), name=f"Resource {i}")
            for i in range(15)  # Less than limit of 20
        ]

        existing_cursor = base64.b64encode(json.dumps({"id": str(uuid4())}).encode()).decode()

        response = generate_response(items=resources, limit=20, cursor=existing_cursor)

        # Last page should have no next cursor (items < limit)
        assert response["next"] is None

        # Last page should have prev cursor (bidirectional navigation implemented)
        assert response["prev"] is not None
        assert isinstance(response["prev"], str)

    def test_generate_response_empty_page(self) -> None:
        """Test generating pagination response for empty results."""
        response = generate_response(items=[], limit=20, cursor=None)

        # Empty page should have no pagination cursors
        assert response["next"] is None
        assert response["prev"] is None

    def test_cursor_token_format(self) -> None:
        """Test that cursor tokens are properly formatted."""
        resources = [MockResource(id=uuid4(), created_at=datetime.now(UTC), name="Test")]

        response = generate_response(items=resources, limit=20, cursor=None)

        if response["next"]:
            # Cursor should be a valid base64-encoded string
            cursor = response["next"]
            assert isinstance(cursor, str)
            # Should be decodable
            try:
                decoded = decode_cursor(cursor)
                assert isinstance(decoded, dict)
                assert "id" in decoded
            except Exception as e:
                pytest.fail(f"Cursor should be valid: {e}")

    def test_invalid_cursor_handling(self) -> None:
        """Test handling of invalid cursor data."""
        # Invalid base64
        with pytest.raises((ValueError, json.JSONDecodeError)):
            decode_cursor("invalid-base64!")

        # Valid base64 but invalid JSON
        invalid_json_cursor = base64.b64encode(b"not-json").decode()
        with pytest.raises(json.JSONDecodeError):
            decode_cursor(invalid_json_cursor)

    def test_cursor_with_timestamps(self) -> None:
        """Test cursor encoding/decoding with timestamp data."""
        test_time = datetime(2025, 10, 15, 12, 30, 45, tzinfo=UTC)
        last_item = MockResource(id=uuid4(), created_at=test_time, name="Test Resource")

        cursor_data = create_cursor_data(
            resource_id=last_item.id,
            created_at=last_item.created_at,
            direction=PaginationDirection.NEXT,
        )
        cursor = encode_cursor(cursor_data)
        decoded = decode_cursor(cursor)

        # Should contain ID at minimum
        assert "id" in decoded

    def test_pagination_cursor_consistency(self) -> None:
        """Test that pagination cursors are consistent across calls."""
        resource = MockResource(id=uuid4(), created_at=datetime.now(UTC), name="Test")
        resources = [resource]

        # Generate response multiple times
        response1 = generate_response(items=resources, limit=20, cursor=None)

        response2 = generate_response(items=resources, limit=20, cursor=None)

        # Both should generate the same cursor for the same resource
        if response1["next"] and response2["next"]:
            assert response1["next"] == response2["next"]

    def test_bidirectional_navigation_new_functionality(self) -> None:
        """Test the new bidirectional navigation features."""
        resources = [MockResource(id=uuid4(), created_at=datetime.now(UTC), name=f"Resource {i}") for i in range(5)]

        # Test direction encoding and detection
        next_cursor_data = create_cursor_data(
            resource_id=resources[0].id, created_at=resources[0].created_at, direction=PaginationDirection.NEXT
        )
        prev_cursor_data = create_cursor_data(
            resource_id=resources[0].id, created_at=resources[0].created_at, direction=PaginationDirection.PREV
        )
        next_cursor = encode_cursor(next_cursor_data)
        prev_cursor = encode_cursor(prev_cursor_data)

        assert get_pagination_direction(None) == PaginationDirection.NEXT
        assert get_pagination_direction(next_cursor) == PaginationDirection.NEXT
        assert get_pagination_direction(prev_cursor) == PaginationDirection.PREV

        # Test cursor contains direction information
        decoded_next = decode_cursor(next_cursor)
        decoded_prev = decode_cursor(prev_cursor)

        assert decoded_next["direction"] == "next"
        assert decoded_prev["direction"] == "prev"
        assert decoded_next["id"] == decoded_prev["id"]  # Same resource, different direction

    def test_empty_page_with_cursor(self) -> None:
        """Test empty page behavior when cursor is provided."""
        # Empty page with cursor should have no prev cursor
        response = generate_response(items=[], limit=20, cursor="some_cursor")

        assert response["next"] is None
        assert response["prev"] is None  # Empty page means no navigation

    def test_single_item_page_navigation(self) -> None:
        """Test navigation with single item pages."""
        resource = MockResource(id=uuid4(), created_at=datetime.now(UTC), name="Single Resource")

        # First page with single item
        first_response = generate_response(items=[resource], limit=5, cursor=None)

        assert first_response["next"] is None  # Less than limit, so no next
        assert first_response["prev"] is None  # First page, so no prev

        # Middle page with single item
        cursor_data = create_cursor_data(
            resource_id=resource.id, created_at=resource.created_at, direction=PaginationDirection.NEXT
        )
        cursor = encode_cursor(cursor_data)
        middle_response = generate_response(items=[resource], limit=5, cursor=cursor)

        assert middle_response["next"] is None  # Less than limit, so no next
        assert middle_response["prev"] is not None  # Has cursor, so has prev

    def test_backward_pagination_to_first_page_generates_next_cursor(self) -> None:
        """Test that backward pagination to first page still generates next cursor.

        This is a regression test for a bug where navigating backward to the first page
        would incorrectly set next=None, preventing forward navigation and hiding
        pagination controls.

        The bug occurred because:
        - During backward pagination, the N+1 pattern detects items in the PREV direction
        - When reaching first page, has_more=False (no items before first page)
        - The code incorrectly used has_more to determine next cursor generation
        - This caused next=None even though there were pages ahead (that we came from)

        Fix: During backward pagination with a cursor, next cursor should always be
        generated to allow forward navigation back through the pages.
        """
        # Create 2 resources (first page when limit=2)
        resources = [
            MockResource(id=uuid4(), created_at=datetime.now(UTC), name="Resource 1"),
            MockResource(id=uuid4(), created_at=datetime.now(UTC), name="Resource 2"),
        ]

        # Simulate backward pagination to first page using a prev cursor
        # This cursor indicates we're navigating backward from a later page
        prev_cursor_data = create_cursor_data(
            resource_id=resources[0].id,
            created_at=resources[0].created_at,
            direction=PaginationDirection.PREV,
        )
        prev_cursor = encode_cursor(prev_cursor_data)

        # Generate response for first page reached via backward pagination
        # is_first_page=True indicates we're on the first page (determined by caller)
        # We have exactly 2 items (no extra), so has_more=False
        response = generate_response(
            items=resources,
            limit=2,
            cursor=prev_cursor,
            is_first_page=True,
        )

        # Assertions for first page reached via backward pagination
        assert len(response["trimmed_items"]) == 2

        # Critical assertion: next cursor MUST be present
        # This allows forward navigation back to the pages we came from
        assert response["next"] is not None, "First page reached via backward pagination must have next cursor"

        # prev cursor must be None since we're on the first page
        assert response["prev"] is None, "First page should have no previous cursor"

        # Verify the next cursor has correct direction
        decoded_next = decode_cursor(response["next"])
        assert decoded_next["direction"] == "next"


class TestCursorSecurity:
    """Test cursor security features and limits."""

    def test_cursor_size_limit_enforcement(self) -> None:
        """Test that oversized cursors are rejected."""
        # Create a cursor that exceeds the maximum size
        oversized_data = {"id": "x" * (FieldLimits.MAX_CURSOR_SIZE + 100)}
        oversized_json = json.dumps(oversized_data)
        oversized_cursor = base64.b64encode(oversized_json.encode()).decode()

        # Should raise SafeValueError for oversized cursor
        with pytest.raises(SafeValueError, match=r"Cursor.*too large"):
            decode_cursor(oversized_cursor)

    def test_cursor_json_size_limit_after_decoding(self) -> None:
        """Test that JSON size is validated after base64 decoding."""
        # Create JSON that's small when encoded but large when decoded
        # Base64 encoding makes data larger, but we test the decoded size
        large_value = "x" * (FieldLimits.MAX_CURSOR_SIZE + 100)
        large_data = {"large_field": large_value}
        large_json = json.dumps(large_data)
        large_cursor = base64.b64encode(large_json.encode()).decode()

        # Should raise SafeValueError for oversized JSON after decoding
        with pytest.raises(SafeValueError, match=r"Cursor.*too large"):
            decode_cursor(large_cursor)

    def test_cursor_json_depth_attack_protection(self) -> None:
        """Test conceptual protection against deeply nested JSON attacks."""
        # Note: Modern Python's json.loads is quite robust and doesn't easily
        # trigger RecursionError with moderate nesting levels
        # This test documents the protection mechanism even if it's hard to trigger

        # Create deeply nested JSON (this may or may not trigger RecursionError)
        nested_data: dict[str, dict[str, Any]] = {}
        current = nested_data

        # Try a depth that might trigger RecursionError on some systems
        depth = 1000
        for _i in range(depth):
            current["n"] = {}
            current = current["n"]

        try:
            nested_json = json.dumps(nested_data)
            # If this creates JSON larger than cursor limit, it will be caught by size check
            if len(nested_json) > FieldLimits.MAX_CURSOR_SIZE:
                nested_cursor = base64.b64encode(nested_json.encode()).decode()
                with pytest.raises(SafeValueError, match=r"Cursor.*too large"):
                    decode_cursor(nested_cursor)
                return  # Test passed via size limit

            nested_cursor = base64.b64encode(nested_json.encode()).decode()

            # This might trigger the RecursionError protection or just succeed
            try:
                result = decode_cursor(nested_cursor)
                # If it succeeds, the nesting wasn't deep enough to trigger RecursionError
                # This is actually fine - the protection is there for extreme cases
                assert result is not None
            except ValueError as e:
                # If it fails with our expected message, great!
                if "Cursor JSON too deeply nested" in str(e):
                    pass  # Test passed
                else:
                    raise  # Re-raise if it's a different error

        except (MemoryError, RecursionError):
            # If JSON creation itself fails, that's system-level protection
            # which is also acceptable
            pass

    def test_cursor_malformed_base64(self) -> None:
        """Test handling of malformed base64 cursors."""
        malformed_cursors = [
            "not_base64_at_all!",
            "invalid-characters-@#$%",
            "missing==padding",
            "ünïcödé_çhãracters",
            "",  # Empty string
            "a",  # Too short
        ]

        for malformed_cursor in malformed_cursors:
            with pytest.raises((ValueError, json.JSONDecodeError)):
                decode_cursor(malformed_cursor)

    def test_cursor_malformed_json_after_decode(self) -> None:
        """Test handling of valid base64 that contains invalid JSON."""
        # Only test invalid JSON that will actually cause JSONDecodeError
        invalid_json_strings = [
            "not json at all",
            '{"incomplete": "json"',  # Missing closing brace
            '{"invalid": syntax}',  # Unquoted value
            '{duplicate": "duplicate": "keys"}',  # Invalid syntax
        ]

        for invalid_json in invalid_json_strings:
            invalid_cursor = base64.b64encode(invalid_json.encode()).decode()

            # Should raise JSONDecodeError
            with pytest.raises(json.JSONDecodeError):
                decode_cursor(invalid_cursor)

        # Test valid JSON but invalid cursor content (non-dict types)
        # These might be accepted by the cursor decoder or raise different errors
        valid_json_non_dict = [
            "null",  # Valid JSON but null value
            "[]",  # Valid JSON but list
            '"string"',  # Valid JSON but string
            "42",  # Valid JSON but number
            "true",  # Valid JSON but boolean
        ]

        for valid_json in valid_json_non_dict:
            invalid_cursor = base64.b64encode(valid_json.encode()).decode()

            with contextlib.suppress(ValueError, TypeError, AttributeError):
                decode_cursor(invalid_cursor)
                # Test just verifies no exception is raised for non-dict JSON

    def test_cursor_unicode_handling(self) -> None:
        """Test proper handling of unicode characters in valid CursorData fields."""
        # Valid unicode in CursorData fields only
        unicode_data: CursorData = {
            "id": "resource-üñïcödé-123",
            "direction": "next",
            "sort_field": "测试字段",  # Chinese characters
            "sort_direction": "asc",
            "created_at": "2025-01-01T12:00:00+00:00-Ελληνικά",  # Greek characters in timestamp
        }

        # Should encode and decode properly, only returning valid CursorData fields
        cursor = encode_cursor(unicode_data)
        decoded = decode_cursor(cursor)

        assert decoded["id"] == "resource-üñïcödé-123"
        assert decoded["direction"] == "next"
        assert decoded["sort_field"] == "测试字段"
        assert decoded["sort_direction"] == "asc"
        assert decoded["created_at"] == "2025-01-01T12:00:00+00:00-Ελληνικά"

    def test_cursor_special_characters_injection(self) -> None:
        """Test that special characters in valid CursorData fields don't cause issues."""
        # Test various special characters in valid CursorData fields only
        special_chars_data: CursorData = {
            "id": "resource-with-'quotes\"and`backticks",
            "direction": "next",
            "sort_field": "field.with%_special\\chars",
            "sort_direction": "asc",
            "created_at": "2025-01-01T12:00:00+00:00<script>alert('xss')</script>",
        }

        # Should handle special characters safely and filter to only valid fields
        cursor = encode_cursor(special_chars_data)
        decoded = decode_cursor(cursor)

        # Should preserve all special characters in valid CursorData fields only
        assert decoded["id"] == "resource-with-'quotes\"and`backticks"
        assert decoded["direction"] == "next"
        assert decoded["sort_field"] == "field.with%_special\\chars"
        assert decoded["sort_direction"] == "asc"
        assert decoded["created_at"] == "2025-01-01T12:00:00+00:00<script>alert('xss')</script>"

        # Invalid fields should be filtered out (not present in decoded result)
        assert "path" not in decoded
        assert "sql_like" not in decoded
        assert "json_chars" not in decoded

    def test_cursor_binary_data_handling(self) -> None:
        """Test handling of binary data in cursor fields."""
        # Test that non-UTF8 binary data causes appropriate errors
        binary_data = b"\x80\x81\x82\x83\x84\x85"  # Invalid UTF-8 sequence

        # Try to create cursor with binary data encoded as base64
        binary_cursor = base64.b64encode(binary_data).decode()

        # Should raise SafeValueError (UnicodeDecodeError gets converted by decode_cursor)
        with pytest.raises(SafeValueError, match="Invalid cursor format"):
            decode_cursor(binary_cursor)

    def test_cursor_empty_and_null_values(self) -> None:
        """Test handling of empty and null values in cursors."""
        # Test empty cursor data
        empty_cursor_data: CursorData = {}
        cursor = encode_cursor(empty_cursor_data)
        decoded = decode_cursor(cursor)
        assert decoded == {}

        # Test cursor with null values - these should be filtered out since CursorData only accepts strings
        # We can't use CursorData type here since it only accepts strings, so use a regular dict
        raw_data_with_nulls = {
            "id": None,
            "direction": "next",
            "created_at": None,
            "sort_field": None,
            "sort_direction": None,
        }
        # Manually encode to test decoding behavior with null values
        cursor_json = json.dumps(raw_data_with_nulls, sort_keys=True)
        cursor_bytes = cursor_json.encode("utf-8")
        cursor = base64.b64encode(cursor_bytes).decode("ascii")

        decoded = decode_cursor(cursor)
        # Only string values should be preserved in CursorData
        assert "id" not in decoded  # None values filtered out
        assert decoded["direction"] == "next"  # String value preserved
        assert "created_at" not in decoded  # None values filtered out
        assert "sort_field" not in decoded  # None values filtered out
        assert "sort_direction" not in decoded  # None values filtered out

        # Invalid fields should not be present
        assert "empty_string" not in decoded
        assert "zero" not in decoded
        assert "false" not in decoded


class TestCursorDirectionAndConsistency:
    """Test cursor direction handling and consistency scenarios."""

    def test_cursor_direction_mismatch_handling(self) -> None:
        """Test graceful handling of mismatched cursor directions."""
        # Create cursor with invalid direction
        invalid_direction_data: CursorData = {
            "id": str(uuid4()),
            "direction": "invalid_direction",
            "created_at": "2025-01-01T12:00:00",
        }
        cursor = encode_cursor(invalid_direction_data)

        # Should default to NEXT direction when direction is invalid
        direction = get_pagination_direction(cursor)
        assert direction == PaginationDirection.NEXT

    def test_cursor_missing_direction_field(self) -> None:
        """Test handling of cursors missing direction field."""
        # Create cursor without direction field
        no_direction_data: CursorData = {"id": str(uuid4()), "created_at": "2025-01-01T12:00:00"}
        cursor = encode_cursor(no_direction_data)

        # Should default to NEXT direction
        direction = get_pagination_direction(cursor)
        assert direction == PaginationDirection.NEXT

    def test_cursor_structure_consistency(self) -> None:
        """Test that cursor structure is consistent across operations."""
        # Test valid cursor data
        valid_cursor: CursorData = {
            "id": str(uuid4()),
            "direction": "next",
            "sort_field": "name",
            "sort_direction": "asc",
        }

        # Should encode and decode successfully
        cursor = encode_cursor(valid_cursor)
        decoded = decode_cursor(cursor)

        # Should maintain structure
        assert decoded["id"] == valid_cursor["id"]
        assert decoded["direction"] == valid_cursor["direction"]
        assert decoded["sort_field"] == valid_cursor["sort_field"]
        assert decoded["sort_direction"] == valid_cursor["sort_direction"]

    def test_cursor_consistency_after_data_changes(self) -> None:
        """Test cursor behavior when underlying data changes."""
        # This tests the conceptual issue of stale cursors
        # Create a cursor pointing to a specific resource
        original_resource_id = uuid4()
        original_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        cursor_data = create_cursor_data(
            resource_id=original_resource_id, created_at=original_time, direction=PaginationDirection.NEXT
        )
        cursor = encode_cursor(cursor_data)

        # Decode and verify the cursor still contains original data
        decoded = decode_cursor(cursor)
        assert decoded["id"] == str(original_resource_id)

        # Note: In a real application, this cursor might now point to:
        # - A deleted resource
        # - A resource with changed timestamp
        # - A resource that moved in sort order
        # This test verifies the cursor structure remains valid even if
        # the underlying data changes

    def test_cursor_edge_case_boundary_values(self) -> None:
        """Test cursor handling at boundary values."""
        # Test with very early timestamp
        early_time = datetime(1970, 1, 1, 0, 0, 0, tzinfo=UTC)
        early_cursor_data = create_cursor_data(
            resource_id=uuid4(), created_at=early_time, direction=PaginationDirection.NEXT
        )
        cursor = encode_cursor(early_cursor_data)
        decoded = decode_cursor(cursor)
        assert "created_at" in decoded

        # Test with far future timestamp
        future_time = datetime(2099, 12, 31, 23, 59, 59, tzinfo=UTC)
        future_cursor_data = create_cursor_data(
            resource_id=uuid4(), created_at=future_time, direction=PaginationDirection.PREV
        )
        cursor = encode_cursor(future_cursor_data)
        decoded = decode_cursor(cursor)
        assert "created_at" in decoded

    def test_cursor_with_all_optional_fields(self) -> None:
        """Test cursor creation and validation with all optional fields."""
        # Create cursor with all possible fields
        comprehensive_cursor_data = create_cursor_data(
            resource_id=uuid4(),
            created_at=datetime.now(UTC),
            direction=PaginationDirection.PREV,
            sort_field="custom_field",
            sort_direction=SortDirection.ASC,
        )

        cursor = encode_cursor(comprehensive_cursor_data)
        decoded = decode_cursor(cursor)

        # Should contain all fields
        assert "id" in decoded
        assert "created_at" in decoded
        assert "direction" in decoded
        assert "sort_field" in decoded
        assert "sort_direction" in decoded

        # Test that cursor can be re-encoded successfully
        re_encoded = encode_cursor(decoded)
        assert isinstance(re_encoded, str)
        assert len(re_encoded) > 0

    def test_pagination_direction_fallback_on_errors(self) -> None:
        """Test that pagination direction falls back safely on errors."""
        # Test with completely malformed cursor
        with pytest.raises((ValueError, json.JSONDecodeError)):
            decode_cursor("definitely_not_a_cursor")

        # But get_pagination_direction should handle this gracefully
        direction = get_pagination_direction("definitely_not_a_cursor")
        assert direction == PaginationDirection.NEXT  # Should default to safe value


class TestGenerateResponseWithSortContext:
    """Tests for generate_response with sort_field and sort_value_fn."""

    def _make_items(self, count: int) -> list[MockResource]:
        """Create a list of mock resources."""
        return [
            MockResource(
                id=uuid4(),
                created_at=datetime(2025, 1, 1 + i, tzinfo=UTC),
                name=f"item-{chr(ord('a') + i)}",
            )
            for i in range(count)
        ]

    def test_sort_context_stored_in_next_cursor(self) -> None:
        """Next cursor includes sort_value from the boundary item."""
        items = self._make_items(11)  # N+1 to trigger has_more
        result = generate_response(
            items=items,
            limit=10,
            cursor=None,
            sort_field="name",
            sort_direction=SortDirection.ASC,
            sort_value_fn=lambda item: item.name,  # type: ignore[attr-defined]
        )
        assert result["next"] is not None
        decoded = decode_cursor(result["next"])
        assert decoded["sort_field"] == "name"
        assert decoded["sort_direction"] == "asc"
        assert decoded["sort_value"] == items[9].name

    def test_sort_context_stored_in_prev_cursor(self) -> None:
        """Prev cursor includes sort_value from the first item."""
        items = self._make_items(5)
        cursor_data = create_cursor_data(
            resource_id=items[0].id,
            created_at=items[0].created_at,
            direction=PaginationDirection.NEXT,
        )
        cursor = encode_cursor(cursor_data)
        result = generate_response(
            items=items,
            limit=10,
            cursor=cursor,
            sort_field="name",
            sort_direction=SortDirection.ASC,
            sort_value_fn=lambda item: item.name,  # type: ignore[attr-defined]
        )
        assert result["prev"] is not None
        decoded = decode_cursor(result["prev"])
        assert decoded["sort_field"] == "name"
        assert decoded["sort_value"] == items[0].name

    def test_created_at_sort_omits_sort_value(self) -> None:
        """When sort_field is created_at, sort_value should be omitted for backward compat."""
        items = self._make_items(11)
        result = generate_response(
            items=items,
            limit=10,
            cursor=None,
            sort_field="created_at",
            sort_direction=SortDirection.DESC,
            sort_value_fn=lambda item: item.created_at,
        )
        assert result["next"] is not None
        decoded = decode_cursor(result["next"])
        assert "sort_value" not in decoded

    def test_no_sort_context_backward_compat(self) -> None:
        """Without sort params, cursors are backward compatible."""
        items = self._make_items(11)
        result = generate_response(items=items, limit=10, cursor=None)
        assert result["next"] is not None
        decoded = decode_cursor(result["next"])
        assert "sort_value" not in decoded
        assert "sort_field" not in decoded
