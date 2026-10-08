"""Subworkflow Trigger activity for v2 workflows.

Child-side trigger substrate for the Sub-workflow (Reference) feature. This is
the dedicated trigger type that marks a workflow as eligible to be invoked as a
sub-workflow, and it follows the same pass-through and output-mapping convention
as the other v2 triggers.

Reference-mode invocation orchestration, eligibility resolution, authorization,
lineage, and the final Sub-workflow I/O / output contract are implemented
separately and are intentionally out of scope for this substrate.
"""

from typing import Any

import structlog
from temporalio import activity

from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

from .output_mapping import apply_output_mapping

logger = structlog.stdlib.get_logger(__name__)


@activity.defn(name=ActivityName.SUBWORKFLOW_TRIGGER)
async def subworkflow_trigger(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
) -> dict[str, Any]:
    """Execute a Subworkflow Trigger node.

    Provides the child-side trigger substrate for Sub-workflow invocation and
    follows the existing trigger output-mapping convention: the inputs passed to
    the trigger node are returned under ``output``, with ``output_config`` applied.

    Reference-mode invocation, eligibility resolution, authorization, lineage,
    and the final Sub-workflow I/O contract are handled separately.

    Args:
        input_config: Inputs passed to the trigger node.
        output_config: Output mapping configuration (field_name -> template expression).
                       None = return full result, {} = suppress all, {...} = extract specific fields.

    Returns:
        A normalized ``{"output": ...}`` structure, consistent with the other triggers.

    """
    mapped_output = apply_output_mapping(input_config, output_config)

    return {"output": mapped_output}
