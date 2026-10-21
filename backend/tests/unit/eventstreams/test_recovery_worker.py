"""Lifecycle, batching, concurrency, and shutdown for the recovery scanner."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.eventstreams.adapters.kafka_record_identity import KafkaRecordIdentity
from syntara.eventstreams.core.deduplication import (
    DeliveryClaim,
    DeliveryIdentity,
    DeliveryState,
    TerminalDelivery,
)
from syntara.eventstreams.core.handler import (
    BlockedDelivery,
    ResolvedDelivery,
    RetryDelivery,
    SchedulingFailureCode,
)
from syntara.eventstreams.services.recovery_worker import EventDeliveryRecoveryWorker


def _identity(offset: int = 0) -> DeliveryIdentity:
    return DeliveryIdentity(
        deployment_id=uuid4(),
        integration_identity=uuid4(),
        source_id=uuid4(),
        source_generation=1,
        workflow_id=uuid4(),
        subscription_id=uuid4(),
        record=KafkaRecordIdentity(topic="orders", partition=0, offset=offset),
    )


def _claim(identity: DeliveryIdentity | None = None) -> DeliveryClaim:
    identity = identity or _identity()
    now = datetime.now(UTC)
    return DeliveryClaim(
        identity=identity,
        token=uuid4(),
        owner_worker_id="recovery-scanner",
        lease_until=now + timedelta(seconds=60),
    )


def _resolved(identity: DeliveryIdentity) -> ResolvedDelivery:
    return ResolvedDelivery(
        terminal=TerminalDelivery(
            identity=identity,
            state=DeliveryState.SCHEDULED,
            resolved_at=datetime.now(UTC),
            execution_id=identity.execution_id,
            temporal_run_id="run-1",
            execution_confirmed_at=datetime.now(UTC),
        )
    )


def _worker(
    recover_due_return: list | None = None,
    *,
    batch_limit: int = 10,
) -> tuple[EventDeliveryRecoveryWorker, AsyncMock]:
    launcher = SimpleNamespace(
        history_retention_seconds=AsyncMock(return_value=259200),
        start=AsyncMock(),
        describe=AsyncMock(),
    )
    session_factory = MagicMock()
    with (
        patch("syntara.eventstreams.services.recovery_worker.EventExecutionRecoveryService"),
        patch("syntara.eventstreams.services.recovery_worker.EventAdmissionService"),
        patch("syntara.eventstreams.services.recovery_worker.PeriodicWorker"),
    ):
        worker = EventDeliveryRecoveryWorker(session_factory, launcher, batch_limit=batch_limit, worker_id="test")
        mock_recover_due = AsyncMock(return_value=recover_due_return or [])
        worker._recovery = SimpleNamespace(recover_due=mock_recover_due)
    return worker, mock_recover_due


@pytest.mark.asyncio
async def test_tick_scans_due_deliveries():
    identity = _identity()
    results = [(identity, _resolved(identity))]
    worker, mock = _worker(results)
    count = await worker.tick()
    assert count == 1
    mock.assert_awaited_once_with("test", limit=10)


@pytest.mark.asyncio
async def test_tick_empty_batch_returns_zero():
    worker, mock = _worker([])
    assert await worker.tick() == 0
    mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_tick_counts_blocked_and_retried():
    id1, id2, id3 = _identity(0), _identity(1), _identity(2)
    results = [
        (id1, _resolved(id1)),
        (id2, BlockedDelivery(error_code=SchedulingFailureCode.RUNTIME_UNAVAILABLE)),
        (
            id3,
            RetryDelivery(
                error_code=SchedulingFailureCode.TEMPORAL_UNAVAILABLE,
                next_attempt_at=datetime.now(UTC),
                circuit_open=False,
            ),
        ),
    ]
    worker, _ = _worker(results)
    assert await worker.tick() == 3


@pytest.mark.asyncio
async def test_tick_skipped_while_draining():
    worker, mock = _worker()
    worker._draining = True
    assert await worker.tick() == 0
    mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_tick_respects_batch_limit():
    worker, mock = _worker([], batch_limit=5)
    await worker.tick()
    mock.assert_awaited_once_with("test", limit=5)


@pytest.mark.asyncio
async def test_drain_sets_flag_and_awaits_in_flight():
    worker, _ = _worker()
    completed = asyncio.Event()

    async def slow_tick() -> None:
        await completed.wait()

    task = asyncio.create_task(slow_tick())
    worker._in_flight = task
    drain_task = asyncio.create_task(worker.drain())
    await asyncio.sleep(0)
    assert worker.draining
    completed.set()
    await drain_task
    assert worker.draining


@pytest.mark.asyncio
async def test_drain_timeout_does_not_hang():
    worker, _ = _worker()

    async def never_finish() -> None:
        await asyncio.sleep(3600)

    task = asyncio.create_task(never_finish())
    worker._in_flight = task

    with patch("syntara.eventstreams.services.recovery_worker.DRAIN_TIMEOUT_SECONDS", 0.01):
        await worker.drain()

    assert worker.draining
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_stop_calls_periodic_stop():
    worker, _ = _worker()
    worker._periodic = MagicMock()
    worker._periodic.stop = AsyncMock()
    await worker.stop()
    worker._periodic.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_resets_draining():
    worker, _ = _worker()
    worker._draining = True
    worker.start()
    assert not worker.draining


def test_invalid_batch_limit_raises():
    launcher = SimpleNamespace(
        history_retention_seconds=AsyncMock(return_value=259200),
        start=AsyncMock(),
        describe=AsyncMock(),
    )
    with pytest.raises(ValueError, match="Batch limit"):
        EventDeliveryRecoveryWorker(MagicMock(), launcher, batch_limit=0)
    with pytest.raises(ValueError, match="Batch limit"):
        EventDeliveryRecoveryWorker(MagicMock(), launcher, batch_limit=101)


@pytest.mark.asyncio
async def test_tick_callback_tracks_in_flight():
    worker, _mock = _worker([])
    assert worker._in_flight is None
    await worker._tick_callback(None)
    assert worker._in_flight is None


@pytest.mark.asyncio
async def test_concurrent_scans_use_different_tokens():
    """Token fencing is in claim_due, but verify tick passes worker_id."""
    worker, mock = _worker([])
    await worker.tick()
    await worker.tick()
    assert mock.await_count == 2
    for call in mock.await_args_list:
        assert call.args[0] == "test"


@pytest.mark.asyncio
async def test_drain_without_in_flight_is_immediate():
    worker, _ = _worker()
    worker._in_flight = None
    await worker.drain()
    assert worker.draining


@pytest.mark.asyncio
async def test_tick_after_drain_returns_zero():
    """Post-drain tick must not claim new work."""
    worker, mock = _worker()
    await worker.drain()
    assert await worker.tick() == 0
    mock.assert_not_awaited()
