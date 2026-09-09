# Reproducing scheduler wake-up PoC results

## Prerequisites

- Python 3.12 or 3.13 and `uv`.
- Docker for the live JetStream measurement.
- No Docker service is required for the HTTP or Temporal measurements.
  Temporal uses `WorkflowEnvironment.start_time_skipping()`, which starts the
  SDK's local test server.

From the repository root:

```bash
cd backend/samples/scheduler-wakeup
uv sync
```

The first JetStream command installs the optional `nats-py` extra. The sample
uses its own virtual environment and lockfile, so it does not modify the main
backend lockfile.

## Reproduce the benchmark: one-command runner

Use `run-poc.sh` for the reproducible PoC measurement. It runs five batches of
100 tasks by default, prints the raw timing results, and writes
`artifacts/<adapter>-<id>/metrics.json`.

```bash
cd backend/samples/scheduler-wakeup
./run-poc.sh http
./run-poc.sh jetstream
./run-poc.sh temporal
```

Run the commands one at a time on the same otherwise-idle machine. Each
adapter uses the same workload:

```text
create 100 queued executions
→ publish one wake hint
→ wait for all 100 claims and fake-dispatch completions
→ repeat five times
→ report median elapsed time and tasks/second
```

The runner prints JSON similar to:

```json
{
  "adapter": "jetstream",
  "task_count": 100,
  "runs": 5,
  "elapsed_seconds": [0.20, 0.19, 0.21, 0.20, 0.18],
  "median_seconds": 0.20,
  "median_tasks_per_second": 500
}
```

Treat the generated `metrics.json` as the result to share or compare. It also
records the adapter and test-environment caveats. The artifact directory is
ignored by Git.

The HTTP run uses the FastAPI ASGI endpoint in-process. The JetStream run
starts and removes an ephemeral `nats:2.10-alpine` Docker container. To use a
pre-existing NATS server instead, set `POC_NATS_URL`:

```bash
POC_NATS_URL=nats://my-nats.example:4222 ./run-poc.sh jetstream
```

The Temporal run starts the Temporal Python SDK local test server and a local
worker, then stops both. Extra options are forwarded to the runner:

```bash
./run-poc.sh http --count 500 --runs 10
```

The equivalent Make entry point is:

```bash
make -C ../../ scheduler-wakeup-poc-bench ADAPTER=http
make -C ../../ scheduler-wakeup-poc-bench ADAPTER=jetstream
make -C ../../ scheduler-wakeup-poc-bench ADAPTER=temporal
```

`run-poc.sh` is the recommended interface because it also handles JetStream
container lifecycle and accepts `--count`, `--runs`, and `--output-dir`.

The detailed commands below remain useful when debugging a single adapter or
changing its measurement environment.

## First, verify correctness

Run the transport-independent correctness suite with recovery enabled:

```bash
make -C ../../ scheduler-wakeup-poc-test ADAPTER=http RECOVERY=on
make -C ../../ scheduler-wakeup-poc-test ADAPTER=jetstream RECOVERY=on
make -C ../../ scheduler-wakeup-poc-test ADAPTER=temporal RECOVERY=on
```

Each command should report seven passing tests. They cover drain-after-one-hint,
competing claims, stale-owner fencing, outbox retry, and the three adapter
envelopes. They do not require a live NATS or Temporal service.

## Local reference baseline

This exercises the store, local wake loop, and fake dispatcher. It is useful as
a lower-bound baseline, not a transport comparison.

```bash
PYTHONPATH=. uv run python - <<'PY'
import asyncio
from statistics import median
from scheduler_wakeup_poc.benchmark import run

async def main():
    values = [await run("local", 100) for _ in range(5)]
    seconds = [float(value["seconds"]) for value in values]
    print({"runs": values, "median_seconds": median(seconds), "median_per_second": 100 / median(seconds)})

asyncio.run(main())
PY
```

## HTTP measurement

The following uses the actual FastAPI route via `httpx.ASGITransport`; it does
not open a TCP socket. It measures 100 inserts, one HTTP wake, Scheduler claims,
and fake-dispatch completion. Run it five times and take the median.

```bash
PYTHONPATH=. uv run python - <<'PY'
import asyncio
from statistics import median
from time import monotonic
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
import httpx
from scheduler_wakeup_poc.adapters.http import HTTPWakePublisher, SchedulerWakeReceiver, create_scheduler_wake_app
from scheduler_wakeup_poc.contracts import SubmitTask, WakeHint
from scheduler_wakeup_poc.dispatchers.fake import FakeDispatcher
from scheduler_wakeup_poc.models import SQLModel
from scheduler_wakeup_poc.scheduler import SchedulingCore
from scheduler_wakeup_poc.store import AsyncExecutionStore

async def one_run():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    store = AsyncExecutionStore(async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))
    dispatcher = FakeDispatcher(store)
    core = SchedulingCore(store, "http-benchmark", dispatcher.dispatch)
    receiver = SchedulerWakeReceiver(core, {"benchmark"})
    await receiver.start()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_scheduler_wake_app(receiver)), base_url="http://scheduler") as client:
            publisher = HTTPWakePublisher("http://scheduler", client=client)
            started = monotonic()
            hint = None
            for index in range(100):
                submission = await store.enqueue(SubmitTask(queue="benchmark", idempotency_key=str(index), task={"duration_ms": 0}))
                hint = hint or WakeHint(event_id=submission.wake_event_id, queue="benchmark")
            await publisher.publish(hint)
            while len(dispatcher.accepted) < 100:
                await asyncio.sleep(0.001)
            await core.wait_for_dispatches()
            return monotonic() - started
    finally:
        await receiver.close()
        await engine.dispose()

async def main():
    results = [await one_run() for _ in range(5)]
    print({"runs_seconds": results, "median_seconds": median(results), "median_per_second": 100 / median(results)})

asyncio.run(main())
PY
```

## JetStream measurement

Start an ephemeral local broker in one terminal:

```bash
docker run --rm --name syntara-scheduler-wakeup-nats -p 4222:4222 nats:2.10-alpine -js -sd /data
```

In a second terminal, run the live broker benchmark. This command creates a
unique stream/consumer per run and uses a durable publish plus pull-consumer
delivery:

```bash
PYTHONPATH=. uv run --extra jetstream python - <<'PY'
import asyncio
from statistics import median
from time import monotonic
from uuid import uuid4
import nats
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from scheduler_wakeup_poc.adapters.jetstream import JetStreamSettings, JetStreamWakePublisher, JetStreamWakeReceiver, ensure_jetstream_resources
from scheduler_wakeup_poc.contracts import SubmitTask, WakeHint
from scheduler_wakeup_poc.dispatchers.fake import FakeDispatcher
from scheduler_wakeup_poc.models import SQLModel
from scheduler_wakeup_poc.scheduler import SchedulingCore
from scheduler_wakeup_poc.store import AsyncExecutionStore

async def one_run():
    settings = JetStreamSettings.for_run(str(uuid4()))
    connection = await nats.connect(servers=list(settings.servers))
    await ensure_jetstream_resources(connection.jetstream(), settings)
    await connection.close()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as database_connection:
        await database_connection.run_sync(SQLModel.metadata.create_all)
    store = AsyncExecutionStore(async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))
    dispatcher = FakeDispatcher(store)
    core = SchedulingCore(store, "jetstream-benchmark", dispatcher.dispatch)
    async def handle(hint): return await core.run_pass(hint.queue)
    receiver = await JetStreamWakeReceiver.connect(settings, handle, accepted_queues={"benchmark"})
    publisher = await JetStreamWakePublisher.connect(settings)
    try:
        started = monotonic(); hint = None
        for index in range(100):
            submission = await store.enqueue(SubmitTask(queue="benchmark", idempotency_key=str(index), task={"duration_ms": 0}))
            hint = hint or WakeHint(event_id=submission.wake_event_id, queue="benchmark")
        await publisher.publish(hint)
        await asyncio.wait_for(receiver.receive_once(), 5)
        await core.wait_for_dispatches()
        assert len(dispatcher.accepted) == 100
        return monotonic() - started
    finally:
        await publisher.close(); await receiver.close(); await engine.dispose()

async def main():
    results = [await one_run() for _ in range(5)]
    print({"runs_seconds": results, "median_seconds": median(results), "median_per_second": 100 / median(results)})

asyncio.run(main())
PY
```

Stop the broker with `Ctrl-C` in its terminal, or run:

```bash
docker rm -f syntara-scheduler-wakeup-nats
```

## Temporal measurement

This starts a local Temporal test server and a worker in the same process. It
measures start-to-completion for one durable wake workflow per 100-task batch.

```bash
PYTHONPATH=. uv run python - <<'PY'
import asyncio
from statistics import median
from time import monotonic
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from scheduler_wakeup_poc.adapters.temporal_client import TemporalWakePublisher, make_run_pass_activity
from scheduler_wakeup_poc.adapters.temporal_workflow import SchedulerWakeWorkflow
from scheduler_wakeup_poc.contracts import SubmitTask, WakeHint
from scheduler_wakeup_poc.dispatchers.fake import FakeDispatcher
from scheduler_wakeup_poc.models import SQLModel
from scheduler_wakeup_poc.scheduler import SchedulingCore
from scheduler_wakeup_poc.store import AsyncExecutionStore

async def main():
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        task_queue = "scheduler-wakeup-metric"
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)
        store = AsyncExecutionStore(async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))
        dispatcher = FakeDispatcher(store)
        core = SchedulingCore(store, "temporal-benchmark", dispatcher.dispatch)
        async with Worker(environment.client, task_queue=task_queue, workflows=[SchedulerWakeWorkflow], activities=[make_run_pass_activity(core.run_pass)]):
            publisher = TemporalWakePublisher(environment.client, task_queue)
            results = []
            for run in range(5):
                started = monotonic(); hint = None
                for index in range(100):
                    submission = await store.enqueue(SubmitTask(queue="benchmark", idempotency_key=f"{run}-{index}", task={"duration_ms": 0}))
                    hint = hint or WakeHint(event_id=submission.wake_event_id, queue="benchmark")
                await publisher.publish(hint)
                await environment.client.get_workflow_handle(f"scheduler-wake/{hint.event_id}").result()
                await core.wait_for_dispatches()
                results.append(monotonic() - started)
            print({"runs_seconds": results, "median_seconds": median(results), "median_per_second": 100 / median(results)})
        await engine.dispose()

asyncio.run(main())
PY
```

## Comparing results responsibly

Run all three on the same idle machine, use five or more runs, and record the
raw values. Do not compare the HTTP ASGI number to a remote HTTP deployment.
Before selecting a production transport, repeat the tests against PostgreSQL,
with independently running producer and Scheduler processes, and collect p50,
p95, p99, duplicate-claim, and recovery-lag metrics.
