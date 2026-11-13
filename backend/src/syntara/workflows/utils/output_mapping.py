"""Shared utility for applying output mapping to node results."""

from enum import StrEnum
from typing import Any

import jsonschema
from temporalio.exceptions import ApplicationError

from syntara.workflows.utils.namespace_resolver import TEMPLATE_PATTERN, NamespaceResolver


class DeclaredOutputErrorCode(StrEnum):
    """Stable internal categories for declared output contract failures."""

    MAPPING_TYPE = "mapping_type"
    INVALID_PATH = "invalid_path"
    UNDECLARED_PATH = "undeclared_path"
    CONFLICTING_PATH = "conflicting_path"
    INVALID_SCHEMA = "invalid_schema"
    SCHEMA_VIOLATION = "schema_violation"
    MAPPING_EXPRESSION = "mapping_expression"


class DeclaredOutputContractError(ValueError):
    """Raised when a child workflow cannot satisfy its declared output contract."""

    def __init__(self, code: DeclaredOutputErrorCode, detail: str = "") -> None:
        """Build a safe runtime error from a short code and optional detail."""
        self.code = code
        self.detail = detail
        super().__init__(self._message())

    def _message(self) -> str:
        messages = {
            "mapping_type": "Output mappings must use string paths and expressions",
            "invalid_path": f"Invalid declared output path: {self.detail}",
            "undeclared_path": f"Output mapping path '{self.detail}' is not declared in output_schema",
            "conflicting_path": f"Conflicting output mapping paths near '{self.detail}'",
            "invalid_schema": f"Invalid declared output schema: {self.detail}",
            "schema_violation": f"Declared outputs do not satisfy the schema at {self.detail}",
            "mapping_expression": "Output mappings must be full template expressions such as ${step.field}",
        }
        return messages.get(self.code, "Declared output contract violation")


def _declared_schema_paths(schema: dict[str, Any], prefix: tuple[str, ...] = ()) -> set[str]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return set()

    paths: set[str] = set()
    for name, property_schema in properties.items():
        if not isinstance(name, str) or not isinstance(property_schema, dict):
            continue
        path = (*prefix, name)
        paths.add(".".join(path))
        paths.update(_declared_schema_paths(property_schema, path))
    return paths


def _set_declared_output(outputs: dict[str, Any], path: list[str], value: object) -> None:
    current = outputs
    for segment in path[:-1]:
        child = current.get(segment)
        if child is None:
            child = {}
            current[segment] = child
        if not isinstance(child, dict):
            raise DeclaredOutputContractError(DeclaredOutputErrorCode.CONFLICTING_PATH, segment)
        current = child

    leaf_name = path[-1]
    existing_value = current.get(leaf_name)
    if leaf_name in current and (isinstance(existing_value, dict) or isinstance(value, dict)):
        raise DeclaredOutputContractError(DeclaredOutputErrorCode.CONFLICTING_PATH, leaf_name)
    current[leaf_name] = value


def apply_output_mapping(result: dict[str, Any], output_config: dict[str, str] | None) -> dict[str, Any]:
    """Apply output mapping to activity result.

    Used by NodeOutput.dump() to filter executor fields before the result is
    returned to the workflow layer.  The workflow layer adds ``status`` and
    ``error`` after this function runs, so this function only deals with
    executor-specific fields.

    Mapping rules:
    - If output_config is None, return the result unchanged
    - If output_config is {} (empty), return {} (suppress all executor fields)
    - If output_config has mappings, extract only mapped fields

    Args:
        result: Executor output data (no status/error — those are added later)
        output_config: Optional output mapping (field_name -> template expression)
                       None = no mapping (return full result)
                       {} = suppress all outputs
                       {...} = extract specific fields

    Returns:
        Mapped result

    """
    if output_config is None:
        return result

    if not output_config:
        return {}

    temp_resolver = NamespaceResolver()
    temp_resolver.set_namespace("result", result)

    mapped_result: dict[str, Any] = {}
    for output_key, template_expr in output_config.items():
        try:
            mapped_result[output_key] = temp_resolver.resolve_value(template_expr)
        except (KeyError, AttributeError, TypeError) as exc:
            msg = f"Failed to resolve output mapping '{template_expr}': {type(exc).__name__}"
            raise ApplicationError(msg, type="OutputMappingError", non_retryable=True) from exc

    return mapped_result


def apply_declared_output_mapping(
    resolver: NamespaceResolver,
    output_schema: dict[str, Any],
    output_mapping: dict[str, str] | None,
) -> dict[str, Any]:
    """Resolve declared child outputs and enforce the JSON Schema contract.

    Missing optional values are omitted. Missing required values, invalid types,
    and malformed mappings fail the child workflow so a parent never receives a
    successful result that violates the published contract.
    """
    declared: dict[str, Any] = {}
    schema_paths = _declared_schema_paths(output_schema)

    for output_path, expression in (output_mapping or {}).items():
        if not isinstance(output_path, str) or not isinstance(expression, str):
            raise DeclaredOutputContractError(DeclaredOutputErrorCode.MAPPING_TYPE)
        path = output_path.split(".")
        if any(not segment for segment in path):
            raise DeclaredOutputContractError(DeclaredOutputErrorCode.INVALID_PATH, output_path)
        if output_path not in schema_paths:
            raise DeclaredOutputContractError(DeclaredOutputErrorCode.UNDECLARED_PATH, output_path)
        if TEMPLATE_PATTERN.fullmatch(expression.strip()) is None:
            raise DeclaredOutputContractError(DeclaredOutputErrorCode.MAPPING_EXPRESSION)

        try:
            value = resolver.resolve_value(expression)
        except (KeyError, AttributeError, TypeError, IndexError):
            # Whether a missing value is acceptable is determined by the schema below.
            continue

        _set_declared_output(declared, path, value)

    try:
        errors = sorted(
            jsonschema.Draft7Validator(output_schema).iter_errors(declared),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
    except jsonschema.SchemaError as exc:
        raise DeclaredOutputContractError(DeclaredOutputErrorCode.INVALID_SCHEMA, exc.message) from exc

    if errors:
        first_error = errors[0]
        field_path = ".".join(str(part) for part in first_error.absolute_path) or "outputs"
        raise DeclaredOutputContractError(
            DeclaredOutputErrorCode.SCHEMA_VIOLATION, f"'{field_path}': {first_error.message}"
        )

    return declared
