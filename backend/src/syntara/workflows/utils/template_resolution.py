"""Template expression resolution utilities for workflow activities.

This module provides shared functionality for resolving template expressions
in activity configurations before validation.
"""

from typing import Any

from syntara.workflows.workflow_engine.expression_resolver import ExpressionResolver


def resolve_value(
    value: Any,  # noqa: ANN401
    resolver: ExpressionResolver,
    workflow_state: dict[str, Any],
) -> Any:  # noqa: ANN401
    """Recursively resolve a value (dict, list, or primitive).

    Args:
        value: Value to resolve
        resolver: Expression resolver
        workflow_state: Workflow state for expression resolution

    Returns:
        Resolved value

    """
    if isinstance(value, dict):
        # Recursively resolve dictionaries
        return {k: resolve_value(v, resolver, workflow_state) for k, v in value.items()}
    if isinstance(value, list):
        # Recursively resolve lists
        return [resolve_value(item, resolver, workflow_state) for item in value]
    # Resolve template expressions or return primitive values
    return resolver.resolve_expression(value, workflow_state)


def resolve_parameter_templates(
    config_dict: dict[str, Any],
    workflow_state: dict[str, Any],
    resolver: ExpressionResolver | None = None,
    exclude_fields: set[str] | None = None,
) -> dict[str, Any]:
    """Resolve template expressions in node parameters before validation.

    This handles fields like timeout, job_template_id, verbosity, etc. that need
    to be resolved from template strings (e.g., ${input.custom_timeout}) to actual
    values before Pydantic validation.

    Also handles nested dictionaries and lists recursively.

    Args:
        config_dict: Raw parameters dictionary with potential templates
        workflow_state: Workflow state for expression resolution
        resolver: Optional expression resolver (creates new one if not provided)
        exclude_fields: Set of field names to exclude from template resolution
                       (e.g., script code that may contain shell variables)

    Returns:
        Parameters dictionary with resolved template expressions

    """
    if resolver is None:
        resolver = ExpressionResolver()
    if exclude_fields is None:
        exclude_fields = set()

    return {
        key: value if key in exclude_fields else resolve_value(value, resolver, workflow_state)
        for key, value in config_dict.items()
    }
