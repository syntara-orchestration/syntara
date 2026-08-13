"""Condition node activity for v2 workflows."""

from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, ConditionOutput
from syntara.workflows.workflow_engine.unified_eval import safe_eval_with_namespace


@activity.defn(name=ActivityName.CONDITION)
async def condition(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
) -> dict[str, Any]:
    """Execute condition node - evaluate expression with namespace context.

    Uses unified context-aware evaluator (Tier 2).

    Returns normalized structure with output and control portions:
    - output: User-facing evaluation result (subject to output mapping)
    - control: Workflow routing data (next_port, never mapped or suppressed)

    Output mapping is applied internally before returning to avoid storing suppressed fields in Temporal.

    Args:
        input_config: Condition node configuration with:
            - "condition": Boolean expression (e.g., "${status} == 'completed'")
            - "namespace": Complete namespace dict for variable lookup (READ-ONLY)
        output_config: Output mapping configuration (field_name -> template expression)
                       None = return full result, {} = suppress all, {...} = extract specific fields

    Returns:
        {
            "output": {
                "status": "completed",
                "evaluated_result": bool  # Only if not suppressed
            },
            "control": {
                "next_port": "true" | "false"
            }
        }

    Note:
        The namespace parameter is treated as read-only. While Temporal's serialization
        provides process isolation, we make a defensive copy to prevent accidental mutations
        and ensure the contract is clear.

    """
    condition_expr = input_config.get("condition", "")
    # Namespace is already a deep copy from get_complete_namespace()
    # Temporal provides process isolation, so no additional copy needed
    namespace = input_config.get("namespace", {})

    if not condition_expr:
        msg = "Missing 'condition' in parameters"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True)

    try:
        # NEW: Use unified context-aware evaluator (Tier 2)
        evaluated_result = safe_eval_with_namespace(condition_expr, namespace)

        output = ConditionOutput(evaluated_result=evaluated_result)

        return {
            "output": output.dump(output_config),
            "control": {
                "next_port": "true" if evaluated_result else "false",
            },
        }

    except (ValueError, KeyError, TypeError, IndexError) as e:
        # RuntimeError intentionally NOT caught: we prefer Temporal infrastructure
        # errors (heartbeat timeout, cancellation) to propagate and fail loudly.
        # AttributeError removed: _eval_attribute raises TypeError for type mismatches.
        # IndexError added: _eval_subscript raises it for out-of-range list access.
        msg = f"Failed to evaluate condition '{condition_expr}': {e!s}"
        raise ApplicationError(msg, type="ConditionEvaluationError", non_retryable=True) from e
