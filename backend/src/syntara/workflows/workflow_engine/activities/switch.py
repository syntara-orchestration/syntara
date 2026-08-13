"""Switch node activity for v2 workflows."""

from typing import Any

import structlog
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, SwitchOutput
from syntara.workflows.workflow_engine.unified_eval import safe_eval_with_namespace

logger = structlog.stdlib.get_logger(__name__)

# Per-expression complexity is bounded by unified_eval.py (10K chars, 50 depth, 500 AST nodes).
# This caps total case count to prevent unbounded sequential evaluation.
SWITCH_CASES_HARD_LIMIT = 100


def _validate_cases_structure(
    cases: Any,  # noqa: ANN401
) -> str | None:
    """Validate cases type, emptiness, and count. Returns error message or None."""
    if not isinstance(cases, list):
        return f"'cases' must be a list, got {type(cases).__name__}"
    if not cases:
        return "Missing or empty 'cases' in switch parameters"
    if len(cases) > SWITCH_CASES_HARD_LIMIT:
        return f"Switch node has {len(cases)} cases, exceeding the maximum of {SWITCH_CASES_HARD_LIMIT}"
    return None


def _validate_case_ports(
    cases: list[dict[str, Any]],
    default_port: str,
) -> str | None:
    """Validate port presence, uniqueness, and no conflict with default. Returns error message or None."""
    for i, c in enumerate(cases):
        if not c.get("port"):
            return f"Case at index {i} is missing required 'port' field"

    # Duplicate ports would cause multiple edges to match the same port,
    # scheduling both downstream branches instead of just one
    case_ports = [c["port"] for c in cases]
    if len(case_ports) != len(set(case_ports)):
        return "Duplicate case ports in switch parameters"

    # A case port matching default_port would make both the case edge
    # and the default edge share the same from_port, executing both
    if default_port in case_ports:
        return f"Case port '{default_port}' conflicts with default_port"

    return None


@activity.defn(name=ActivityName.SWITCH)
async def switch(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
) -> dict[str, Any]:
    """Execute switch node - evaluate per-case boolean expressions and route to first match.

    Uses unified context-aware evaluator (Tier 2). Each case has its own boolean
    condition evaluated in order. First truthy match determines the output port.
    If no case matches, routes to the default port.

    Returns normalized structure with output and control portions:
    - output: User-facing evaluation result (subject to output mapping)
    - control: Workflow routing data (next_port, never mapped or suppressed)

    Args:
        input_config: Switch node configuration with:
            - "cases": List of case dicts, each with "port", "label", "condition"
            - "default_port": Port name for unmatched values (default: "default")
            - "namespace": Complete namespace dict for variable lookup (READ-ONLY)
        output_config: Output mapping configuration (field_name -> template expression)
                       None = return full result, {} = suppress all, {...} = extract specific fields

    Returns:
        {
            "output": {
                "status": "completed",
                "matched_port": str
            },
            "control": {
                "next_port": str
            }
        }

    """
    cases = input_config.get("cases", [])
    default_port = input_config.get("default_port", "default")
    # Namespace is already a deep copy from get_complete_namespace()
    # Temporal provides process isolation, so no additional copy needed
    namespace = input_config.get("namespace", {})

    structure_error = _validate_cases_structure(cases)
    if structure_error:
        logger.warning("switch_activity_failed", error_type="ConfigError", error=structure_error)
        raise ApplicationError(structure_error, type="ConfigError", non_retryable=True)

    port_error = _validate_case_ports(cases, default_port)
    if port_error:
        logger.warning("switch_activity_failed", error_type="ConfigError", error=port_error)
        raise ApplicationError(port_error, type="ConfigError", non_retryable=True)

    logger.info("switch_activity_started", case_count=len(cases))

    for index, case in enumerate(cases):
        case_condition = case.get("condition") or ""
        if not case_condition:
            continue

        try:
            # Tier 2 evaluation: AST-based with direct namespace lookup
            evaluated = safe_eval_with_namespace(case_condition, namespace)
        except (ValueError, KeyError, TypeError, IndexError) as e:
            # RuntimeError intentionally NOT caught: Temporal infrastructure errors
            # (heartbeat timeout, cancellation) should propagate and fail loudly.
            logger.warning(
                "switch_activity_failed",
                error_type="SwitchEvaluationError",
                case_index=index,
                condition=case_condition,
                error=str(e),
            )
            msg = f"Failed to evaluate case {index} condition '{case_condition}': {e!s}"
            raise ApplicationError(msg, type="SwitchEvaluationError", non_retryable=True) from None

        if evaluated:
            case_port = case["port"]
            output = SwitchOutput(matched_port=case_port)

            logger.info("switch_activity_completed", matched_port=case_port)

            return {
                "output": output.dump(output_config),
                "control": {"next_port": case_port},
            }

    # No case matched — route to default
    output = SwitchOutput(matched_port=default_port)

    logger.info("switch_activity_completed", matched_port=default_port)

    return {
        "output": output.dump(output_config),
        "control": {"next_port": default_port},
    }
