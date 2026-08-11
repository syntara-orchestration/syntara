"""Manual trigger activity for v2 workflows."""

from typing import Any

import structlog
from temporalio import activity

from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

from .output_mapping import apply_output_mapping

logger = structlog.stdlib.get_logger(__name__)


@activity.defn(name=ActivityName.MANUAL_TRIGGER)
async def manual_trigger(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
) -> dict[str, Any]:
    """Execute manual trigger node.

    Returns normalized structure with output portion (no control needed for triggers).
    Output mapping is applied internally before returning to avoid storing suppressed fields in Temporal.

    Note: For triggers, input_config contains the user-provided inputs.
    Validation happens before workflow starts (in API layer), so this is just a pass-through.

    Args:
        input_config: User-provided inputs when workflow was triggered
        output_config: Output mapping configuration (field_name -> template expression)
                       None = return full result, {} = suppress all, {...} = extract specific fields

    Returns:
        {
            "output": {
                "status": "completed",
                ...input_config  # Only if not suppressed by output_config
            }
        }

    """
    # For prototype: skip input schema validation, just return inputs

    # Apply output mapping (suppresses fields before Temporal stores it)
    mapped_output = apply_output_mapping(input_config, output_config)

    return {"output": mapped_output}
