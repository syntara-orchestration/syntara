"""Validation helpers for free-form JSONB fields."""

from __future__ import annotations

import json
from typing import Any

from syntara.core.constants import FieldLimits, JsonbLimits, ValidationMessages
from syntara.core.exceptions import SafeValueError


def serialized_json_size(value: Any) -> int:  # noqa: ANN401
    """Return UTF-8 byte length of JSON-serialized value."""
    try:
        return len(json.dumps(value, default=str, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError):
        return len(str(value).encode("utf-8"))


def validate_jsonb_size[T](
    value: T,
    *,
    field_name: str,
    max_bytes: int = JsonbLimits.MAX_FIELD_BYTES,
) -> T:
    """Reject values whose JSON serialization exceeds max_bytes."""
    if value is None:
        return value

    size = serialized_json_size(value)
    if size > max_bytes:
        msg = f"{field_name} exceeds maximum serialized size of {max_bytes} bytes ({size} bytes after JSON encoding)"
        raise SafeValueError(msg)
    return value


def validate_labels_dict(labels: dict[str, str] | None) -> dict[str, str] | None:
    """Validate labels dict structure, per-entry lengths, count, and total serialized size."""
    if labels is None:
        return labels

    if not isinstance(labels, dict):
        raise SafeValueError(ValidationMessages.LABELS_MUST_BE_DICT)

    if len(labels) > FieldLimits.MAX_LABELS_COUNT:
        msg = f"labels contains {len(labels)} entries, maximum is {FieldLimits.MAX_LABELS_COUNT}"
        raise SafeValueError(msg)

    for key, value in labels.items():
        if not isinstance(key, str):
            msg = ValidationMessages.LABELS_KEY_MUST_BE_STRING.format(key=key, type_name=type(key).__name__)  # type: ignore[unreachable]
            raise SafeValueError(msg)
        if len(key) > FieldLimits.MAX_LABEL_KEY_LENGTH:
            msg = f"labels key exceeds maximum length of {FieldLimits.MAX_LABEL_KEY_LENGTH} characters"
            raise SafeValueError(msg)
        if not isinstance(value, str):
            msg = ValidationMessages.LABELS_VALUE_MUST_BE_STRING.format(key=key, type_name=type(value).__name__)  # type: ignore[unreachable]
            raise SafeValueError(msg)
        if len(value) > FieldLimits.MAX_LABEL_VALUE_LENGTH:
            msg = (
                f"labels value for key '{key}' exceeds maximum length of "
                f"{FieldLimits.MAX_LABEL_VALUE_LENGTH} characters"
            )
            raise SafeValueError(msg)

    size = serialized_json_size(labels)
    if size > FieldLimits.MAX_LABELS_BYTES:
        msg = (
            f"labels exceeds maximum serialized size of {FieldLimits.MAX_LABELS_BYTES} bytes "
            f"({size} bytes after JSON encoding)"
        )
        raise SafeValueError(msg)

    return labels


def validate_workflow_definition_json[T](value: T) -> T:
    """Reject oversized raw workflow_definition dict payloads."""
    if value is None or not isinstance(value, dict):
        return value
    return validate_jsonb_size(
        value,
        field_name="workflow_definition",
        max_bytes=JsonbLimits.MAX_WORKFLOW_DEFINITION_BYTES,
    )
