"""Form trigger activity for V2 workflows."""

from typing import Any

import structlog
from temporalio import activity

from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

from .output_mapping import apply_output_mapping

logger = structlog.stdlib.get_logger(__name__)


@activity.defn(name=ActivityName.FORM_TRIGGER)
async def form_trigger(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
) -> dict[str, Any]:
    """Pass submitted form values through the trigger's output mapping.

    The mapped values are nested under ``response_data``: fields are available as
    ``${<node_id>.response_data.<value_name>}`` and in the shared
    ``${trigger.response_data.<value_name>}`` namespace, matching form_prompt. No
    submitter metadata is injected; workflows can read it from
    ``workflow_context.execution.created_by`` and ``workflow_context.execution.created_at``.
    """
    logger.info("Executing form trigger", field_count=len(input_config or {}))
    mapped_output = apply_output_mapping(input_config, output_config)
    return {"output": {"response_data": mapped_output}}
