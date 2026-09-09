from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from scheduler_wakeup_poc.adapters.local import LocalWakePublisher
from scheduler_wakeup_poc.contracts import SubmitTask, WakeHint
from scheduler_wakeup_poc.dispatchers.fake import FakeDispatcher
from scheduler_wakeup_poc.publication import WakeOutboxPublisher
from scheduler_wakeup_poc.scheduler import SchedulingCore, WakeDrainLoop


@pytest.mark.asyncio
async def test_one_hint_drains_more_than_a_claim_batch(store) -> None:
    dispatcher = FakeDispatcher(store)
    core = SchedulingCore(store, "scheduler-a", dispatcher.dispatch, claim_batch_size=2)
    loop = WakeDrainLoop(core)
    first = None
    for index in range(5):
        submission = await store.enqueue(SubmitTask(queue="default", idempotency_key=str(index), task={"duration_ms": 0}))
        first = first or submission
    await LocalWakePublisher(loop).publish(WakeHint(event_id=first.wake_event_id, queue="default"))
    await loop.wait_idle("default")
    for _ in range(100):
        if len(dispatcher.accepted) == 5:
            break
        await asyncio.sleep(0.01)
    assert len(dispatcher.accepted) == 5


@pytest.mark.asyncio
async def test_concurrent_claimers_only_get_one_valid_claim(store) -> None:
    submission = await store.enqueue(SubmitTask(queue="default", idempotency_key="only", task={}))
    first, second = await asyncio.gather(
        store.claim_ready("default", "one", 1), store.claim_ready("default", "two", 1)
    )
    assert len(first) + len(second) == 1
    assert (first or second)[0].execution_id == submission.execution_id


@pytest.mark.asyncio
async def test_expired_owner_is_fenced_and_work_is_claimable_again(store) -> None:
    await store.enqueue(SubmitTask(queue="default", idempotency_key="expired", task={}))
    original = (await store.claim_ready("default", "stalled-scheduler", 1))[0]
    await asyncio.sleep(0.06)
    assert await store.complete(original, {"too": "late"}) is False
    assert await store.recover_expired("default", 10) == 1
    recovered = (await store.claim_ready("default", "healthy-scheduler", 1))[0]
    assert recovered.execution_id == original.execution_id
    assert recovered.fencing_token == original.fencing_token + 1


@pytest.mark.asyncio
async def test_outbox_failure_keeps_a_retryable_durable_wake_intent(store) -> None:
    submission = await store.enqueue(SubmitTask(queue="default", idempotency_key="outbox", task={}))

    class FlakyPublisher:
        attempts = 0

        async def publish(self, hint):
            self.attempts += 1
            if self.attempts == 1:
                raise OSError("receiver unavailable")
            return object()

    publisher = FlakyPublisher()
    service = WakeOutboxPublisher(store, publisher, "task-executor", retry_delay=timedelta())
    assert await service.publish_due() == 0
    assert await service.publish_due() == 1
    assert publisher.attempts == 2
    assert submission.wake_event_id is not None
