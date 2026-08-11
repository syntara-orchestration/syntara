"""Payload truncation utilities for audit data."""

import copy
import json
from typing import Any

import structlog
from pydantic import BaseModel

logger = structlog.stdlib.get_logger(__name__)

DEFAULT_MAX_PAYLOAD_BYTES = 10_000

_TRUNCATION_SUFFIX = "...<truncated>"


def _serialized_size(value: Any) -> int:  # noqa: ANN401
    """Return the serialized byte size of a value."""
    try:
        return len(json.dumps(value, default=str).encode())
    except (TypeError, ValueError):
        return len(str(value).encode())


def _collect_string_leaves(
    obj: Any,  # noqa: ANN401
    path: tuple[str | int, ...] = (),
) -> list[tuple[tuple[str | int, ...], int]]:
    """Recursively collect all string leaf values with their paths and serialized sizes.

    Returns a list of (path, byte_size) tuples for every string leaf in the structure.
    """
    leaves: list[tuple[tuple[str | int, ...], int]] = []

    if isinstance(obj, str):
        leaves.append((path, _serialized_size(obj)))
    elif isinstance(obj, dict):
        for key, value in obj.items():
            leaves.extend(_collect_string_leaves(value, (*path, key)))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            leaves.extend(_collect_string_leaves(item, (*path, idx)))

    return leaves


def _get_at_path(obj: Any, path: tuple[str | int, ...]) -> str:  # noqa: ANN401
    """Retrieve a value from a nested structure by path."""
    current = obj
    for key in path:
        current = current[key]
    return current  # type: ignore[no-any-return]


def _set_at_path(obj: Any, path: tuple[str | int, ...], value: str) -> None:  # noqa: ANN401
    """Set a value in a nested structure by path."""
    current = obj
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value


def _truncate_largest_leaves(
    structured_data: dict[str, Any],
    leaf_sizes: dict[tuple[str | int, ...], int],
    total: int,
    max_bytes: int,
) -> None:
    """Repeatedly truncate the largest string leaf until total fits within max_bytes.

    Mutates structured_data and leaf_sizes in place.
    """
    while total > max_bytes:
        if not leaf_sizes:
            break

        # Find the largest string leaf
        largest_path = max(leaf_sizes, key=leaf_sizes.get)  # type: ignore[arg-type]
        raw = _get_at_path(structured_data, largest_path)

        # Can't shrink further if already at or below suffix length
        if len(raw) <= len(_TRUNCATION_SUFFIX):
            del leaf_sizes[largest_path]
            continue

        overage = total - max_bytes
        raw_bytes = len(raw.encode())
        cut_to = max(0, raw_bytes - overage - len(_TRUNCATION_SUFFIX.encode()))
        # cut_to is in bytes; convert back to a character-safe cut point
        truncated = raw.encode()[:cut_to].decode(errors="ignore") + _TRUNCATION_SUFFIX

        logger.warning(
            "Structured data exceeds max payload size, truncating leaf value",
            path=".".join(str(p) for p in largest_path),
            total_size_bytes=total,
            max_bytes=max_bytes,
        )

        _set_at_path(structured_data, largest_path, truncated)

        # Update cached size
        old_size = leaf_sizes[largest_path]
        new_size = _serialized_size(truncated)
        leaf_sizes[largest_path] = new_size

        # No-progress guard — skip this leaf and try others
        if new_size >= old_size:
            del leaf_sizes[largest_path]
            continue

        total -= old_size - new_size


def enforce_payload_limit[T: BaseModel](data: T, max_bytes: int) -> T:
    """Truncate oversized structured_data by shortening the largest string leaf values.

    Preserves the structure of dicts and lists — only individual string values
    within the structure are shortened. Non-string values (ints, bools, None, etc.)
    are never modified.

    Args:
        data: The BaseModel instance to enforce payload limits on
        max_bytes: Maximum total serialized size in bytes

    Returns:
        A new instance of the same type with payload limits enforced

    """
    structured_data = data.model_dump()
    # Snapshot before mutation for diffing later
    original_top_level = copy.deepcopy(structured_data)

    # Fast bail — check total size first
    try:
        total = len(json.dumps(structured_data, default=str).encode())
    except (TypeError, ValueError):
        return data
    if total <= max_bytes:
        return data

    # Collect all string leaves with their paths and sizes
    leaves = _collect_string_leaves(structured_data)
    if not leaves:
        return data

    leaf_sizes: dict[tuple[str | int, ...], int] = dict(leaves)
    _truncate_largest_leaves(structured_data, leaf_sizes, total, max_bytes)

    # Determine which top-level keys changed for model_copy
    updates = {}
    for key in structured_data:
        if structured_data[key] != original_top_level[key]:
            updates[key] = structured_data[key]

    if not updates:
        return data

    return data.model_copy(update=updates)
