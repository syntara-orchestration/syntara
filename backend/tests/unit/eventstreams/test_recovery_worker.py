"""Lifecycle, batching, concurrency, and shutdown for the recovery scanner."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.eventstreams.adapters.kafka_record_identity import KafkaRecordIdentity
from syntara.eventstreams.core.deduplication import (
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
    results_sequence: list[object | None] | None = None,
    *,
    batch_limit: int = 10,
) -> tuple[EventDeliveryRecoveryWorker, AsyncMock]:
    """Build a worker with mocked _claim_and_recover_one.

    results_sequence: successive return values. None signals no more work.
    Defaults to [None] (empty scan).
    """
    launcher = SimpleNamespace(
        history_retention_seconds=AsyncMock(return_value=259200),
        start=AsyncMock(),
        describe=AsyncMock(),
    )
    session_factory = MagicMock()
    with (
        patch("syntara.eventstreams.services.recovery_worker.EventAdmissionService"),
        patch("syntara.eventstreams.services.recovery_worker.PeriodicWorker"),
    ):
        worker = EventDeliveryRecoveryWorker(session_factory, launcher, batch_limit=batch_limit, worker_id="test")
    sequence = results_sequence if results_sequence is not None else [None]
    mock_claim_recover = AsyncMock(side_effect=sequence)
    worker._claim_and_recover_one = mock_claim_recover  # type: ignore[assignment]
    return worker, mock_claim_recover


@pytest.mark.asyncio
async def test_tick_scans_due_deliveries() -> None:
    identity = _identity()
    worker, mock = _worker([_resolved(identity), None])
    count = await worker.tick()
    assert count == 1
    assert mock.await_count == 2


@pytest.mark.asyncio
async def test_tick_empty_batch_returns_zero() -> None:
    worker, mock = _worker([None])
    assert await worker.tick() == 0
    mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_tick_counts_blocked_and_retried() -> None:
    id1 = _identity(0)
    worker, _ = _worker(
        [
            _resolved(id1),
            BlockedDelivery(error_code=SchedulingFailureCode.RUNTIME_UNAVAILABLE),
            RetryDelivery(
                error_code=SchedulingFailureCode.TEMPORAL_UNAVAILABLE,
                next_attempt_at=datetime.now(UTC),
                circuit_open=False,
            ),
            None,
        ]
    )
    assert await worker.tick() == 3


@pytest.mark.asyncio
async def test_tick_skipped_while_draining() -> None:
    worker, mock = _worker()
    worker._draining = True
    assert await worker.tick() == 0
    mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_tick_stops_at_batch_limit() -> None:
    results = [_resolved(_identity(i)) for i in range(10)]
    worker, mock = _worker(results, batch_limit=5)
    count = await worker.tick()
    assert count == 5
    assert mock.await_count == 5


@pytest.mark.asyncio
async def test_drain_sets_flag_and_awaits_in_flight() -> None:
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
async def test_drain_timeout_does_not_hang() -> None:
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
async def test_stop_drains_before_periodic_stop() -> None:
    """drain() must complete before PeriodicWorker.stop() to protect in-flight work."""
    worker, _ = _worker()
    call_order: list[str] = []

    async def mock_drain() -> None:
        call_order.append("drain")

    periodic_mock = MagicMock()

    async def mock_periodic_stop() -> None:
        call_order.append("periodic_stop")

    periodic_mock.stop = mock_periodic_stop
    worker._periodic = periodic_mock
    worker.drain = mock_drain  # type: ignore[assignment]
    await worker.stop()
    assert call_order == ["drain", "periodic_stop"]


@pytest.mark.asyncio
async def test_stop_during_active_tick_drains_in_flight() -> None:
    """Stop during active tick awaits in-flight recovery before stopping periodic."""
    worker, _ = _worker()
    tick_started = asyncio.Event()
    tick_release = asyncio.Event()
    drained = False

    async def slow_tick() -> None:
        tick_started.set()
        await tick_release.wait()

    task = asyncio.create_task(slow_tick())
    worker._in_flight = task

    async def do_stop() -> None:
        nonlocal drained
        await worker.stop()
        drained = True

    worker._periodic = MagicMock()
    worker._periodic.stop = AsyncMock()

    stop_task = asyncio.create_task(do_stop())
    await tick_started.wait()
    assert not drained
    assert worker.draining
    tick_release.set()
    await stop_task
    assert drained
    worker._periodic.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_resets_draining() -> None:
    worker, _ = _worker()
    worker._draining = True
    worker.start()
    assert not worker.draining


def test_invalid_batch_limit_raises() -> None:
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
async def test_tick_callback_tracks_in_flight() -> None:
    worker, _ = _worker([None])
    assert worker._in_flight is None
    await worker._tick_callback(None)
    assert worker._in_flight is None


@pytest.mark.asyncio
async def test_drain_without_in_flight_is_immediate() -> None:
    worker, _ = _worker()
    worker._in_flight = None
    await worker.drain()
    assert worker.draining


@pytest.mark.asyncio
async def test_tick_after_drain_returns_zero() -> None:
    """Post-drain tick must not claim new work."""
    worker, mock = _worker()
    await worker.drain()
    assert await worker.tick() == 0
    mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_each_claim_is_fresh() -> None:
    """Each delivery is claimed individually so no claim waits with an aging lease."""
    id1, id2 = _identity(0), _identity(1)
    worker, mock = _worker([_resolved(id1), _resolved(id2), None])
    count = await worker.tick()
    assert count == 2
    assert mock.await_count == 3


@pytest.mark.asyncio
async def test_drain_mid_tick_stops_further_claims() -> None:
    """Setting draining during tick iteration stops claiming more work."""
    id1 = _identity()

    call_count = 0

    async def drain_after_first() -> object | None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _resolved(id1)
        if call_count == 2:
            worker._draining = True
            return _resolved(_identity(1))
        return None

    worker, _ = _worker()
    worker._claim_and_recover_one = AsyncMock(side_effect=drain_after_first)  # type: ignore[assignment]
    count = await worker.tick()
    assert count == 2
    assert call_count == 2
