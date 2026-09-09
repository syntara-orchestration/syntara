"""Open-loop-ish local benchmark for comparing adapter overhead."""

from __future__ import annotations

import argparse
import asyncio
from time import monotonic
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from .contracts import SubmitTask, WakeHint
from .adapters.local import LocalWakePublisher
from .dispatchers.fake import FakeDispatcher
from .models import SQLModel
from .scheduler import SchedulingCore, WakeDrainLoop
from .store import AsyncExecutionStore


async def run(adapter: str, count: int) -> dict[str, float | int | str]:
    """Run the local adapter reference; networked adapters need their services."""
    if adapter != "local":
        raise SystemExit(f"{adapter} requires its configured transport service; use adapter=local for this standalone runner")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    store = AsyncExecutionStore(async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))
    dispatcher = FakeDispatcher(store)
    core = SchedulingCore(store, "benchmark", dispatcher.dispatch)
    loop = WakeDrainLoop(core)
    publisher = LocalWakePublisher(loop)
    started = monotonic()
    first_hint: WakeHint | None = None
    for index in range(count):
        request = SubmitTask(queue="benchmark", idempotency_key=f"benchmark-{index}", task={"duration_ms": 0})
        submission = await store.enqueue(request)
        if first_hint is None:
            first_hint = WakeHint(event_id=submission.wake_event_id, queue="benchmark")
    assert first_hint is not None
    # A single advisory hint must drain a queue that accumulated while the
    # producer was busy. This avoids measuring one wake RPC per submission.
    await publisher.publish(first_hint)
    await loop.wait_idle("benchmark")
    if len(dispatcher.accepted) != count:
        raise RuntimeError(f"expected {count} accepted tasks, got {len(dispatcher.accepted)}")
    elapsed = monotonic() - started
    await engine.dispose()
    return {"adapter": adapter, "submissions": count, "seconds": elapsed, "per_second": count / elapsed}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", default="local")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args()
    print(asyncio.run(run(args.adapter, args.count)))


if __name__ == "__main__":
    main()
