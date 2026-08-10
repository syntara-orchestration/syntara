"""Converge node activity for v2 workflows."""

from typing import Any

import structlog
from temporalio import activity

from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, ConvergeOutput

logger = structlog.stdlib.get_logger(__name__)


@activity.defn(name=ActivityName.CONVERGE)
async def converge(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
    predecessor_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Execute converge node - merges results from completed predecessors.

    The actual waiting logic is handled by the workflow executor.
    This activity aggregates results from predecessors that completed
    before the convergence condition was met.

    Supports two strategies:
    - "all" (default): all predecessors must complete
    - "any": at least n_required predecessors must complete

    Args:
        input_config: Converge node configuration with strategy, n_required, total_branches
        output_config: Output mapping configuration (field_name -> template expression)
                       None = return full result, {} = suppress all, {...} = extract specific fields
        predecessor_results: Results from predecessor nodes that completed

    Returns:
        {"output": {"status": "completed", "branch_count": ..., "completed_count": ..., ...}}

    """
    completed_branch_ids = list(predecessor_results.keys())
    total_branches = input_config.get("total_branches", len(completed_branch_ids))

    output = ConvergeOutput(
        branch_count=total_branches,
        completed_count=len(completed_branch_ids),
        completed_branch_node_ids=completed_branch_ids,
    )

    return {"output": output.dump(output_config)}
