"""Datetime utility functions for workflows.

Provides utilities for datetime conversion, timezone handling, and protobuf timestamp processing.
"""

from datetime import UTC, datetime
from typing import cast

import structlog
from google.protobuf.timestamp_pb2 import Timestamp

logger = structlog.stdlib.get_logger(__name__)


def ensure_timezone_aware(dt: datetime | Timestamp | object) -> datetime:
    """Ensure datetime has timezone information, defaulting to UTC if naive.

    Handles both Python datetime objects and protobuf Timestamp objects from Temporal.

    Args:
        dt: Datetime object, protobuf Timestamp, or any object with ToDatetime() method

    Returns:
        Timezone-aware datetime (original if already aware, UTC if naive)

    Example:
        >>> naive_dt = datetime(2024, 1, 1, 12, 0, 0)
        >>> aware_dt = ensure_timezone_aware(naive_dt)
        >>> aware_dt.tzinfo
        datetime.timezone.utc

    """
    # Handle protobuf Timestamp (from Temporal history events)
    if isinstance(dt, Timestamp):
        # Convert protobuf Timestamp to Python datetime (always UTC)
        return datetime.fromtimestamp(dt.seconds + dt.nanos / 1e9, tz=UTC)

    # Handle objects with ToDatetime() method (some Temporal SDK types)
    if hasattr(dt, "ToDatetime"):
        dt = dt.ToDatetime()

    # Handle Python datetime objects
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt

    # Fallback: check if object has datetime-like attributes
    if hasattr(dt, "tzinfo") and hasattr(dt, "replace"):
        dt_like = cast("datetime", dt)
        if dt_like.tzinfo is None:
            return dt_like.replace(tzinfo=UTC)
        return dt_like

    # If all else fails, log error and return current UTC time
    logger.exception("Cannot convert to timezone-aware datetime", object=dt, object_type=type(dt))
    return datetime.now(UTC)
