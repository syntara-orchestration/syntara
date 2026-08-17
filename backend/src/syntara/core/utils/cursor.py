"""Unified cursor data structure for pagination and sorting.

This module provides a centralized CursorData class that combines pagination
and sorting state into a single structure, along with utilities for encoding
and decoding cursor tokens.
"""

import base64
import json
from datetime import datetime
from enum import Enum
from typing import Any, TypedDict
from uuid import UUID

from syntara.core.constants import FieldLimits, ValidationMessages
from syntara.core.exceptions import SafeValueError


def _raise_cursor_too_large() -> None:
    """Raise SafeValueError for cursor size validation."""
    msg = ValidationMessages.CURSOR_TOO_LARGE.format(max_size=FieldLimits.MAX_CURSOR_SIZE)
    raise SafeValueError(msg)


class PaginationDirection(str, Enum):
    """Enumeration for pagination direction."""

    NEXT = "next"
    PREV = "prev"


class SortDirection(str, Enum):
    """Sort direction enumeration."""

    ASC = "asc"
    DESC = "desc"


class CursorData(TypedDict, total=False):
    """Unified cursor data structure for pagination and sorting.

    This structure contains all the information needed to maintain
    pagination and sorting state across API requests.

    Attributes:
        id: Resource ID for pagination positioning
        created_at: Creation timestamp for pagination positioning
        direction: Pagination direction ("next" or "prev")
        sort_field: Field name used for sorting
        sort_direction: Sort direction ("asc" or "desc")

    Note:
        All fields are optional (total=False) to support various cursor scenarios.
        The minimal cursor only needs fields relevant to the specific use case.

    """

    # Pagination fields
    id: str
    created_at: str
    direction: str

    # Sorting fields
    sort_field: str
    sort_direction: str
    sort_value: str


def serialize_sort_value(value: Any) -> str:  # noqa: ANN401
    """Serialize a sort column value to a string for cursor storage.

    Args:
        value: The sort column value (datetime, UUID, bool, int, str, None, etc.)

    Returns:
        String representation suitable for cursor encoding.
        Empty string for None values.

    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def column_python_type(column: Any) -> type | None:  # noqa: ANN401
    """Return ``column.type.python_type``, or ``None`` when unavailable.

    Same approach as ``syntara.core.utils.filters._convert_filter_value``:
    some SQLAlchemy types raise ``NotImplementedError`` / lack ``python_type``.
    """
    try:
        return column.type.python_type  # type: ignore[no-any-return]
    except (AttributeError, NotImplementedError):
        return None


def _deserialize_bool_sort_value(value: str) -> bool:
    """Parse a cursor boolean ``sort_value``.

    Raises:
        ValueError: If ``value`` is not ``true``/``false`` (case-insensitive).
            Callers wrap this as ``SafeValueError``; do not raise
            ``SafeValueError`` here (it subclasses ``ValueError`` and would
            double-wrap).

    """
    normalized = value.lower()
    if normalized not in ("true", "false"):
        msg = f"invalid boolean: {value}"
        raise ValueError(msg)
    return normalized == "true"


def deserialize_sort_value(value: str, python_type: type | None) -> Any:  # noqa: ANN401
    """Deserialize a cursor ``sort_value`` string back to a typed Python value.

    Inverse of :func:`serialize_sort_value`. Callers typically pass
    :func:`column_python_type` (same approach as filter value coercion in
    ``syntara.core.utils.filters``).

    Args:
        value: Serialized sort value from the cursor.
        python_type: Target Python type inferred from the SQLAlchemy column, if known.

    Returns:
        Value suitable for keyset comparison against the sort column.
        Empty strings for datetime/UUID/int targets become ``None``.

    Raises:
        SafeValueError: If ``value`` cannot be coerced to ``python_type``
            (malformed user-controlled cursor token → API 422).

    """
    if value == "" and python_type in {datetime, UUID, int}:
        return None
    try:
        if python_type is datetime:
            # Match filters._convert_datetime_value ISO/'Z' handling
            iso_value = value.replace("Z", "+00:00") if value.endswith("Z") else value
            return datetime.fromisoformat(iso_value)
        if python_type is UUID:
            return UUID(value)
        if python_type is bool:
            return _deserialize_bool_sort_value(value)
        if python_type is int:
            return int(value)
    except (ValueError, TypeError) as e:
        msg = ValidationMessages.CURSOR_INVALID_FORMAT.format(error=e)
        raise SafeValueError(msg) from e
    return value


def deserialize_column_sort_value(value: str, column: Any) -> Any:  # noqa: ANN401
    """Deserialize a cursor sort_value using the column's Python type."""
    return deserialize_sort_value(value, column_python_type(column))


def create_cursor_data(
    *,
    resource_id: str | UUID | None = None,
    created_at: datetime | str | None = None,
    direction: PaginationDirection = PaginationDirection.NEXT,
    sort_field: str | None = None,
    sort_direction: SortDirection = SortDirection.DESC,
    sort_value: str | None = None,
) -> CursorData:
    """Create a cursor data structure with the provided parameters.

    Args:
        resource_id: Resource ID for pagination positioning
        created_at: Creation timestamp for pagination positioning
        direction: Pagination direction
        sort_field: Field name used for sorting
        sort_direction: Sort direction
        sort_value: Serialized value of the sort field at the boundary item

    Returns:
        CursorData dictionary with the provided fields

    """
    cursor: CursorData = {}

    if resource_id is not None:
        cursor["id"] = str(resource_id)

    if created_at is not None:
        if isinstance(created_at, datetime):
            cursor["created_at"] = created_at.isoformat()
        else:
            cursor["created_at"] = created_at

    cursor["direction"] = direction.value

    if sort_field is not None:
        cursor["sort_field"] = sort_field

    if sort_field is not None:
        cursor["sort_direction"] = sort_direction.value

    if sort_value is not None:
        cursor["sort_value"] = sort_value

    return cursor


def _filter_to_cursor_data(raw_data: Any) -> CursorData:  # noqa: ANN401
    """Filter raw JSON data to only valid CursorData fields.

    Args:
        raw_data: Raw data from JSON parsing

    Returns:
        CursorData dictionary with only valid fields

    """
    # Type safety: Filter to only valid CursorData fields
    # This ensures the return type matches CursorData TypedDict
    if not isinstance(raw_data, dict):
        return {}  # Return empty CursorData for non-dict JSON

    cursor_data: CursorData = {}

    # Only include fields that are part of CursorData structure and are strings
    if "id" in raw_data and isinstance(raw_data["id"], str):
        cursor_data["id"] = raw_data["id"]
    if "created_at" in raw_data and isinstance(raw_data["created_at"], str):
        cursor_data["created_at"] = raw_data["created_at"]
    if "direction" in raw_data and isinstance(raw_data["direction"], str):
        cursor_data["direction"] = raw_data["direction"]
    if "sort_field" in raw_data and isinstance(raw_data["sort_field"], str):
        cursor_data["sort_field"] = raw_data["sort_field"]
    if "sort_direction" in raw_data and isinstance(raw_data["sort_direction"], str):
        cursor_data["sort_direction"] = raw_data["sort_direction"]
    if "sort_value" in raw_data and isinstance(raw_data["sort_value"], str):
        cursor_data["sort_value"] = raw_data["sort_value"]

    return cursor_data


def encode_cursor(cursor_data: CursorData) -> str:
    """Encode cursor data to a base64 string.

    Args:
        cursor_data: CursorData dictionary to encode

    Returns:
        Base64-encoded cursor string

    Examples:
        >>> cursor = {"id": "uuid", "direction": "next"}
        >>> encode_cursor(cursor)
        "eyJkaXJlY3Rpb24iOiJuZXh0IiwiaWQiOiJ1dWlkIn0="

    """
    # Sort keys for consistent encoding
    cursor_json = json.dumps(cursor_data, sort_keys=True)
    cursor_bytes = cursor_json.encode("utf-8")
    return base64.b64encode(cursor_bytes).decode("ascii")


def decode_cursor(cursor: str) -> CursorData:
    """Decode cursor token to CursorData dictionary.

    Args:
        cursor: Base64-encoded cursor string

    Returns:
        CursorData dictionary containing cursor information

    Raises:
        ValueError: If cursor is malformed
        json.JSONDecodeError: If cursor contains invalid JSON

    Examples:
        >>> cursor = "eyJpZCI6InV1aWQifQ=="
        >>> decode_cursor(cursor)
        {"id": "uuid"}

    """
    try:
        # Security: Validate cursor size to prevent memory exhaustion attacks
        if len(cursor) > FieldLimits.MAX_CURSOR_SIZE:
            _raise_cursor_too_large()

        cursor_bytes = base64.b64decode(cursor.encode("ascii"))
        cursor_json = cursor_bytes.decode("utf-8")

        # Security: Validate JSON size after decoding
        if len(cursor_json) > FieldLimits.MAX_CURSOR_SIZE:
            _raise_cursor_too_large()

        # Security: Use secure JSON loading with limited depth
        try:
            raw_data = json.loads(cursor_json)
            return _filter_to_cursor_data(raw_data)
        except RecursionError:
            msg = "Cursor JSON too deeply nested"
            raise SafeValueError(msg) from None

    except json.JSONDecodeError:
        # Re-raise JSONDecodeError as-is for explicit handling
        raise
    except (ValueError, UnicodeDecodeError) as e:
        if "Cursor" in str(e):
            # Re-raise our security-related errors as-is
            raise
        msg = ValidationMessages.CURSOR_INVALID_FORMAT.format(error=e)
        raise SafeValueError(msg) from e


def get_pagination_direction(cursor: str | None) -> PaginationDirection:
    """Extract pagination direction from cursor.

    Args:
        cursor: Cursor string containing direction information

    Returns:
        Pagination direction (NEXT, PREV, or NEXT for None cursor)

    Examples:
        >>> cursor_data = {"direction": "next"}
        >>> cursor = encode_cursor(cursor_data)
        >>> get_pagination_direction(cursor)
        PaginationDirection.NEXT

    """
    if cursor is None:
        return PaginationDirection.NEXT  # First page is always forward navigation

    try:
        cursor_data = decode_cursor(cursor)
        direction_str = cursor_data.get("direction", "next")
        if direction_str == "next":
            return PaginationDirection.NEXT
        if direction_str == "prev":
            return PaginationDirection.PREV
        return PaginationDirection.NEXT  # Default to forward navigation for invalid direction
    except (ValueError, json.JSONDecodeError):
        return PaginationDirection.NEXT  # Default to forward navigation on invalid cursor


def extract_sort_from_cursor(cursor_data: CursorData) -> tuple[str, SortDirection]:
    """Extract sort information from cursor data.

    Args:
        cursor_data: CursorData containing cursor information

    Returns:
        Tuple of (field_name, sort_direction) from cursor

    Examples:
        >>> cursor: CursorData = {"sort_field": "name", "sort_direction": "asc"}
        >>> extract_sort_from_cursor(cursor)
        ("name", SortDirection.ASC)

    """
    field = cursor_data.get("sort_field", "created_at")
    direction_str = cursor_data.get("sort_direction", "desc")

    try:
        direction = SortDirection(direction_str)
    except ValueError:
        direction = SortDirection.DESC

    return field, direction


def extract_pagination_from_cursor(cursor_data: CursorData) -> tuple[str | None, str | None, PaginationDirection]:
    """Extract pagination information from cursor data.

    Args:
        cursor_data: CursorData containing cursor information

    Returns:
        Tuple of (resource_id, created_at, direction) from cursor

    Examples:
        >>> cursor: CursorData = {
        ...     "id": "uuid",
        ...     "created_at": "2025-01-01T12:00:00",
        ...     "direction": "next"
        ... }
        >>> extract_pagination_from_cursor(cursor)
        ("uuid", "2025-01-01T12:00:00", PaginationDirection.NEXT)

    """
    resource_id = cursor_data.get("id")
    created_at = cursor_data.get("created_at")
    direction_str = cursor_data.get("direction", "next")

    try:
        direction = PaginationDirection(direction_str)
    except ValueError:
        direction = PaginationDirection.NEXT

    return resource_id, created_at, direction


def extract_keyset_from_cursor(
    cursor_data: CursorData,
) -> tuple[str | None, str | None, str | None, str | None, PaginationDirection]:
    """Extract full keyset pagination info including sort value.

    Returns:
        Tuple of (sort_field, sort_value, resource_id, created_at, direction).
        sort_field and sort_value are None for old cursors that lack them.

    """
    resource_id = cursor_data.get("id")
    created_at = cursor_data.get("created_at")
    sort_field = cursor_data.get("sort_field")
    sort_value = cursor_data.get("sort_value")
    direction_str = cursor_data.get("direction", "next")

    try:
        direction = PaginationDirection(direction_str)
    except ValueError:
        direction = PaginationDirection.NEXT

    return sort_field, sort_value, resource_id, created_at, direction
