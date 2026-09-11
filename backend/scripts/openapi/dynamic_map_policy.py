"""Shared constants and helpers for dynamic-map OpenAPI breaking-change policy."""

from __future__ import annotations

from typing import Any

# Fields checked by detect_dynamic_map_constraint_tightening().
DYNAMIC_MAP_FIELD_NAMES = frozenset(
    {
        "labels",
        "context_data",
        "input_data",
        "output_data",
        "result",
    }
)

# JSON Schema constraint keys compared by _json_schema_strictly_narrows().
SCHEMA_CONSTRAINT_KEYS_EVALUATED = frozenset(
    {
        "type",
        "maxLength",
        "minLength",
        "enum",
        "maxItems",
        "minItems",
        "maximum",
        "minimum",
    }
)

# Constraint keys intentionally not compared (documented known gaps).
SCHEMA_CONSTRAINT_KEYS_NOT_EVALUATED = frozenset(
    {
        "pattern",
        "format",
        "multipleOf",
        "exclusiveMinimum",
        "exclusiveMaximum",
    }
)

# Property names matching these rules must appear in DYNAMIC_MAP_FIELD_NAMES unless excluded.
POLICY_REGISTRY_EXACT_NAMES = frozenset({"labels", "result"})
POLICY_REGISTRY_SUFFIXES = ("_data",)

# Workflow-internal or non-resource dynamic maps excluded from registry enforcement.
EXCLUDED_DYNAMIC_MAP_FIELD_NAMES = frozenset(
    {
        # Execution signal payload to activities; not a resource metadata map.
        "signal_data",
    }
)

# OpenAPI sources excluded from the dynamic-map field registry scan.
REGISTRY_SCAN_IGNORE_GLOBS = (
    "openapi.yaml",
    "openapi-public.yaml",
    "openapi-public.json",
    "*websocket*",
    "*asyncapi*",
)


def is_policy_registry_field_name(name: str) -> bool:
    """Return True when a dynamic-map property name must be registered for policy checks."""
    if name in EXCLUDED_DYNAMIC_MAP_FIELD_NAMES:
        return False
    if name in POLICY_REGISTRY_EXACT_NAMES:
        return True
    return any(name.endswith(suffix) for suffix in POLICY_REGISTRY_SUFFIXES)


def is_dynamic_map_schema(schema: Any) -> bool:
    """Return True when a schema node represents an open object map."""
    if not isinstance(schema, dict):
        return False

    additional_properties = schema.get("additionalProperties")
    if additional_properties is False:
        return False
    if additional_properties is True or isinstance(additional_properties, dict):
        if schema.get("type") == "object" or "additionalProperties" in schema:
            return True

    for key in ("anyOf", "oneOf"):
        variants = schema.get(key)
        if isinstance(variants, list):
            for variant in variants:
                if isinstance(variant, dict) and is_dynamic_map_schema(variant):
                    return True
    return False


def collect_policy_registry_field_names(node: Any) -> set[str]:
    """Collect dynamic-map property names that must be registered for policy checks."""
    found: set[str] = set()

    def walk(current: Any) -> None:
        if isinstance(current, list):
            for item in current:
                walk(item)
            return
        if not isinstance(current, dict):
            return

        properties = current.get("properties")
        if isinstance(properties, dict):
            for field_name, field_schema in properties.items():
                if is_policy_registry_field_name(field_name) and is_dynamic_map_schema(field_schema):
                    found.add(field_name)

        for key, value in current.items():
            if key == "properties":
                continue
            if isinstance(value, dict):
                walk(value)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

    walk(node)
    return found
