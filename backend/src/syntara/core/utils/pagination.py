"""Pagination utilities for cursor-based pagination.

This module provides functions for generating cursor-based pagination
responses with next/prev cursors and optional total counts.

Cursor Format:
    Base64-encoded JSON containing pagination state:
    {"id": "uuid", "created_at": "iso8601", "direction": "next", ...}
"""

from collections.abc import Callable, Sequence
from typing import TypedDict

from syntara.core.models.base import BaseResource
from syntara.core.utils.cursor import (
    PaginationDirection,
    SortDirection,
    create_cursor_data,
    decode_cursor,
    encode_cursor,
    serialize_sort_value,
)


class PaginationResult(TypedDict):
    """Typed return value of a Paginated response."""

    trimmed_items: list[BaseResource]
    next: str | None
    prev: str | None
    total: int | None


def _make_cursor(
    item: BaseResource,
    direction: PaginationDirection,
    sort_field: str | None,
    sort_direction: SortDirection | None,
    sort_value_fn: Callable[[BaseResource], object] | None,
) -> str:
    """Build and encode a cursor token for a boundary item."""
    sv: str | None = None
    if sort_value_fn is not None and sort_field is not None and sort_field != "created_at":
        sv = serialize_sort_value(sort_value_fn(item))

    return encode_cursor(
        create_cursor_data(
            resource_id=item.id,
            created_at=item.created_at,
            direction=direction,
            sort_field=sort_field,
            sort_direction=sort_direction or SortDirection.DESC,
            sort_value=sv,
        )
    )


def generate_response(
    items: Sequence[BaseResource],
    limit: int,
    cursor: str | None,
    *,
    include_total: bool = False,
    total_count: int | None = None,
    is_first_page: bool = False,
    sort_field: str | None = None,
    sort_direction: SortDirection | None = None,
    sort_value_fn: Callable[[BaseResource], object] | None = None,
) -> PaginationResult:
    """Generate paginated response with next/prev cursor tokens using N+1 pattern.

    This implementation uses the industry-standard "Fetch N+1" pattern where the caller
    fetches limit+1 items to definitively detect if more pages exist in the fetch direction.

    Key behaviors:
    - Trims items to requested limit if more than limit items provided
    - Forward pagination: Generates next cursor when items were trimmed (definitive "has more")
    - Backward pagination: Generates next cursor when navigated via cursor (allows returning forward)
    - Generates prev cursor based on cursor presence and is_first_page flag
    - Uses N+1 pattern to detect more items in fetch direction

    Note: The N+1 pattern works asymmetrically for forward vs backward pagination:
    - Forward: has_more indicates more items ahead (next direction)
    - Backward: has_more indicates more items behind (prev direction)
    For backward pagination, the caller must provide is_first_page flag (typically via a
    separate query) since N+1 alone cannot detect first page during backward navigation.

    The N+1 pattern is used by Stripe, GitHub, Shopify, and GraphQL Relay specification.

    Args:
        items: List of items for current page (may contain limit+1 items)
        limit: Items per page limit (caller should fetch limit+1)
        cursor: Current cursor token (None for first page)
        include_total: Whether to include total count in response
        total_count: Total count if include_total is True
        is_first_page: Explicit flag indicating this is the first page (for backward navigation)
        sort_field: Name of the sort column (stored in generated cursors)
        sort_direction: Direction of the sort (stored in generated cursors)
        sort_value_fn: Callable that extracts the raw sort value from a boundary item

    Returns:
        Dictionary with trimmed_items, next, prev, and optional total fields

    """
    response: PaginationResult = {"trimmed_items": [], "next": None, "prev": None, "total": None}

    # Detect if this was backward pagination by checking cursor direction
    is_backward_pagination = False
    if cursor is not None:
        try:
            cursor_data = decode_cursor(cursor)
            direction_str = cursor_data.get("direction", "next")
            is_backward_pagination = direction_str == PaginationDirection.PREV.value
        except (ValueError, KeyError):
            pass

    # N+1 Pattern: Trim items if we got more than requested
    has_more = len(items) > limit

    # For backward pagination, the extra item is at the START after reversal.
    trimmed_items = (
        (list(items[1 : limit + 1]) if is_backward_pagination else list(items[:limit])) if has_more else list(items)
    )

    response["trimmed_items"] = trimmed_items

    # Generate next cursor
    if is_backward_pagination:
        if cursor is not None and len(trimmed_items) > 0:
            response["next"] = _make_cursor(
                trimmed_items[-1], PaginationDirection.NEXT, sort_field, sort_direction, sort_value_fn
            )
        else:
            response["next"] = None
    elif has_more and len(trimmed_items) > 0:
        response["next"] = _make_cursor(
            trimmed_items[-1], PaginationDirection.NEXT, sort_field, sort_direction, sort_value_fn
        )
    else:
        response["next"] = None

    # Generate prev cursor for bidirectional navigation
    if cursor is None or is_first_page:
        response["prev"] = None
    elif len(trimmed_items) > 0:
        response["prev"] = _make_cursor(
            trimmed_items[0], PaginationDirection.PREV, sort_field, sort_direction, sort_value_fn
        )
    else:
        response["prev"] = None

    # Include total count if requested
    if include_total and total_count is not None:
        response["total"] = total_count
    else:
        response["total"] = None

    return response
