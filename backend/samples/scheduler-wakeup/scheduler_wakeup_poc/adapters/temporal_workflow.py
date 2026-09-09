"""Dedicated Temporal workflow that invokes a bounded scheduling pass."""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

from ..contracts import PassResult, WakeHint

_MAX_PASSES_PER_RUN = 128


@workflow.defn(name="scheduler_wakeup_poc")
class SchedulerWakeWorkflow:
    """Keeps Temporal-specific control flow separate from the scheduling core."""

    @workflow.run
    async def run(self, hint: WakeHint, completed_passes: int = 0) -> None:
        # The default Temporal JSON converter materialises Pydantic models as
        # dictionaries. Keep the workflow usable without forcing the whole
        # application onto Temporal's optional Pydantic converter.
        hint = WakeHint.model_validate(hint)
        while True:
            result = await workflow.execute_activity(
                "scheduler_wakeup_poc_run_pass",
                hint.queue,
                start_to_close_timeout=timedelta(seconds=10),
                heartbeat_timeout=timedelta(seconds=5),
            )
            parsed = PassResult.model_validate(result)
            if not parsed.immediate_more:
                return
            completed_passes += 1
            if completed_passes >= _MAX_PASSES_PER_RUN:
                workflow.continue_as_new(hint, 0)
