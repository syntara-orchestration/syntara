"""EDA trigger activity for v2 workflows.

Delegates to webhook_trigger — the logic is identical. A separate Temporal
activity registration is kept so EDA and webhook executions are distinguishable
in Temporal UI, metrics, and logs.
"""

from typing import Any

from temporalio import activity

from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

from .webhook_trigger import webhook_trigger


@activity.defn(name=ActivityName.EDA_TRIGGER)
async def eda_trigger(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
) -> dict[str, Any]:
    """Execute EDA trigger node. Same pass-through logic as webhook_trigger."""
    return await webhook_trigger(input_config, output_config)
