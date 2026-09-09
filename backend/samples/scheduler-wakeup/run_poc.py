"""Run one reproducible Scheduler wake-up PoC without a composition factory."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from statistics import median
from time import monotonic
from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from scheduler_wakeup_poc.adapters.http import (
    HTTPWakePublisher,
    SchedulerWakeReceiver,
    create_scheduler_wake_app,
)
from scheduler_wakeup_poc.adapters.jetstream import (
    JetStreamSettings,
    JetStreamWakePublisher,
    JetStreamWakeReceiver,
    ensure_jetstream_resources,
)
from scheduler_wakeup_poc.adapters.temporal_client import (
    TemporalWakePublisher,
    make_run_pass_activity,
)
from scheduler_wakeup_poc.adapters.temporal_workflow import SchedulerWakeWorkflow
from scheduler_wakeup_poc.contracts import SubmitTask, WakeHint
from scheduler_wakeup_poc.dispatchers.fake import FakeDispatcher
from scheduler_wakeup_poc.models import SQLModel
from scheduler_wakeup_poc.scheduler import SchedulingCore
from scheduler_wakeup_poc.store import AsyncExecutionStore


async def _new_store() -> tuple[object, AsyncExecutionStore]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    store = AsyncExecutionStore(async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))
    return engine, store


async def _enqueue_batch(store: AsyncExecutionStore, run: int, count: int) -> WakeHint:
    hint: WakeHint | None = None
    for index in range(count):
        submission = await store.enqueue(
            SubmitTask(
                queue="benchmark",
                idempotency_key=f"{run}-{index}",
                task={"duration_ms": 0},
            )
        )
        if hint is None:
            if submission.wake_event_id is None:
                raise RuntimeError("new submission did not create a wake event")
            hint = WakeHint(event_id=submission.wake_event_id, queue="benchmark")
    if hint is None:
        raise ValueError("count must be positive")
    return hint


async def _wait_for_dispatches(core: SchedulingCore, dispatcher: FakeDispatcher, count: int) -> None:
    while len(dispatcher.accepted) < count:
        await asyncio.sleep(0.001)
    await core.wait_for_dispatches()


async def _run_http(count: int) -> float:
    engine, store = await _new_store()
    dispatcher = FakeDispatcher(store)
    core = SchedulingCore(store, "http-benchmark", dispatcher.dispatch)
    receiver = SchedulerWakeReceiver(core, {"benchmark"})
    await receiver.start()
    try:
        app = create_scheduler_wake_app(receiver)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://scheduler") as client:
            publisher = HTTPWakePublisher("http://scheduler", client=client)
            started = monotonic()
            hint = await _enqueue_batch(store, 0, count)
            await publisher.publish(hint)
            await _wait_for_dispatches(core, dispatcher, count)
            return monotonic() - started
    finally:
        await receiver.close()
        await engine.dispose()


async def _run_jetstream(count: int, nats_url: str) -> float:
    import nats

    settings = JetStreamSettings.for_run(str(uuid4()), servers=(nats_url,))
    connection = await nats.connect(servers=list(settings.servers))
    await ensure_jetstream_resources(connection.jetstream(), settings)
    await connection.close()

    engine, store = await _new_store()
    dispatcher = FakeDispatcher(store)
    core = SchedulingCore(store, "jetstream-benchmark", dispatcher.dispatch)

    async def handle(hint: WakeHint):
        return await core.run_pass(hint.queue)

    receiver = await JetStreamWakeReceiver.connect(settings, handle, accepted_queues={"benchmark"})
    publisher = await JetStreamWakePublisher.connect(settings)
    try:
        started = monotonic()
        hint = await _enqueue_batch(store, 0, count)
        await publisher.publish(hint)
        await asyncio.wait_for(receiver.receive_once(), timeout=5)
        await _wait_for_dispatches(core, dispatcher, count)
        return monotonic() - started
    finally:
        await publisher.close()
        await receiver.close()
        await engine.dispose()


async def _run_temporal(count: int) -> float:
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        engine, store = await _new_store()
        dispatcher = FakeDispatcher(store)
        core = SchedulingCore(store, "temporal-benchmark", dispatcher.dispatch)
        task_queue = f"scheduler-wakeup-poc-{uuid4()}"
        try:
            async with Worker(
                environment.client,
                task_queue=task_queue,
                workflows=[SchedulerWakeWorkflow],
                activities=[make_run_pass_activity(core.run_pass)],
            ):
                publisher = TemporalWakePublisher(environment.client, task_queue)
                started = monotonic()
                hint = await _enqueue_batch(store, 0, count)
                await publisher.publish(hint)
                workflow_id = f"scheduler-wake/{hint.event_id}"
                await environment.client.get_workflow_handle(workflow_id).result()
                await _wait_for_dispatches(core, dispatcher, count)
                return monotonic() - started
        finally:
            await engine.dispose()


async def run(adapter: str, count: int, runs: int, nats_url: str) -> dict[str, object]:
    runners = {
        "http": lambda: _run_http(count),
        "jetstream": lambda: _run_jetstream(count, nats_url),
        "temporal": lambda: _run_temporal(count),
    }
    elapsed = [await runners[adapter]() for _ in range(runs)]
    middle = median(elapsed)
    return {
        "adapter": adapter,
        "task_count": count,
        "runs": runs,
        "elapsed_seconds": elapsed,
        "median_seconds": middle,
        "median_tasks_per_second": count / middle,
        "notes": {
            "store": "SQLite in-memory",
            "dispatcher": "in-process fake dispatcher",
            "http": "ASGI in-process endpoint" if adapter == "http" else None,
            "jetstream": "live NATS JetStream broker" if adapter == "jetstream" else None,
            "temporal": "Temporal SDK local test server" if adapter == "temporal" else None,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("adapter", choices=("http", "jetstream", "temporal"))
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--nats-url", default="nats://127.0.0.1:4222")
    parser.add_argument("--output-dir", default="artifacts")
    args = parser.parse_args()
    if args.count < 1 or args.runs < 1:
        parser.error("--count and --runs must both be positive")
    result = asyncio.run(run(args.adapter, args.count, args.runs, args.nats_url))
    output_dir = Path(args.output_dir) / f"{args.adapter}-{uuid4()}"
    output_dir.mkdir(parents=True, exist_ok=False)
    output = output_dir / "metrics.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    print(f"metrics artifact: {output}")


if __name__ == "__main__":
    main()
