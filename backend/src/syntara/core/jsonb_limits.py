"""Validation helpers for free-form JSONB fields."""

from __future__ import annotations

import json
from typing import Annotated, Any, cast

from pydantic import BeforeValidator

from syntara.core.constants import FieldLimits, JsonbLimits, ValidationMessages
from syntara.core.exceptions import SafeValueError

_FORM_NODE_TYPES = frozenset({"form_prompt", "form_trigger"})


def serialized_json_size(value: Any) -> int:  # noqa: ANN401
    """Return UTF-8 byte length of JSON-serialized value."""
    try:
        return len(json.dumps(value, default=str, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
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
    """Reject workflow_definition dicts that exceed size or structural complexity bounds."""
    if value is None or not isinstance(value, dict):
        return value

    authored_value = _without_generated_form_response_schemas(value)
    validate_jsonb_size(
        authored_value,
        field_name="workflow_definition",
        max_bytes=JsonbLimits.MAX_WORKFLOW_DEFINITION_BYTES,
    )

    nodes = authored_value.get("nodes", [])
    node_count = len(nodes) if isinstance(nodes, list) else 0
    if node_count > JsonbLimits.MAX_WORKFLOW_NODES:
        msg = (
            f"workflow_definition has too many nodes: {node_count} exceeds maximum of {JsonbLimits.MAX_WORKFLOW_NODES}"
        )
        raise SafeValueError(msg)

    edges = authored_value.get("edges", [])
    edge_count = len(edges) if isinstance(edges, list) else 0
    if edge_count > JsonbLimits.MAX_WORKFLOW_EDGES:
        msg = (
            f"workflow_definition has too many edges: {edge_count} exceeds maximum of {JsonbLimits.MAX_WORKFLOW_EDGES}"
        )
        raise SafeValueError(msg)

    return cast("T", authored_value)


def _without_generated_form_response_schemas(value: dict[str, Any]) -> dict[str, Any]:
    if not _contains_generated_form_response_schema(value):
        return value

    authored_value = {**value}
    for collection_name in ("triggers", "nodes"):
        items = authored_value.get(collection_name, [])
        if not isinstance(items, list):
            continue

        filtered_items: list[Any] = []
        for item in items:
            if (
                isinstance(item, dict)
                and _is_form_node(item)
                and isinstance(item.get("parameters"), dict)
                and "response_schema" in item["parameters"]
            ):
                parameters = item["parameters"]
                filtered_items.append(
                    {
                        **item,
                        "parameters": {
                            key: parameter_value
                            for key, parameter_value in parameters.items()
                            if key != "response_schema"
                        },
                    }
                )
                continue

            filtered_items.append(item)

        authored_value[collection_name] = filtered_items
    return authored_value


def _contains_generated_form_response_schema(value: dict[str, Any]) -> bool:
    for collection_name in ("triggers", "nodes"):
        items = value.get(collection_name, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or not _is_form_node(item):
                continue
            parameters = item.get("parameters")
            if isinstance(parameters, dict) and "response_schema" in parameters:
                return True
    return False


def _is_form_node(item: dict[str, Any]) -> bool:
    node_type = item.get("type")
    return isinstance(node_type, str) and node_type in _FORM_NODE_TYPES


# Reusable annotated field types / validators: apply at the field's type annotation
# instead of redeclaring a per-class field_validator, so new labels/workflow_definition
# fields get the size cap automatically rather than by convention (a per-class
# copy-paste validator pattern previously let WorkflowUpdate.labels slip through
# uncapped). WorkflowDefinitionValidator is exposed standalone (rather than bundled
# into a type alias with WorkflowDefinition) to avoid a circular import: WorkflowDefinition
# lives in syntara.workflows.models, whose package __init__ transitively imports
# BaseResource from this module's own callers.
LabelsField = Annotated[dict[str, str], BeforeValidator(validate_labels_dict)]
OptionalLabelsField = Annotated[dict[str, str] | None, BeforeValidator(validate_labels_dict)]
WorkflowDefinitionValidator = BeforeValidator(validate_workflow_definition_json)
