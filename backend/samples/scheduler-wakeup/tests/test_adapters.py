from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from scheduler_wakeup_poc.adapters.http import SchedulerWakeReceiver
from scheduler_wakeup_poc.adapters.jetstream import JetStreamSettings, JetStreamWakePublisher
from scheduler_wakeup_poc.adapters.temporal_client import make_run_pass_activity
from scheduler_wakeup_poc.contracts import PassResult, WakeHint


class RecordingScheduler:
    def __init__(self) -> None:
        self.queues: list[str] = []

    async def run_pass(self, queue: str) -> PassResult:
        self.queues.append(queue)
        return PassResult(claimed_count=0, deferred_count=0, immediate_more=False)


@pytest.mark.asyncio
async def test_http_receiver_coalesces_and_drains_a_hint() -> None:
    scheduler = RecordingScheduler()
    receiver = SchedulerWakeReceiver(scheduler, {"default"})
    await receiver.start()
    try:
        receipt = receiver.accept(WakeHint(event_id=uuid4(), queue="default"))
        assert receipt.acceptance == "volatile"
        for _ in range(20):
            if scheduler.queues:
                break
            await asyncio.sleep(0.005)
        assert scheduler.queues == ["default"]
    finally:
        await receiver.close()


class FakePublishAck:
    seq = 42


class FakeJetStream:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes, dict[str, str]]] = []

    async def publish(self, subject: str, payload: bytes, *, headers: dict[str, str]) -> FakePublishAck:
        self.published.append((subject, payload, headers))
        return FakePublishAck()


@pytest.mark.asyncio
async def test_jetstream_publisher_uses_run_scoped_subject_and_event_deduplication() -> None:
    settings = JetStreamSettings.for_run("run-1")
    client = FakeJetStream()
    hint = WakeHint(event_id=uuid4(), queue="default")
    receipt = await JetStreamWakePublisher(client, settings).publish(hint)
    assert receipt.acceptance == "durable"
    assert client.published[0][0] == "execution.scheduler.wake.poc.run-1.default"
    assert client.published[0][2]["Nats-Msg-Id"] == str(hint.event_id)


@pytest.mark.asyncio
async def test_temporal_activity_has_stable_registration_name() -> None:
    async def pass_once(queue: str) -> PassResult:
        return PassResult(claimed_count=1, deferred_count=0, immediate_more=False)

    activity = make_run_pass_activity(pass_once)
    assert await activity("default") == {
        "claimed_count": 1,
        "deferred_count": 0,
        "immediate_more": False,
        "next_due_at": None,
    }
