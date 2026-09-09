"""Small command-line runner for local wake-up sample development."""

from __future__ import annotations

import argparse
import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from .contracts import SubmitTask, WakeHint
from .dispatchers.fake import FakeDispatcher
from .scheduler import SchedulingCore, WakeDrainLoop
from .settings import POCSettings


async def _run_local() -> None:
    from .adapters.local import LocalWakePublisher
    from .models import SQLModel
    from .store import AsyncExecutionStore

    settings = POCSettings.from_environment()
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    store = AsyncExecutionStore(
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False),
        lease_duration=settings.lease_duration,
    )
    dispatcher = FakeDispatcher(store)
    core = SchedulingCore(store, settings.owner_id, dispatcher.dispatch, claim_batch_size=settings.claim_batch_size)
    loop = WakeDrainLoop(core)
    publisher = LocalWakePublisher(loop)
    request = SubmitTask(queue="default", idempotency_key=str(uuid4()), task={"kind": "fake", "duration_ms": 10})
    submission = await store.enqueue(request)
    if submission.wake_event_id is None:
        raise RuntimeError("submission did not create a wake event")
    await publisher.publish(WakeHint(event_id=submission.wake_event_id, queue=request.queue))
    await loop.wait_idle(request.queue)
    await asyncio.sleep(0.02)
    print(submission.model_dump_json())
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=["local"], default="local", nargs="?")
    args = parser.parse_args()
    if args.role == "local":
        asyncio.run(_run_local())


if __name__ == "__main__":
    main()
