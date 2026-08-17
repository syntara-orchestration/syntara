"""Loop activity implementation (for_each and do_while)."""

from typing import Any

import structlog
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, LoopOutput, LoopType

logger = structlog.stdlib.get_logger(__name__)


@activity.defn(name=ActivityName.LOOP)
async def loop(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
    iteration_results: dict[str, list[Any]],
) -> dict[str, Any]:
    """Loop activity that iterates over a collection or condition.

    Input config (for_each):
    - type: "for_each"
    - items: List of items to iterate over
    - current_index: Current iteration index (managed by workflow engine)

    Input config (do_while):
    - type: "do_while"
    - current_index: Current iteration index
    - condition_result: Boolean result of condition evaluation (None on first iteration)
    - max_iterations: Maximum iteration limit

    Args:
        input_config: Loop configuration
        output_config: Output mapping configuration
        iteration_results: Aggregated results from previous iterations

    Returns:
    - output: Mapped output containing iteration metadata
    - control: next_port ("iterate" or "complete") and loop state

    """
    loop_type = input_config.get("type", LoopType.FOR_EACH)
    current_index = input_config.get("current_index", 0)

    if loop_type == LoopType.FOR_EACH:
        items = input_config.get("items") or []
        if not isinstance(items, list):
            msg = f"'items' must be a list, got {type(items).__name__}"
            raise ApplicationError(msg, type="ConfigError", non_retryable=True)

        # Check if we have more items to process
        if current_index < len(items):
            current_item = items[current_index]
            next_port = "iterate"
            next_index = current_index + 1
        else:
            current_item = None
            next_port = "complete"
            next_index = current_index

        output = LoopOutput(
            iteration_count=current_index,
            iteration_results=iteration_results if next_port == "complete" else None,
        )

        return {
            "output": output.dump(output_config),
            "control": {
                "next_port": next_port,
                "next_index": next_index,
                "items": items,
                "current_item": current_item,
                "current_index": current_index,
            },
        }

    if loop_type == LoopType.DO_WHILE:
        condition_result = input_config.get("condition_result")

        # First iteration always executes (do-while semantic).
        # max_iterations enforcement happens in the workflow before this activity is called.
        if current_index == 0 or condition_result is True:
            next_port = "iterate"
            next_index = current_index + 1
        else:
            next_port = "complete"
            next_index = current_index

        output = LoopOutput(
            iteration_count=current_index,
            iteration_results=iteration_results if next_port == "complete" else None,
        )

        return {
            "output": output.dump(output_config),
            "control": {
                "next_port": next_port,
                "next_index": next_index,
                "current_index": current_index,
            },
        }

    msg = f"Unknown loop type: {loop_type}"
    raise ApplicationError(msg, type="ConfigError", non_retryable=True)
