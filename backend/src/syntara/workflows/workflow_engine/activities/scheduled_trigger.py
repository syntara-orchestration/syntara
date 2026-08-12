"""Scheduled trigger activity for v2 workflows.

Receives the schedule configuration and passes it through as the trigger output.
Schedule management (cron/interval firing) is handled by the scheduling
infrastructure (Temporal Schedules); this activity is the pass-through that
executes when the schedule fires.
"""

from typing import Any

import structlog
from temporalio import activity

from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

from .output_mapping import apply_output_mapping

logger = structlog.stdlib.get_logger(__name__)


@activity.defn(name=ActivityName.SCHEDULED_TRIGGER)
async def scheduled_trigger(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
) -> dict[str, Any]:
    """Execute scheduled trigger node.

    Returns normalized structure with output portion (no control needed for triggers).
    Output mapping is applied internally before returning to avoid storing suppressed
    fields in Temporal.

    Note: For scheduled triggers, input_config contains the schedule metadata
    (schedule_type, cron/interval, timezone). The actual scheduling is managed
    by Temporal Schedules; this activity runs when the schedule fires.

    Args:
        input_config: Schedule trigger configuration data
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
    logger.info("Executing scheduled trigger", schedule_keys=list(input_config.keys()) if input_config else [])

    mapped_output = apply_output_mapping(input_config, output_config)

    return {"output": mapped_output}
