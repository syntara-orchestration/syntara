"""Worker-scoped TFE execution selection, keeping Temporal activity names stable."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from temporalio import activity

from syntara.terraform.errors import TFEError
from syntara.terraform.step_bindings import TFE_STEP_BINDINGS
from syntara.workflows.workflow_engine.activities.tfe_activities import TFE_ACTIVITIES
from syntara.workflows.workflow_engine.activities.tfe_common import raise_as_application_error
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

if TYPE_CHECKING:
    from syntara.terraform.step_executor import TFEStepExecutor


TFEActivity = Callable[[dict[str, Any], dict[str, str] | None], Awaitable[dict[str, Any]]]


def _sdk_activity(node_type: str, executor: TFEStepExecutor) -> TFEActivity:
    async def execute(input_config: dict[str, Any], outputs: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            return await executor.execute(node_type, input_config, outputs)
        except TFEError as exc:
            raise_as_application_error(exc)
            raise

    execute.__name__ = f"execute_{node_type}_activity"
    return activity.defn(name=ActivityName(execute.__name__))(execute)


def build_tfe_activity_registry(executor: TFEStepExecutor | None = None) -> dict[ActivityName, TFEActivity]:
    """Select the backend at worker startup, never from untrusted workflow inputs.

    Default registration uses the existing native activity implementations.
    An explicitly supplied executor replaces only the TFE activity functions.
    No module-global mutable backend or cross-worker selection is used.
    """
    if executor is None:
        return {ActivityName(fn.__name__): fn for fn in TFE_ACTIVITIES}
    return {
        ActivityName(f"execute_{node_type}_activity"): _sdk_activity(node_type, executor)
        for node_type in TFE_STEP_BINDINGS
    }
