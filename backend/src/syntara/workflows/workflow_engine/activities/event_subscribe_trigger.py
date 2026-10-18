"""Pass a supplied event envelope through ordinary workflow output mapping."""

from typing import Any

from temporalio import activity

from syntara.workflows.utils.output_mapping import apply_output_mapping
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName


@activity.defn(name=ActivityName.EVENT_SUBSCRIBE_TRIGGER)
async def event_subscribe_trigger(input_config: dict[str, Any], output_config: dict[str, str] | None) -> dict[str, Any]:
    """Expose the supplied envelope without changing it or logging its contents."""
    return {"output": apply_output_mapping(input_config, output_config)}
