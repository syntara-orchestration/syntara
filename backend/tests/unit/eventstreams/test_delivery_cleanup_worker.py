"""Automatic cleanup scheduling, resource gates and bounded shutdown."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from syntara.core.constants import EventDeliveryDefaults
from syntara.eventstreams.adapters.kafka_retention_verifier import KafkaRetentionVerifier
from syntara.eventstreams.services.delivery_cleanup_worker import EventDeliveryCleanupWorker
from syntara.eventstreams.services.delivery_retention_service import EventDeliveryRetentionService
from syntara.eventstreams.services.worker_resources import EventWorkerResources
from tests.unit.eventstreams.test_consumer_service import eventually


def context(
    *,
    batch_limit: int = EventDeliveryDefaults.CLEANUP_BATCH_LIMIT,
    idle_seconds: float = EventDeliveryDefaults.CLEANUP_IDLE_SECONDS,
    batch_seconds: float = EventDeliveryDefaults.CLEANUP_BATCH_TIMEOUT_SECONDS,
) -> SimpleNamespace:
    trace: list[str] = []

    @asynccontextmanager
    async def batch() -> AsyncIterator[None]:
        trace.append("batch_open")
        try:
            yield
        finally:
            trace.append("client_closed")

    retention = MagicMock(spec=EventDeliveryRetentionService, cleanup=AsyncMock(return_value=0), last_scan_count=0)
    verifier = MagicMock(spec=KafkaRetentionVerifier, batch=batch)
    resources = MagicMock(spec=EventWorkerResources, accepting=True, scheduling_open=True, database_failed=MagicMock())
    worker = EventDeliveryCleanupWorker(
        retention, verifier, resources, batch_limit=batch_limit, idle_seconds=idle_seconds, batch_seconds=batch_seconds
    )
    return SimpleNamespace(worker=worker, retention=retention, resources=resources, trace=trace)


async def test_tick_uses_one_bounded_page_and_closes_probe():
    ctx = context(batch_limit=7)
    ctx.retention.cleanup.return_value = 3
    ctx.retention.last_scan_count = 7
    assert await ctx.worker.tick() == 3
    ctx.retention.cleanup.assert_awaited_once_with(limit=7)
    assert ctx.trace == ["batch_open", "client_closed"]


@pytest.mark.parametrize("gate", ["accepting", "scheduling_open"])
async def test_closed_process_gate_opens_no_cleanup_batch(gate):
    ctx = context()
    setattr(ctx.resources, gate, False)
    assert await ctx.worker.tick() == 0
    ctx.retention.cleanup.assert_not_awaited()
    assert not ctx.trace


async def test_database_failure_closes_shared_trust_without_losing_evidence():
    ctx = context()
    ctx.retention.cleanup.side_effect = SQLAlchemyError("PRIVATE error contents")
    assert await ctx.worker.tick() == 0
    ctx.resources.database_failed.assert_called_once()
    assert ctx.trace[-1] == "client_closed"


async def test_batch_deadline_closes_probe_and_allows_later_work():
    ctx = context(batch_seconds=0.01)

    async def wait(**_kwargs: object) -> None:
        await asyncio.Event().wait()

    ctx.retention.cleanup.side_effect = wait
    assert await ctx.worker.tick() == 0
    assert ctx.trace[-1] == "client_closed"
    ctx.retention.cleanup.side_effect = None
    assert await ctx.worker.tick() == 0
    assert ctx.retention.cleanup.await_count == 2


async def test_start_is_idempotent_and_stop_closes_inflight_batch():
    ctx = context()
    entered = asyncio.Event()

    async def wait(**_kwargs: object) -> None:
        entered.set()
        await asyncio.Event().wait()

    ctx.retention.cleanup.side_effect = wait
    ctx.worker.start()
    first = ctx.worker._task
    ctx.worker.start()
    assert ctx.worker._task is first
    await entered.wait()
    await ctx.worker.stop()
    assert ctx.trace == ["batch_open", "client_closed"]
    assert first.done()
    assert ctx.worker._task is None
    assert await ctx.worker.tick() == 0
    ctx.retention.cleanup.assert_awaited_once()


async def test_protected_pages_continue_without_waiting_for_idle_interval():
    ctx = context(idle_seconds=100)

    async def scan(**_kwargs: object) -> int:
        # Zero deletions is not an empty page: the next page still needs checking.
        ctx.retention.last_scan_count = 1 if ctx.retention.cleanup.await_count < 3 else 0
        return 0

    ctx.retention.cleanup.side_effect = scan
    ctx.worker.start()
    try:
        await eventually(lambda: ctx.retention.cleanup.await_count >= 3)
        assert ctx.worker._scanned == 0
    finally:
        await ctx.worker.stop()


async def test_parallel_ticks_do_not_share_a_probe_or_scan():
    ctx = context()
    entered, release = asyncio.Event(), asyncio.Event()

    async def scan(**_kwargs: object) -> int:
        entered.set()
        await release.wait()
        return 0

    ctx.retention.cleanup.side_effect = scan
    first = asyncio.create_task(ctx.worker.tick())
    await entered.wait()
    second = asyncio.create_task(ctx.worker.tick())
    await asyncio.sleep(0)
    assert ctx.retention.cleanup.await_count == 1
    release.set()
    await asyncio.gather(first, second)
    assert ctx.trace == ["batch_open", "client_closed", "batch_open", "client_closed"]


@pytest.mark.parametrize("limit", [0, 101, True])
def test_invalid_batch_limit_is_rejected(limit):
    with pytest.raises(ValueError, match="batch limit"):
        context(batch_limit=limit)
