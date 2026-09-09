"""Temporal publisher and activity factory for the wake-up PoC."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from temporalio import activity
from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from ..contracts import PassResult, PublishReceipt, WakeHint
from .temporal_workflow import SchedulerWakeWorkflow


class TemporalWakePublisher:
    """Publishes one durable Temporal workflow per advisory wake event."""

    def __init__(self, client: Client, task_queue: str) -> None:
        self._client = client
        self._task_queue = task_queue

    async def publish(self, hint: WakeHint) -> PublishReceipt:
        workflow_id = f"scheduler-wake/{hint.event_id}"
        try:
            handle = await self._client.start_workflow(
                SchedulerWakeWorkflow.run,
                hint,
                id=workflow_id,
                task_queue=self._task_queue,
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
            )
        except WorkflowAlreadyStartedError:
            return PublishReceipt(acceptance="durable", transport_ref=workflow_id)
        return PublishReceipt(acceptance="durable", transport_ref=f"{workflow_id}/{handle.result_run_id}")


def make_run_pass_activity(
    scheduler_run_pass: Callable[[str], Awaitable[PassResult]],
) -> Callable[[str], Awaitable[dict[str, object]]]:
    """Create the registered activity without coupling the shared core to Temporal."""

    @activity.defn(name="scheduler_wakeup_poc_run_pass")
    async def run_pass(queue: str) -> dict[str, object]:
        return (await scheduler_run_pass(queue)).model_dump(mode="json")

    return run_pass
