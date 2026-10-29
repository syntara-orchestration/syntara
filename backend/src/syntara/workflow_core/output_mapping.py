"""Shared utility for applying output mapping to node results."""

from typing import Any

from syntara.workflow_core.utils.namespace_resolver import NamespaceResolver


class OutputMappingError(ValueError):
    """Raised when a workflow output mapping cannot be resolved."""


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
            raise OutputMappingError(msg) from exc

    return mapped_result
