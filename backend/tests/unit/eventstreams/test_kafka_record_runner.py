"""Kafka runner orchestration and injected failures using isolated adapters."""

import asyncio
import random
import sqlite3
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
import pytest_asyncio
from aiokafka.errors import (
    AuthenticationFailedError,
    GroupAuthorizationFailedError,
    KafkaConnectionError,
    KafkaTimeoutError,
)

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.config.base import get_settings
from syntara.core.constants import EventSchedulingDefaults, EventStreamLimits
from syntara.eventstreams.adapters import kafka_record_runner as module
from syntara.eventstreams.adapters.kafka_consumer import KafkaCommitUncertainError, KafkaPartitionConsumer
from syntara.eventstreams.adapters.kafka_initial_position import (
    PositionResult,
    PositionStatus,
    RecoveryPolicy,
    RecoveryReplacementRequest,
    RecoveryRequest,
)
from syntara.eventstreams.adapters.kafka_initial_position_service import KafkaInitialPositionService
from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.adapters.kafka_position_store import KafkaPositionError
from syntara.eventstreams.adapters.kafka_record_runner import KafkaRecordRunner, raw_event_size
from syntara.eventstreams.core import inspection_spool
from syntara.eventstreams.core.consumer import MAX_POSITION_OFFSET
from syntara.eventstreams.core.deduplication import DeliveryIdentity
from syntara.eventstreams.core.envelope import RawEvent, RawEventHeader
from syntara.eventstreams.core.handler import BlockedDelivery, ResolvedDelivery, RetryDelivery, SchedulingFailureCode
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.core.processing import HeldRecord, InspectedRecord, RecordProcessingGate, SkippedRecord
from syntara.eventstreams.core.results import EventDecodeFailure
from syntara.eventstreams.core.runtime import PendingInspections, RuntimeState, SubscriptionRuntimeError
from syntara.eventstreams.core.serialization import JsonEventDecoder
from syntara.eventstreams.exceptions import KafkaTransportError
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services import record_processing_service
from syntara.eventstreams.services.admission_service import EventAdmissionService
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.eventstreams.services.record_processing_service import EventRecordProcessingService
from tests.unit.eventstreams.test_connection_provider import connection_context
from tests.unit.eventstreams.test_filtered_record_processing import filtered_context
from tests.unit.eventstreams.test_record_processing_service import processing_context, terminal


@pytest_asyncio.fixture
async def harness(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SimpleNamespace]:
    snapshot = connection_context().snapshot
    settings = get_settings().model_copy(update={"event_drain_timeout_seconds": 0.01, "event_fetch_timeout_ms": 1})
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    client = MagicMock(spec=KafkaPartitionConsumer)
    client.topic, client.group_id = snapshot.configuration.topic, snapshot.configuration.group_id
    client.epoch, client.assignment = 7, frozenset({0, 1})
    client.fetch.return_value = {}
    processing = MagicMock(spec=EventRecordProcessingService)
    processing.local_skip_commit_guard.return_value.__aenter__.return_value = True
    processing.admission_eligible.return_value = True
    processing.process.side_effect = lambda _snapshot, identity, record, **kwargs: (
        terminal(identity) if record is not None or kwargs.get("handoff") else HeldRecord(reason="admission_closed")
    )
    processing.hold_content_failure.return_value = HeldRecord(
        reason="content_inspection_required", permanent_content_error=True
    )

    processing.inspect_only.side_effect = lambda _snapshot, identity, _record: InspectedRecord(identity=identity)

    def inspect_unbuffered(_snapshot, identity, record, **_kwargs: object) -> InspectedRecord | EventDecodeFailure:
        decoded = JsonEventDecoder().decode(record)
        return decoded if isinstance(decoded, EventDecodeFailure) else InspectedRecord(identity=identity)

    processing.inspect_unbuffered.side_effect = inspect_unbuffered
    positions = MagicMock(spec=KafkaInitialPositionService)
    positions.initialize.side_effect = lambda request: PositionResult(
        status=PositionStatus.READY, next_offset=0, assignment_epoch=request.assignment_epoch
    )
    runner = KafkaRecordRunner(
        snapshot,
        client,
        MagicMock(),
        MagicMock(spec=EventExecutionPreparationService),
        MagicMock(spec=EventAdmissionService),
        processing=processing,
        positions=positions,
    )
    await runner.start()
    await runner.on_partitions_assigned(client.assignment, client.epoch)
    for state in runner._partitions.values():
        state.ready = state.eligible = True
    yield SimpleNamespace(
        runner=runner,
        client=client,
        processing=processing,
        positions=positions,
        settings=settings,
    )
    if runner._handoffs or any(state.handoff is not None for state in runner._partitions.values()):
        monkeypatch.setattr(
            runner._processing,
            "process",
            AsyncMock(side_effect=lambda _snapshot, identity, _event, **_kwargs: terminal(identity)),
        )
    await runner.stop()


def event(harness: SimpleNamespace, offset: int, partition: int = 0, value: bytes = b"{}") -> RawEvent:
    snapshot = harness.runner.snapshot
    return RawEvent(
        value=value,
        source_metadata=KafkaSourceMetadata(
            integration_id=snapshot.integration_identity,
            subscription_id=snapshot.subscription_id,
            source_generation=snapshot.source_generation,
            received_at=datetime.now(UTC),
            topic=snapshot.configuration.topic,
            partition=partition,
            offset=str(offset),
        ),
    )


async def test_numeric_gaps_and_unresolved_fetched_positions(harness) -> None:
    runner = harness.runner
    await runner._enqueue({0: [event(harness, 41), event(harness, 44), event(harness, 90)]}, 7)
    state = runner._partitions[0]
    await runner._advance(state)
    await runner._commit_positions((state,))
    harness.client.commit.assert_awaited_once_with({0: 42}, expected_epoch=7)
    await runner._advance(state)
    await runner._commit_positions((state,))
    assert harness.client.commit.await_args_list[-1].args == ({0: 45},)
    assert [runner._identity(item).record.offset for item in state.records] == [90]
    assert harness.processing.process.await_count == 2


async def test_buffered_records_use_shared_gate_without_per_record_eligibility_reads(harness) -> None:
    runner = harness.runner
    gate = MagicMock(spec=RecordProcessingGate)
    gate.admission_open.return_value = True
    gate.resolution_open.return_value = True
    runner._gate = gate
    await runner._enqueue({0: [event(harness, 41), event(harness, 44)]}, 7)
    state = runner._partitions[0]
    await runner._advance(state)
    harness.processing.admission_eligible.return_value = False
    harness.processing.process.side_effect = None
    harness.processing.process.return_value = HeldRecord(reason="admission_closed")
    await runner._advance(state)
    harness.processing.admission_eligible.assert_not_awaited()
    assert harness.processing.process.await_count == 2
    assert state.held.reason == "admission_closed"
    assert state.resolved_next_offset == 42
    await runner._commit_positions((state,))
    harness.client.commit.assert_awaited_once_with({0: 42}, expected_epoch=7)


async def test_delivered_head_recovers_accepted_run_after_current_admission_closes(harness, monkeypatch) -> None:
    _context, processing, admission, _record = processing_context(monkeypatch)
    runner = harness.runner
    current = event(harness, 41)
    admission.lookup_execution.return_value = terminal(runner._identity(current))
    monkeypatch.setattr(processing, "admission_eligible", AsyncMock(return_value=False))
    runner._processing = processing
    await runner._enqueue({0: [current]}, 7)
    await runner._advance(runner._partitions[0])
    admission.lookup_execution.assert_awaited_once_with(runner._identity(current))
    admission.recover_accepted.assert_not_awaited()
    admission.schedule.assert_not_awaited()
    assert runner._partitions[0].resolved_next_offset == 42


async def test_gate_closing_during_fetch_rewinds_every_unqueued_partition(harness) -> None:
    runner = harness.runner
    gate = MagicMock(spec=RecordProcessingGate)
    gate.admission_open.return_value = False
    gate.resolution_open.return_value = True
    runner._gate = gate
    runner._fetching = frozenset({0, 1})
    await runner._enqueue({0: [event(harness, 10)], 1: [event(harness, 20, partition=1)]}, 7)
    harness.client.seek.assert_not_awaited()
    await runner._finish_fetch()
    assert [call.args for call in harness.client.seek.await_args_list] == [(0, 10), (1, 20)]
    assert runner.queued_records == 0
    harness.client.commit.assert_not_awaited()
    gate.admission_open.return_value = True
    await runner._enqueue({0: [event(harness, 10), event(harness, 11)]}, 7)
    await runner._advance(runner._partitions[0])
    assert runner._partitions[0].resolved_next_offset == 11
    assert runner._identity(runner._partitions[0].records[0]).record.offset == 11


async def test_partition_task_drains_queued_heads_without_waiting_for_another_fetch_tick(harness) -> None:
    runner = harness.runner
    await runner._enqueue({0: [event(harness, offset) for offset in (41, 44, 90)]}, 7)
    runner._start_due_tasks()
    task = runner._partitions[0].task
    assert task is not None
    await task
    assert [call.args[1].record.offset for call in harness.processing.process.await_args_list] == [41, 44, 90]
    assert runner._partitions[0].resolved_next_offset == 91
    assert runner.queued_records == 0


async def test_recovery_inspects_queued_content_without_closing_a_healthy_sibling(harness, monkeypatch) -> None:
    _context, processing, admission, _record = processing_context(monkeypatch)
    runner = harness.runner
    runner._processing = processing
    runner._placement_authority = lambda: True
    harness.settings.event_fetch_timeout_ms = 1000
    harness.settings.event_drain_timeout_seconds = 1
    current = event(harness, 10)
    await runner._enqueue({0: [current]}, 7)
    harness.client.fetch.return_value = {0: [current]}
    evidence = await runner.close_and_drain(runner._request(runner._partitions[0]), token=uuid4(), boundary=0)
    assert evidence.quiescent
    assert not evidence.permanent_content_error
    assert runner._partitions[0].fence is not None
    assert runner._active(runner._partitions[1])
    admission.schedule.assert_not_awaited()


@pytest.mark.parametrize("limit", ["records", "bytes", "partition"])
async def test_queue_bounds_rewind_only_the_unqueued_tail(harness, limit) -> None:
    runner = harness.runner
    if limit == "records":
        harness.settings.event_queue_max_records = 2
    elif limit == "bytes":
        harness.settings.event_queue_max_bytes = 4
    else:
        harness.settings.event_partition_max_records = 2
    await runner._enqueue({0: [event(harness, offset) for offset in [41, 44, 90]]}, 7)
    assert runner.queued_records == 2
    assert runner.queued_bytes == 4
    harness.client.seek.assert_awaited_once_with(0, 90, expected_epoch=7)
    harness.client.commit.assert_not_awaited()


async def test_raw_queue_sizing_counts_key_and_duplicate_header_bytes(harness) -> None:
    record = event(harness, 0).model_copy(
        update={
            "key": b"abc",
            "headers": (RawEventHeader(name="a", value=b"b"), RawEventHeader(name="a", value=None)),
        }
    )
    assert raw_event_size(record) == 8 + 2 * EventStreamLimits.HEADER_JSON_OVERHEAD_BYTES


async def test_record_larger_than_queue_is_held_without_scheduling_or_commit(harness) -> None:
    harness.settings.event_queue_max_bytes = 1
    harness.processing.process.side_effect = None
    harness.processing.process.return_value = HeldRecord(reason="delivery_evidence_unavailable")
    await harness.runner._enqueue({0: [event(harness, 41)]}, 7)
    assert harness.runner.queued_bytes == 0
    assert harness.runner.queued_records == 1
    assert harness.runner._partitions[0].pending_failure.failure is None
    await harness.runner._advance(harness.runner._partitions[0])
    assert harness.runner._partitions[0].held.reason == "queue_capacity"
    harness.processing.process.assert_awaited_once_with(
        harness.runner.snapshot, harness.runner._identity(event(harness, 41)), None
    )
    harness.processing.hold_content_failure.assert_not_awaited()
    harness.client.seek.assert_awaited_once_with(0, 41, expected_epoch=7)
    harness.client.commit.assert_not_awaited()


async def test_busy_partition_releases_queue_capacity_and_healthy_partition_continues(harness) -> None:
    runner = harness.runner

    async def process(_snapshot, identity, _record, **_kwargs: object) -> ResolvedDelivery | HeldRecord:
        if identity.record.partition == 0:
            return HeldRecord(reason="claim_busy", retry_at=datetime.now(UTC) + timedelta(seconds=60))
        return terminal(identity)

    harness.processing.process.side_effect = process
    await runner._enqueue({0: [event(harness, 41), event(harness, 44)], 1: [event(harness, 10, 1)]}, 7)
    await runner._advance(runner._partitions[0])
    assert runner.queued_records == 1
    await runner._advance(runner._partitions[1])
    await runner._commit_positions(tuple(runner._partitions.values()))
    harness.client.commit.assert_awaited_once_with({1: 11}, expected_epoch=7)
    harness.client.seek.assert_awaited_once_with(0, 41, expected_epoch=7)


async def test_downstream_concurrency_is_bounded_and_fetch_stays_responsive(harness) -> None:
    runner = harness.runner
    runner._work = asyncio.Semaphore(1)
    entered, release = asyncio.Event(), asyncio.Event()
    active = maximum = 0

    async def process(_snapshot, identity, _record, **_kwargs: object) -> ResolvedDelivery:
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        entered.set()
        await release.wait()
        active -= 1
        return terminal(identity)

    harness.processing.process.side_effect = process
    await runner._enqueue({0: [event(harness, 0)], 1: [event(harness, 0, 1)]}, 7)
    await runner._tick()
    await entered.wait()
    first = runner._partitions[0].task
    await asyncio.wait_for(runner._tick(), timeout=1)
    assert runner._partitions[0].task is first
    assert maximum == 1
    harness.client.fetch.assert_awaited()
    release.set()
    await asyncio.gather(*(state.task for state in runner._partitions.values() if state.task is not None))
    assert maximum == 1


async def test_commit_failure_keeps_only_proven_offsets_for_retry(harness) -> None:
    state = harness.runner._partitions[0]
    await harness.runner._enqueue({0: [event(harness, 41), event(harness, 90)]}, 7)
    await harness.runner._advance(state)
    harness.client.commit.side_effect = KafkaTransportError("unavailable")
    await harness.runner._commit_positions((state,))
    assert state.resolved_next_offset == 42
    harness.client.commit.side_effect = None
    await harness.runner._commit_positions((state,))
    assert state.resolved_next_offset is None
    assert [call.args for call in harness.client.commit.await_args_list] == [({0: 42},), ({0: 42},)]


async def test_stale_epoch_prevents_late_seek_commit_and_new_work(harness) -> None:
    state = harness.runner._partitions[0]
    state.resolved_next_offset = 42
    harness.client.epoch = 8
    await harness.runner._advance(state)
    await harness.runner._enqueue({0: [event(harness, 44)]}, 7)
    await harness.runner._commit_positions((state,))
    harness.processing.process.assert_not_awaited()
    harness.client.seek.assert_not_awaited()
    harness.client.commit.assert_not_awaited()


@pytest.mark.parametrize("lose_ownership", [False, True])
async def test_revocation_drains_only_while_ownership_permits_commit(harness, lose_ownership) -> None:
    runner = harness.runner
    entered, release = asyncio.Event(), asyncio.Event()

    async def process(_snapshot, identity, _record, **_kwargs: object) -> ResolvedDelivery:
        entered.set()
        await release.wait()
        return terminal(identity)

    harness.processing.process.side_effect = process
    await runner._enqueue({0: [event(harness, 41)]}, 7)
    state = runner._partitions[0]
    state.task = asyncio.create_task(runner._advance(state))
    await entered.wait()
    if lose_ownership:
        harness.client.epoch = 8
    release.set()
    await runner.on_partitions_revoked(frozenset({0}), 7)
    assert 0 not in runner._partitions
    if lose_ownership:
        harness.client.commit.assert_not_awaited()
    else:
        harness.client.commit.assert_awaited_once_with({0: 42}, expected_epoch=7)
    harness.client.seek.assert_not_awaited()


async def test_drain_deadline_cancels_unfinished_task_without_committing(harness) -> None:
    entered = asyncio.Event()

    async def process(*_args: object, **_kwargs: object) -> None:
        entered.set()
        await asyncio.Event().wait()

    harness.processing.process.side_effect = process
    runner = harness.runner
    await runner._enqueue({0: [event(harness, 41)]}, 7)
    state = runner._partitions[0]
    state.task = asyncio.create_task(runner._advance(state))
    await entered.wait()
    await asyncio.wait_for(runner.drain(), timeout=1)
    assert state.task.cancelled()
    assert runner._closing
    assert state.resolved_next_offset is None
    harness.client.commit.assert_not_awaited()
    await runner._tick()
    assert harness.processing.process.await_count == 1


async def test_permanent_error_gate_survives_shutdown_without_commit(harness) -> None:
    runner = harness.runner
    harness.processing.process.side_effect = None
    harness.processing.process.return_value = HeldRecord(
        reason="content_inspection_required", permanent_content_error=True
    )
    await runner._enqueue({0: [event(harness, 44)]}, 7)
    await runner._advance(runner._partitions[0])
    assert runner._partitions[0].held.permanent_content_error
    assert runner.queued_records == 0
    await runner.stop()
    harness.client.commit.assert_not_awaited()


async def test_run_always_stops_client_after_fetch_failure(harness) -> None:
    harness.client.fetch.side_effect = RuntimeError("unexpected adapter failure")
    with pytest.raises(RuntimeError, match="unexpected adapter"):
        await harness.runner.run()
    harness.client.stop.assert_awaited_once()


async def test_broker_failure_pauses_and_backs_off_active_partitions(harness) -> None:
    harness.client.fetch.side_effect = KafkaTransportError("unavailable")
    await harness.runner._tick()
    for state in harness.runner._partitions.values():
        assert state.held.reason == "broker_unavailable"
        assert state.held.retry_at > datetime.now(UTC)
        assert state.paused
        assert not state.ready
    await harness.runner._tick()
    assert harness.client.fetch.await_args.args[0] == []
    harness.client.commit.assert_not_awaited()


async def test_broker_retry_backoff_is_partition_local_and_resets_after_success(harness, monkeypatch) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    clock = MagicMock(wraps=datetime)
    clock.now.return_value = now
    monkeypatch.setattr(module, "datetime", clock)
    monkeypatch.setattr(random, "uniform", lambda *_args: 1.0)
    runner = harness.runner
    state = runner._partitions[0]
    for delay in [1, 2, 4, 8, 16, 30, 30, 30]:
        await runner._broker_failed([0], 7)
        assert state.held.retry_at == now + timedelta(seconds=delay)
        assert not state.ready
        assert runner._partitions[1].ready
        assert runner._partitions[1].connection_failures == 0
    state.held = None
    state.ready = state.eligible = True
    await runner._tick()
    assert state.connection_failures == 0
    await runner._broker_failed([0], 7)
    assert state.held.retry_at == now + timedelta(seconds=1)
    harness.client.commit.assert_not_awaited()


async def test_fetch_failure_rechecks_offsets_before_resuming(harness) -> None:
    runner = harness.runner
    await runner._broker_failed([0], harness.client.epoch)
    state = runner._partitions[0]
    state.held = None
    harness.positions.initialize.side_effect = None
    harness.positions.initialize.return_value = PositionResult(
        status=PositionStatus.RECOVERY_GAP, assignment_epoch=state.epoch, reason="out_of_range"
    )
    await runner._advance(state)
    harness.positions.initialize.assert_awaited_once_with(runner._request(state))
    assert state.initialization.status == PositionStatus.RECOVERY_GAP
    assert not state.ready
    assert runner._partitions[1].ready
    harness.client.commit.assert_not_awaited()


async def test_blocked_initialization_does_not_admit_records(harness) -> None:
    for state in harness.runner._partitions.values():
        state.ready = state.eligible = False
    harness.positions.initialize.side_effect = None
    harness.positions.initialize.return_value = PositionResult(
        status=PositionStatus.BLOCKED, assignment_epoch=7, reason="storage_unavailable"
    )
    await harness.runner._advance(harness.runner._partitions[0])
    assert harness.runner._partitions[0].held.reason == "initialization_unresolved"
    await harness.runner._tick()
    assert harness.client.fetch.await_args.args[0] == []
    harness.processing.process.assert_not_awaited()


async def test_startup_failure_closes_partial_client(harness) -> None:
    harness.runner._started = False
    harness.client.start.side_effect = OSError("unavailable")
    with pytest.raises(OSError, match="unavailable"):
        await harness.runner.start()
    harness.client.stop.assert_awaited_once()


async def test_blocked_head_rewinds_after_outstanding_fetch_not_before(harness) -> None:
    runner = harness.runner
    fetch_entered, release_fetch = asyncio.Event(), asyncio.Event()
    trace = []

    async def fetch(*_args: object, **_kwargs: object) -> dict[int, list[RawEvent]]:
        fetch_entered.set()
        await release_fetch.wait()
        trace.append("fetch_settled")
        return {0: [event(harness, 44)]}

    async def process(*_args: object, **_kwargs: object) -> HeldRecord:
        await fetch_entered.wait()
        return HeldRecord(reason="claim_busy", retry_at=datetime.now(UTC) + timedelta(seconds=60))

    async def seek(_partition, offset, **_kwargs: object) -> None:
        trace.append(offset)

    harness.client.fetch.side_effect = fetch
    harness.client.seek.side_effect = seek
    harness.processing.process.side_effect = process
    await runner._enqueue({0: [event(harness, 41)]}, 7)
    tick = asyncio.create_task(runner._tick())
    await fetch_entered.wait()
    await runner._partitions[0].task
    assert runner._partitions[0].rewind_offset == 41
    harness.client.seek.assert_not_awaited()
    release_fetch.set()
    await tick
    assert trace == ["fetch_settled", 41]
    assert runner.queued_records == 0
    assert runner._partitions[0].rewind_offset is None
    harness.client.commit.assert_not_awaited()


async def test_reservation_rewinds_evicted_tail_before_processing_a_later_fetch(harness, monkeypatch) -> None:
    context, processing, admission, head, _logs = filtered_context(monkeypatch, {"expression": "true"})
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    runner = harness.runner
    runner.snapshot, runner._processing = context.snapshot, processing
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(harness.client.assignment, 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    tail = event(harness, 6, 2, b"{}" + b" " * 256)
    later = event(harness, 7, 2)
    harness.settings.event_queue_max_bytes = prepared.encoded_arguments_size() + raw_event_size(head) + 64
    fetching, reserved, finish_start = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def fetch(*_args: object, **_kwargs: object) -> dict[int, list[RawEvent]]:
        fetching.set()
        await reserved.wait()
        return {2: [later]}

    async def lookup(identity: DeliveryIdentity) -> ResolvedDelivery | None:
        if identity != context.identity:
            return terminal(identity)
        await fetching.wait()
        return None

    async def schedule(attempt: PreparedExecution) -> ResolvedDelivery:
        reserved.set()
        await finish_start.wait()
        return terminal(attempt.identity)

    admission.lookup_execution.side_effect = lookup
    admission.schedule.side_effect = schedule
    harness.client.fetch.side_effect = fetch
    await runner._enqueue({2: [head, tail]}, 7)
    try:
        await asyncio.wait_for(runner._tick(), timeout=1)
        assert not state.records
        harness.client.seek.assert_awaited_once_with(2, 6, expected_epoch=7)
    finally:
        finish_start.set()
        if state.task is not None:
            await state.task
    await runner._commit_positions((state,))
    harness.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)
    await runner._enqueue({2: [tail, later]}, 7)
    await runner._run_partition(state)
    await runner._commit_positions((state,))
    assert harness.client.commit.await_args.args == ({2: 8},)
    assert [call.args[0].record.offset for call in admission.lookup_execution.await_args_list] == [5, 6, 7]


@pytest.mark.parametrize("reservation_fits", [False, True], ids=["parked-queue", "evicted-tail"])
async def test_recovery_inspects_delivered_tail_dropped_for_reservation(
    harness, monkeypatch, *, reservation_fits
) -> None:
    context, processing, admission, head, _logs = filtered_context(monkeypatch, {"expression": "true"})
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    runner = harness.runner
    runner.snapshot, runner._processing = context.snapshot, processing
    harness.settings.event_drain_timeout_seconds = 1
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(harness.client.assignment, 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    tail = event(harness, 6, 2, b"invalid" + b" " * 256)
    harness.settings.event_queue_max_bytes = (
        prepared.encoded_arguments_size() + raw_event_size(head) + 64
        if reservation_fits
        else raw_event_size(head) + raw_event_size(tail)
    )
    await runner._enqueue({2: [head, tail]}, 7)
    await runner._advance(state)
    assert not state.records
    assert max(state.inspections.offsets) == 6
    admission.recover_accepted.return_value = terminal(runner._identity(head))
    harness.client.fetch.return_value = {2: [tail]}
    evidence = await runner.close_and_drain(runner._request(state), token=uuid4(), boundary=8)
    assert evidence.permanent_content_error
    harness.client.fetch.assert_awaited_once()
    harness.client.commit.assert_not_awaited()


async def test_recovery_fence_waits_for_conflicting_fetch_before_reporting_quiescence(harness) -> None:
    runner = harness.runner
    harness.settings.event_drain_timeout_seconds = 1
    fetch_entered, release_fetch = asyncio.Event(), asyncio.Event()

    async def fetch(*_args: object, **_kwargs: object) -> dict[int, list[RawEvent]]:
        fetch_entered.set()
        await release_fetch.wait()
        return {0: [event(harness, 44)]}

    harness.client.fetch.side_effect = fetch
    tick = asyncio.create_task(runner._tick())
    await fetch_entered.wait()
    state = runner._partitions[0]
    token = uuid4()
    recovery = asyncio.create_task(runner.close_and_drain(runner._request(state), token=token, boundary=50))
    await asyncio.sleep(0)
    assert not recovery.done()
    release_fetch.set()
    await tick
    evidence = await recovery
    assert evidence.quiescent
    assert not evidence.retained_evidence_complete
    assert state.fence == token
    assert not state.records
    assert not evidence.permanent_content_error
    assert not state.inspections.offsets
    harness.client.seek.assert_awaited_once_with(0, 44, expected_epoch=7)
    assert await runner.resume_after_recovery(runner._request(state), token=token)
    harness.client.commit.assert_not_awaited()


async def test_unordered_fetch_stops_without_skipping_the_unresolved_tail(harness) -> None:
    harness.client.fetch.return_value = {0: [event(harness, offset) for offset in [41, 44, 43, 90]]}
    with pytest.raises(ValueError, match="out of order"):
        await harness.runner.run()
    harness.client.stop.assert_awaited_once()
    harness.client.commit.assert_not_awaited()


async def test_failed_overflow_seek_reloads_committed_progress_before_later_records(harness) -> None:
    runner = harness.runner
    harness.settings.event_partition_max_records = 1
    cursor = committed = 41
    fail_seek = True
    processed = []
    trace = []

    async def fetch(partitions, *_args: object, **_kwargs: object) -> dict[int, list[RawEvent]]:
        nonlocal cursor
        if 0 not in partitions:
            return {}
        offsets = [offset for offset in [41, 44, 90] if offset >= cursor]
        cursor = 91
        return {0: [event(harness, offset) for offset in offsets]}

    async def seek(_partition, offset, **_kwargs: object) -> None:
        nonlocal cursor, fail_seek
        if fail_seek:
            fail_seek = False
            trace.append("failed_seek")
            msg = "seek_unavailable"
            raise KafkaTransportError(msg)
        cursor = offset

    async def initialize(request) -> PositionResult:
        nonlocal cursor
        cursor = committed
        trace.append("initialize")
        return PositionResult(
            status=PositionStatus.READY, next_offset=cursor, assignment_epoch=request.assignment_epoch
        )

    async def process(_snapshot, identity, _event, **_kwargs: object) -> ResolvedDelivery:
        trace.append(identity.record.offset)
        processed.append(identity.record.offset)
        return terminal(identity)

    async def commit(offsets, **_kwargs: object) -> None:
        nonlocal committed
        committed = offsets.get(0, committed)
        assert committed <= 44 or 44 in processed
        assert committed <= 90 or 90 in processed

    harness.client.fetch.side_effect = fetch
    harness.client.seek.side_effect = seek
    harness.client.commit.side_effect = commit
    harness.positions.initialize.side_effect = initialize
    harness.processing.process.side_effect = process
    for _ in range(12):
        await runner._tick()
        await asyncio.gather(*(state.task for state in runner._partitions.values() if state.task is not None))
    assert processed == [41, 44, 90]
    assert trace[:2] == ["failed_seek", "initialize"]
    assert committed == 91


async def test_admission_closing_during_empty_queue_fetch_rewinds_before_resume(harness) -> None:
    runner = harness.runner
    cursor = 44
    first_fetch = True
    processed = []

    async def fetch(partitions, *_args: object, **_kwargs: object) -> dict[int, list[RawEvent]]:
        nonlocal cursor, first_fetch
        if 0 not in partitions:
            return {}
        if first_fetch:
            first_fetch = False
            await asyncio.sleep(0)  # Eligibility can close while an earlier fetch is still in progress.
        offset = cursor
        cursor = 90 if cursor == 44 else 91
        return {0: [event(harness, offset)]} if offset < 91 else {}

    async def seek(_partition, offset, **_kwargs: object) -> None:
        nonlocal cursor
        cursor = offset

    async def process(_snapshot, identity, _event, **_kwargs: object) -> ResolvedDelivery:
        processed.append(identity.record.offset)
        return terminal(identity)

    harness.processing.admission_eligible.return_value = False
    harness.client.fetch.side_effect = fetch
    harness.client.seek.side_effect = seek
    harness.processing.process.side_effect = process
    await runner._tick()
    await asyncio.gather(*(state.task for state in runner._partitions.values() if state.task is not None))
    harness.client.seek.assert_awaited_once_with(0, 44, expected_epoch=7)
    harness.processing.process.assert_not_awaited()
    harness.processing.admission_eligible.return_value = True
    for state in runner._partitions.values():
        state.held = None
    for _ in range(6):
        await runner._tick()
        await asyncio.gather(*(state.task for state in runner._partitions.values() if state.task is not None))
    assert processed == [44, 90]
    assert harness.client.commit.await_args_list[-1].args == ({0: 91},)


@pytest.mark.parametrize("replacement", [False, True])
async def test_completed_recovery_service_accepts_real_request_types(harness, replacement) -> None:
    runner = harness.runner
    state = runner._partitions[0]
    fields = {
        **runner._request(state).model_dump(),
        "expected_recovery_revision": 0,
        "policy": RecoveryPolicy.CURRENT_END,
        "reason": "administrator_recovery",
    }
    request = (
        RecoveryReplacementRequest(**fields, expected_pending_boundary=50) if replacement else RecoveryRequest(**fields)
    )
    service = KafkaInitialPositionService(MagicMock(), harness.client, runner)
    token = uuid4()
    await service._drain(request, token, 50)
    assert await runner.is_fenced(request, token=token)
    assert await runner.resume_after_recovery(request, token=token)
    assert state.fence is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_id", uuid4()),
        ("source_generation", 2),
        ("configuration_revision", 2),
        ("partition", 2),
        ("assignment_epoch", 8),
    ],
)
async def test_recovery_fence_rejects_changed_request_coordinates(harness, field, value) -> None:
    runner = harness.runner
    state = runner._partitions[0]
    request = runner._request(state)
    if field in {"source_generation", "configuration_revision"}:
        value = getattr(request, field) + 1
    changed = request.model_copy(update={field: value})
    token = uuid4()
    evidence = await runner.close_and_drain(changed, token=token, boundary=50)
    assert not evidence.quiescent
    assert not await runner.is_fenced(changed, token=token)
    assert state.fence is None


def skip_invalid_content(snapshot, identity, failure, **_kwargs: object) -> SkippedRecord:
    return SkippedRecord(
        identity=identity,
        configuration_revision=snapshot.configuration_revision,
        outcome="invalid_content",
        error_code=failure.code,
    )


async def test_known_invalid_unbufferable_content_skips_under_offset_checks(harness) -> None:
    runner = harness.runner
    harness.processing.hold_content_failure.side_effect = skip_invalid_content
    record = event(harness, 41, value=b"x" * (harness.settings.event_queue_max_bytes + 1))
    await runner._enqueue({0: [record]}, 7)
    state = runner._partitions[0]
    assert runner.queued_bytes == 0
    assert runner.queued_records == 1  # Only the identity and failure code are staged.
    harness.processing.hold_content_failure.assert_not_awaited()
    await runner._advance(state)
    assert runner.queued_records == 0
    harness.processing.inspect_unbuffered.assert_called_once_with(runner.snapshot, runner._identity(record), record)
    assert state.pending_failure is None
    assert state.held is None
    assert state.resolved_next_offset == 42
    await runner._commit_positions((state,))
    harness.client.commit.assert_awaited_once_with({0: 42}, expected_epoch=7)
    evidence = await runner.close_and_drain(runner._request(state), token=uuid4(), boundary=91)
    assert evidence.quiescent
    assert not evidence.permanent_content_error
    await runner.stop()
    harness.processing.process.assert_not_awaited()


async def test_uninspected_oversized_content_blocks_recovery_when_dependencies_are_unavailable(harness) -> None:
    runner = harness.runner
    harness.processing.hold_content_failure.return_value = HeldRecord(
        reason="dependency_unavailable", retry_at=datetime.now(UTC)
    )
    harness.processing.inspect_only.side_effect = None
    harness.processing.inspect_only.return_value = HeldRecord(reason="dependency_unavailable")
    harness.processing.process.side_effect = None
    harness.processing.process.return_value = HeldRecord(reason="delivery_evidence_unavailable")
    await runner._enqueue({0: [event(harness, 41, value=b"x" * (harness.settings.event_queue_max_bytes + 1))]}, 7)
    state = runner._partitions[0]
    await runner._advance(state)
    assert state.pending_failure is not None
    assert state.inspections.first == 41
    assert not state.held.permanent_content_error
    request = RecoveryRequest(
        **runner._request(state).model_dump(),
        expected_recovery_revision=0,
        policy=RecoveryPolicy.CURRENT_END,
        reason="administrator_recovery",
    )
    service = KafkaInitialPositionService(MagicMock(), harness.client, runner)
    token = uuid4()
    with pytest.raises(KafkaPositionError, match="permanent_content_error"):
        await service._drain(request, token, 91)
    assert not await runner.resume_after_recovery(request, token=token)
    harness.client.commit.assert_not_awaited()


async def test_valid_unbufferable_content_does_not_create_a_false_permanent_gate(harness) -> None:
    harness.settings.event_queue_max_bytes = 1
    harness.processing.process.side_effect = None
    harness.processing.process.return_value = HeldRecord(reason="admission_closed")
    runner = harness.runner
    await runner._enqueue({0: [event(harness, 41)]}, 7)
    state = runner._partitions[0]
    evidence = await runner.close_and_drain(runner._request(state), token=uuid4(), boundary=91)
    assert not evidence.quiescent  # Valid content still lacks terminal delivery evidence.
    assert not evidence.permanent_content_error
    assert runner.queued_records == 0
    assert runner.queued_bytes == 0
    harness.processing.inspect_unbuffered.assert_called_once()


async def test_oversized_tail_waits_for_earlier_record_resolution(harness) -> None:
    runner = harness.runner
    harness.processing.hold_content_failure.side_effect = skip_invalid_content
    oversized = event(harness, 44, value=b"x" * (harness.settings.event_queue_max_bytes + 1))
    await runner._enqueue({0: [event(harness, 41), oversized, event(harness, 90)]}, 7)
    state = runner._partitions[0]
    assert state.pending_failure is None
    assert state.inspections.offsets
    assert runner.queued_records == 1
    await runner._advance(state)
    assert state.resolved_next_offset == 42
    harness.processing.hold_content_failure.assert_not_awaited()
    await runner._enqueue({0: [oversized, event(harness, 90)]}, 7)
    await runner._advance(state)
    assert state.held is None
    assert state.resolved_next_offset == 45
    assert state.inspections.first == 90
    assert harness.processing.process.await_count == 1
    harness.processing.inspect_unbuffered.assert_called_once()
    await runner._commit_positions((state,))
    harness.client.commit.assert_awaited_once_with({0: 45}, expected_epoch=7)


async def test_oversized_terminal_redelivery_resolves_without_retaining_payload(harness) -> None:
    runner = harness.runner
    record = event(harness, 41, value=b"x" * (harness.settings.event_queue_max_bytes + 1))
    identity = runner._identity(record)
    harness.processing.hold_content_failure.return_value = terminal(identity)
    await runner._enqueue({0: [record]}, 7)
    state = runner._partitions[0]
    await runner._advance(state)
    assert state.pending_failure is None
    assert state.held is None
    assert state.resolved_next_offset == 42
    assert runner.queued_records == runner.queued_bytes == 0
    assert harness.client.seek.await_args_list[-1].args == (0, 42)
    await runner._commit_positions((state,))
    harness.client.commit.assert_awaited_once_with({0: 42}, expected_epoch=7)


@pytest.mark.parametrize("failure", ["mismatched", "exhausted"])
async def test_oversized_terminal_evidence_must_match_a_committable_identity(harness, failure) -> None:
    runner = harness.runner
    offset = MAX_POSITION_OFFSET if failure == "exhausted" else 41
    record = event(harness, offset, value=b"x" * (harness.settings.event_queue_max_bytes + 1))
    identity = runner._identity(event(harness, 44) if failure == "mismatched" else record)
    harness.processing.hold_content_failure.return_value = terminal(identity)
    await runner._enqueue({0: [record]}, 7)
    state = runner._partitions[0]
    await runner._advance(state)
    await runner._commit_positions((state,))
    assert state.pending_failure is not None
    assert state.held is not None
    assert state.resolved_next_offset is None
    harness.client.commit.assert_not_awaited()


async def test_terminal_redelivery_exceeding_only_queue_capacity_uses_existing_evidence(harness) -> None:
    harness.settings.event_queue_max_bytes = 1
    runner = harness.runner
    record = event(harness, 41)
    harness.processing.process.side_effect = None
    harness.processing.process.return_value = terminal(runner._identity(record))
    await runner._enqueue({0: [record]}, 7)
    state = runner._partitions[0]
    await runner._advance(state)
    assert state.pending_failure is None
    assert not state.inspections.offsets
    assert state.resolved_next_offset == 42
    await runner._commit_positions((state,))
    harness.processing.process.assert_awaited_once_with(runner.snapshot, runner._identity(record), None)
    harness.processing.hold_content_failure.assert_not_awaited()
    harness.client.commit.assert_awaited_once_with({0: 42}, expected_epoch=7)


async def test_cursor_reload_replays_prefix_before_a_staged_oversized_record(harness) -> None:
    runner, client = harness.runner, harness.client
    state = runner._partitions[0]
    harness.settings.event_queue_max_bytes = 64
    oversized = event(harness, 41, value=b"{}" + b" " * 128)
    client.seek.side_effect = KafkaTransportError("seek unavailable")
    await runner._enqueue({0: [oversized]}, 7)
    assert state.reload_required
    assert state.pending_failure is not None
    assert state.inspections.requires_delivery(41)

    client.seek.side_effect = None
    harness.positions.initialize.side_effect = None
    harness.positions.initialize.return_value = PositionResult(
        status=PositionStatus.READY, next_offset=4, assignment_epoch=7
    )
    await runner._advance(state)
    assert state.pending_failure is None
    assert state.inspections.requires_delivery(41)
    harness.processing.process.assert_not_awaited()
    await runner._enqueue({0: [event(harness, 4)]}, 7)
    await runner._advance(state)
    await runner._commit_positions((state,))
    client.commit.assert_awaited_once_with({0: 5}, expected_epoch=7)


async def test_completion_behind_recovery_fence_cannot_restore_old_commit_position(harness) -> None:
    runner = harness.runner
    entered, release = asyncio.Event(), asyncio.Event()

    async def process(_snapshot, identity, _record, **_kwargs: object) -> ResolvedDelivery:
        entered.set()
        await release.wait()
        return terminal(identity)

    harness.processing.process.side_effect = process
    await runner._enqueue({0: [event(harness, 41)]}, 7)
    state = runner._partitions[0]
    state.task = asyncio.create_task(runner._advance(state))
    await entered.wait()
    token = uuid4()
    request = runner._request(state)
    drain = asyncio.create_task(runner.close_and_drain(request, token=token, boundary=91))
    await asyncio.sleep(0)
    release.set()
    evidence = await drain
    assert evidence.quiescent
    assert state.resolved_next_offset is None
    assert await runner.resume_after_recovery(request, token=token)
    await runner._commit_positions((state,))
    harness.client.commit.assert_not_awaited()
    harness.client.seek.assert_not_awaited()


async def test_staged_content_lookup_respects_shutdown_deadline(harness) -> None:
    runner = harness.runner
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def persist(*_args: object) -> HeldRecord:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return HeldRecord(reason="dependency_unavailable")

    harness.settings.event_queue_max_bytes = 1
    harness.processing.process.side_effect = persist
    await runner._enqueue({0: [event(harness, 41)]}, 7)
    async with asyncio.timeout(1):
        await runner.stop()
    assert entered.is_set()
    assert cancelled.is_set()
    assert runner._partitions[0].pending_failure is not None
    harness.client.commit.assert_not_awaited()
    harness.client.stop.assert_awaited_once()


async def test_timed_out_client_stop_can_be_retried(harness) -> None:
    runner = harness.runner

    async def stop() -> None:
        await asyncio.Event().wait()

    harness.client.stop.side_effect = stop
    with pytest.raises(TimeoutError):
        await runner.stop()
    assert not runner._stopped
    assert runner._closing
    harness.client.stop.side_effect = None
    await runner.stop()
    assert runner._stopped
    assert harness.client.stop.await_count == 2
    await runner.stop()
    assert harness.client.stop.await_count == 2


@pytest.mark.parametrize("permanent", [False, True], ids=["retry-inspection", "recover-existing-execution"])
async def test_fenced_inspection_retries_without_admitting_work(harness, permanent) -> None:
    runner = harness.runner
    record = event(harness, 41)
    await runner._enqueue({0: [record]}, 7)
    harness.client.fetch.return_value = {0: [record]}
    identity = runner._identity(record)
    harness.processing.inspect_only.side_effect = [
        HeldRecord(
            reason="activity_log_unavailable" if permanent else "dependency_unavailable",
            permanent_content_error=permanent,
        ),
        terminal(identity) if permanent else InspectedRecord(identity=identity),
    ]
    state = runner._partitions[0]
    token = uuid4()
    request = runner._request(state)
    first = await runner.close_and_drain(request, token=token, boundary=91)
    assert first.quiescent
    assert first.permanent_content_error
    assert set(state.inspections.offsets) == {41}
    second = await runner.close_and_drain(request, token=token, boundary=91)
    assert second.quiescent
    assert not second.permanent_content_error
    assert await runner.resume_after_recovery(request, token=token)
    harness.processing.process.assert_not_awaited()
    harness.client.commit.assert_not_awaited()


async def test_fenced_inspection_tolerates_numeric_gaps_without_commit_candidates(harness) -> None:
    runner = harness.runner
    records = [event(harness, offset) for offset in [41, 44, 90]]
    await runner._enqueue({0: records}, 7)
    harness.client.fetch.side_effect = [{0: [record]} for record in records]
    state = runner._partitions[0]
    result = await runner.close_and_drain(runner._request(state), token=uuid4(), boundary=91)
    assert result.quiescent
    assert not result.permanent_content_error
    assert [call.args[1] for call in harness.client.seek.await_args_list] == [41, 44, 90]
    assert [call.args[1].record.offset for call in harness.processing.inspect_only.await_args_list] == [41, 44, 90]
    assert state.resolved_next_offset is None
    assert runner.queued_records == runner.queued_bytes == 0
    harness.processing.process.assert_not_awaited()
    harness.client.commit.assert_not_awaited()


@pytest.mark.parametrize("boundary", [4, 5])
async def test_recovery_before_a_missing_offset_resumes_the_safe_prefix(harness, boundary) -> None:
    runner, client = harness.runner, harness.client
    state = runner._partitions[0]
    later = event(harness, 6)
    await runner._enqueue({0: [event(harness, 5), later]}, 7)
    client.fetch.return_value = {0: [later]}
    request = RecoveryRequest(
        **runner._request(state).model_dump(),
        expected_recovery_revision=0,
        policy=RecoveryPolicy.RETAINED_BEGINNING,
        reason="administrator_recovery",
        acknowledge_duplicate_risk=True,
    )
    service = KafkaInitialPositionService(MagicMock(), client, runner)
    incomplete = uuid4()
    with pytest.raises(KafkaPositionError, match="permanent_content_error"):
        await service._drain(request, incomplete, 6)
    assert not await runner.resume_after_recovery(request, token=incomplete)

    client.fetch.reset_mock()
    token = uuid4()
    await service._drain(request, token, boundary)
    client.fetch.assert_not_awaited()
    harness.positions.initialize.side_effect = None
    harness.positions.initialize.return_value = PositionResult(
        status=PositionStatus.READY, next_offset=boundary, assignment_epoch=7
    )
    assert await runner.resume_after_recovery(request, token=token)
    assert set(state.inspections.offsets) == {5, 6}
    if boundary == 4:
        await runner._enqueue({0: [event(harness, 4)]}, 7)
        await runner._advance(state)
    await runner._enqueue({0: [later]}, 7)
    await runner._advance(state)
    await runner._commit_positions((state,))
    assert state.inspections.first == 5
    if boundary == 4:
        client.commit.assert_awaited_once_with({0: 5}, expected_epoch=7)
    else:
        client.commit.assert_not_awaited()


async def test_verified_recovery_drops_a_rewind_left_by_an_in_flight_fetch(harness) -> None:
    runner, client = harness.runner, harness.client
    client.assignment = frozenset({0})
    state = runner._partitions[0]
    harness.settings.event_drain_timeout_seconds = 1
    entered, release = asyncio.Event(), asyncio.Event()
    cursor = 8

    async def seek(partition, offset, **_kwargs: object) -> None:
        nonlocal cursor
        assert partition == 0
        cursor = offset

    async def fetch(partitions, *_args: object, **_kwargs: object) -> dict[int, list[RawEvent]]:
        if not partitions:
            return {}
        if not entered.is_set():
            entered.set()
            await release.wait()
            return {0: [event(harness, 8)]}
        if cursor <= 8:
            return {0: [event(harness, 4 if cursor <= 4 else 8)]}
        return {}

    client.seek.side_effect = seek
    client.fetch.side_effect = fetch
    request = RecoveryRequest(
        **runner._request(state).model_dump(),
        expected_recovery_revision=0,
        policy=RecoveryPolicy.RETAINED_BEGINNING,
        reason="administrator_recovery",
        acknowledge_duplicate_risk=True,
    )
    positions = KafkaInitialPositionService(MagicMock(), client, runner)
    token = uuid4()
    tick = asyncio.create_task(runner._tick())
    await asyncio.wait_for(entered.wait(), timeout=1)
    draining = asyncio.create_task(positions._drain(request, token, 4))
    try:
        await asyncio.sleep(0)
        assert state.fence == token
    finally:
        release.set()
        await tick
        await draining
    assert state.rewind_offset == 8
    assert state.inspections.first == 8

    async def initialize(_request) -> PositionResult:
        await client.seek(0, 4, expected_epoch=7)
        return PositionResult(status=PositionStatus.READY, next_offset=4, assignment_epoch=7)

    harness.positions.initialize.side_effect = initialize
    state.reload_required = True
    assert await runner.resume_after_recovery(request, token=token)
    assert state.rewind_offset is None
    assert not state.reload_required
    assert state.inspections.first == 8
    await runner._tick()
    await runner._advance(state)
    await runner._commit_positions((state,))
    client.seek.assert_awaited_once_with(0, 4, expected_epoch=7)
    client.commit.assert_awaited_once_with({0: 5}, expected_epoch=7)


async def test_overlapping_stop_calls_share_successful_client_shutdown(harness) -> None:
    runner = harness.runner
    harness.settings.event_drain_timeout_seconds = 1
    entered, release = asyncio.Event(), asyncio.Event()

    async def close() -> None:
        entered.set()
        await release.wait()

    harness.client.stop.side_effect = close
    first = asyncio.create_task(runner.stop())
    await entered.wait()
    second = asyncio.create_task(runner.stop())
    await asyncio.sleep(0)
    assert not runner._stopped
    assert harness.client.stop.await_count == 1
    release.set()
    await asyncio.gather(first, second)
    assert runner._stopped
    assert harness.client.stop.await_count == 1


async def test_public_status_waits_for_first_assignment_before_reporting_active(
    harness: SimpleNamespace,
) -> None:
    snapshot = harness.runner.snapshot
    client = MagicMock(spec=KafkaPartitionConsumer)
    client.topic, client.group_id = snapshot.configuration.topic, snapshot.configuration.group_id
    client.epoch, client.assignment = 0, frozenset()
    client.fetch.return_value = {}
    runner: KafkaRecordRunner = KafkaRecordRunner(
        snapshot,
        client,
        MagicMock(),
        MagicMock(spec=EventExecutionPreparationService),
        MagicMock(spec=EventAdmissionService),
        processing=harness.processing,
        positions=harness.positions,
    )

    try:
        await runner.start()
        startup_status = runner.status
        assert startup_status.state == RuntimeState.STARTING
        harness.positions.initialize.assert_not_awaited()
        await runner.on_partitions_assigned(frozenset(), client.epoch)
        empty_assignment_status = runner.status
        assert empty_assignment_status.state == RuntimeState.ACTIVE
        harness.positions.initialize.assert_not_awaited()
        client.epoch, client.assignment = 1, frozenset({0})
        await runner.on_partitions_assigned(client.assignment, client.epoch)
        assigned_status = runner.status
        assert assigned_status.state == RuntimeState.STARTING
        await runner._advance(runner._partitions[0])
        harness.positions.initialize.assert_awaited_once()
        ready_status = runner.status
        assert ready_status.state == RuntimeState.ACTIVE
    finally:
        await runner.stop()


async def test_assignment_status_waits_after_revocation_and_ignores_stale_callbacks(harness):
    runner, client = harness.runner, harness.client
    assert runner.status.state == RuntimeState.ACTIVE
    await runner.on_partitions_revoked(client.assignment, client.epoch)
    assert runner.status.state == RuntimeState.STARTING
    client.epoch, client.assignment = 8, frozenset()
    await runner.on_partitions_assigned(client.assignment, client.epoch)
    assert runner.status.state == RuntimeState.ACTIVE
    await runner.on_partitions_assigned(frozenset(), 7)
    await runner.on_partitions_revoked(frozenset(), 7)
    assert runner.status.state == RuntimeState.ACTIVE


@pytest.mark.parametrize(
    ("position_status", "reason", "observed"),
    [
        (PositionStatus.RECOVERY_GAP, "missing_commit", "recovery_gap"),
        (PositionStatus.RECOVERY_GAP, "Storage Unavailable", "recovery_gap"),
        (PositionStatus.BLOCKED, "storage_unavailable", "storage_unavailable"),
        (PositionStatus.BLOCKED, "a" * 100, "a" * 100),
        (PositionStatus.BLOCKED, None, "initialization_unresolved"),
        (PositionStatus.BLOCKED, "", "initialization_unresolved"),
        (PositionStatus.BLOCKED, "Storage Unavailable", "initialization_unresolved"),
        (PositionStatus.BLOCKED, "storage-unavailable", "initialization_unresolved"),
        (PositionStatus.BLOCKED, "storage_unavailable\n", "initialization_unresolved"),
        (PositionStatus.BLOCKED, "échec", "initialization_unresolved"),
        (PositionStatus.BLOCKED, "a" * 101, "initialization_unresolved"),
    ],
)
async def test_public_status_exposes_initialization_holds(harness, position_status, reason, observed):
    runner = harness.runner
    for state in runner._partitions.values():
        state.ready = state.eligible = False
    assert runner.status.state == RuntimeState.STARTING
    harness.positions.initialize.side_effect = None
    harness.positions.initialize.return_value = PositionResult(
        status=position_status, assignment_epoch=7, reason=reason
    )
    await runner._advance(runner._partitions[0])
    assert runner.status.state == RuntimeState.BLOCKED
    assert runner.status.reason == observed
    assert not runner.status.permanent_content_error
    harness.client.commit.assert_not_awaited()
    harness.processing.process.assert_not_awaited()


async def test_public_status_prioritizes_permanent_content_and_reports_teardown(harness):
    runner = harness.runner
    runner._partitions[0].held = HeldRecord(reason="broker_unavailable")
    runner._partitions[1].held = HeldRecord(reason="content_inspection_required", permanent_content_error=True)
    observed = runner.status
    assert observed.state == RuntimeState.BLOCKED
    assert observed.reason == "content_inspection_required"
    assert observed.permanent_content_error
    await runner.drain()
    assert runner.status.state == RuntimeState.DRAINING
    await runner.stop()
    assert runner.status.state == RuntimeState.STOPPED
    assert observed.permanent_content_error  # Prior immutable observations cannot be cleared by stop.
    harness.client.commit.assert_not_awaited()


@pytest.mark.parametrize(
    ("cause", "transient"),
    [
        (AuthenticationFailedError("PRIVATE"), False),
        (KafkaConnectionError("PRIVATE"), True),
        (KafkaTimeoutError("PRIVATE"), True),
        (None, False),
    ],
)
async def test_startup_errors_leave_adapter_with_safe_retry_classification(harness, cause, transient):
    harness.runner._started = False
    failure = KafkaTransportError("PRIVATE credential contents")
    failure.__cause__ = cause
    harness.client.start.side_effect = failure
    with pytest.raises(SubscriptionRuntimeError) as caught:
        await harness.runner.start()
    assert caught.value.transient is transient
    assert str(caught.value) == "connection_unavailable"
    harness.client.stop.assert_awaited_once()


async def test_supervised_startup_keeps_admission_closed_until_explicit_authorization(harness):
    runner = harness.runner
    permitted = [True]
    runner._started = False
    runner.bind_placement(lambda: permitted[0])
    await runner.start()
    await runner._enqueue({0: [event(harness, 41)]}, 7)
    assert runner.queued_records == 0
    assert runner.open_admission()
    await runner._rewind(runner._partitions[0])
    await runner._enqueue({0: [event(harness, 41)]}, 7)
    assert runner.queued_records == 1
    permitted[0] = False
    await runner._advance(runner._partitions[0])
    harness.processing.process.assert_not_awaited()
    assert not runner.open_admission()


async def test_placement_loss_preserves_admitted_handoff_and_assignment_checked_drain_commit(harness):
    runner = harness.runner
    permitted = [True]
    runner._started = False
    runner.bind_placement(lambda: permitted[0])
    await runner.start()
    assert runner.open_admission()
    entered, release = asyncio.Event(), asyncio.Event()
    admitted = []

    async def complete(_snapshot, identity, _record, *, admission_guard, **_kwargs: object) -> ResolvedDelivery:
        assert admission_guard()
        admitted.append(identity)
        entered.set()
        await release.wait()
        return terminal(identity)

    harness.processing.process.side_effect = complete
    await runner._enqueue({0: [event(harness, 41)]}, 7)
    state = runner._partitions[0]
    state.task = asyncio.create_task(runner._advance(state))
    await entered.wait()
    permitted[0] = False
    closing = asyncio.create_task(runner.close_admission())
    release.set()
    await asyncio.gather(closing, state.task)
    assert admitted == [runner._identity(event(harness, 41))]
    harness.client.commit.assert_awaited_with({0: 42}, expected_epoch=7)
    harness.client.pause.assert_awaited()
    assert not runner._accepting_work()
    assert runner._drain_deadline is not None


@pytest.mark.parametrize("reason", ["assignment", "deadline"])
async def test_placement_loss_never_bypasses_assignment_or_drain_deadline(harness, monkeypatch, reason):
    runner = harness.runner
    state = runner._partitions[0]
    state.resolved_next_offset = 42
    monkeypatch.setattr(runner, "_placement_authority", lambda: False)
    if reason == "assignment":
        harness.client.epoch += 1
    else:
        runner._drain_deadline = asyncio.get_running_loop().time() - 1
    await runner._commit_positions((state,))
    harness.client.commit.assert_not_awaited()
    assert state.resolved_next_offset == 42


async def test_offset_gap_dispatches_automatic_recovery_without_a_manual_request(harness, monkeypatch) -> None:
    runner = harness.runner
    state = runner._partitions[0]
    state.ready = False
    state.initialization = PositionResult(
        status=PositionStatus.RECOVERY_GAP, assignment_epoch=state.epoch, reason="missing_commit"
    )
    observations = []

    async def recover(value) -> PositionResult:
        async def shielded_operation() -> PositionResult:
            evidence = await runner.close_and_drain(value, token=uuid4(), boundary=0)
            observations.append(evidence)
            return PositionResult(status=PositionStatus.READY, next_offset=0, assignment_epoch=state.epoch)

        return await asyncio.shield(asyncio.create_task(shielded_operation()))

    harness.positions.recover_automatically.side_effect = recover
    resume = AsyncMock(return_value=True)
    monkeypatch.setattr(runner, "resume_after_recovery", resume)
    runner._poll_control(state)
    assert state.control_task is not None
    await asyncio.wait_for(state.control_task, timeout=1)
    assert observations[0].quiescent
    resume.assert_awaited_once()
    assert state.initialization.status == PositionStatus.READY
    harness.positions.recover.assert_not_awaited()
    assert harness.client.commit.await_count == 0


async def test_automatic_recovery_cannot_dispatch_after_assignment_loss(harness) -> None:
    runner = harness.runner
    state = runner._partitions[0]
    state.initialization = PositionResult(
        status=PositionStatus.RECOVERY_GAP, assignment_epoch=state.epoch, reason="missing_commit"
    )
    harness.client.epoch += 1
    await runner._recover_requested(state)
    harness.positions.recover_automatically.assert_not_awaited()


@pytest.mark.parametrize("uninspected", [False, True])
async def test_revocation_preserves_content_gate_after_partition_state_is_removed(
    harness, *, uninspected: bool
) -> None:
    runner = harness.runner
    state = runner._partitions[0]
    if uninspected:
        state.inspections.remember(41)
    else:
        state.held = HeldRecord(reason="content_inspection_required", permanent_content_error=True)
    await runner.on_partitions_revoked(frozenset({0}), state.epoch)
    assert 0 not in runner._partitions
    if uninspected:
        assert runner._retained_inspection[0].first == 41
    else:
        assert runner.status.state == RuntimeState.BLOCKED
        assert runner.status.reason == "content_inspection_required"
        assert runner.status.permanent_content_error
    assert runner._accepting_work()  # The healthy sibling remains independent.
    await runner._enqueue({1: [event(harness, 41, partition=1)]}, harness.client.epoch)
    await runner._advance(runner._partitions[1])
    assert runner._partitions[1].resolved_next_offset == 42
    await runner.on_partitions_assigned(frozenset({0}), harness.client.epoch)
    if uninspected:
        assert runner._crosses_inspection(runner._partitions[0], 42)
    else:
        retained = runner._partitions[0].held
        assert retained is not None
        assert retained.reason == "content_inspection_required"
        assert retained.permanent_content_error
    await runner.stop()
    assert runner.status.permanent_content_error is not uninspected


@pytest.mark.parametrize("checkpoint", [41, 42], ids=["record-replayed", "already-committed-by-group"])
async def test_transient_hold_keeps_replay_eligible_after_reassignment(harness, checkpoint) -> None:
    runner = harness.runner
    record = event(harness, 41)
    await runner._enqueue({0: [record]}, 7)
    harness.processing.process.side_effect = [
        HeldRecord(reason="temporal_unavailable", retry_at=datetime.now(UTC) + timedelta(seconds=30)),
        terminal(runner._identity(record)),
    ]
    await runner._advance(runner._partitions[0])
    assert runner._partitions[0].inspections.offsets
    await runner.on_partitions_revoked(frozenset({0}), 7)
    assert not runner.status.permanent_content_error

    harness.client.epoch = 8
    await runner.on_partitions_assigned(harness.client.assignment, 8)
    state = runner._partitions[0]
    assert state.held is None
    assert set(state.inspections.offsets) == {41}
    harness.positions.initialize.side_effect = lambda request: PositionResult(
        status=PositionStatus.READY, next_offset=checkpoint, assignment_epoch=request.assignment_epoch
    )
    await runner._advance(state)
    assert state.eligible
    if checkpoint == 41:
        assert state.inspections.offsets
        await runner._enqueue({0: [record]}, 8)
        await runner._advance(state)
        await runner._commit_positions((state,))
        harness.client.commit.assert_awaited_once_with({0: 42}, expected_epoch=8)
    else:
        harness.client.commit.assert_not_awaited()
    assert not state.inspections.offsets


@pytest.mark.parametrize("oversized", [False, True], ids=["normal-head", "oversized-head"])
async def test_reassignment_cannot_commit_past_a_compacted_unchecked_record(harness, oversized) -> None:
    runner, client = harness.runner, harness.client
    first, missing = event(harness, 5), event(harness, 6, value=b"invalid")
    await runner._enqueue({0: [first, missing]}, 7)
    harness.processing.process.side_effect = [
        HeldRecord(reason="temporal_unavailable", retry_at=datetime.now(UTC)),
        terminal(runner._identity(first)),
        HeldRecord(reason="admission_closed"),
    ]
    await runner._advance(runner._partitions[0])
    await runner.on_partitions_revoked(frozenset({0}), 7)
    assert set(runner.pending_inspections()[0].offsets) == {5, 6}
    client.epoch = 8
    await runner.on_partitions_assigned(client.assignment, 8)
    state = runner._partitions[0]
    await runner._advance(state)
    await runner._enqueue({0: [first]}, 8)
    await runner._advance(state)
    await runner._commit_positions((state,))

    if oversized:
        harness.settings.event_queue_max_bytes = 1
    await runner._enqueue({0: [event(harness, 7)]}, 8)
    await runner._advance(state)
    await runner._commit_positions((state,))
    assert 6 in state.inspections.offsets
    assert state.held.reason == "inspection_unavailable"
    client.seek.assert_awaited_with(0, 6, expected_epoch=8)
    client.commit.assert_awaited_once_with({0: 6}, expected_epoch=8)
    assert harness.processing.process.await_count == 3
    harness.processing.inspect_only.assert_not_awaited()


async def test_replacement_recovery_must_read_each_inherited_offset(harness) -> None:
    runner, client = harness.runner, harness.client
    created = KafkaRecordRunner(
        runner.snapshot,
        client,
        MagicMock(),
        MagicMock(spec=EventExecutionPreparationService),
        MagicMock(spec=EventAdmissionService),
        processing=harness.processing,
        positions=harness.positions,
    )
    await runner._enqueue({0: [event(harness, 5, value=b"invalid"), event(harness, 6)]}, 7)
    await runner.stop()
    created.restore_inspections(runner.pending_inspections())
    await created.start()
    await created.on_partitions_assigned(client.assignment, 7)
    try:
        state = created._partitions[0]
        client.fetch.return_value = {0: [event(harness, 6)]}
        evidence = await created.close_and_drain(created._request(state), token=uuid4(), boundary=7)
        assert evidence.quiescent
        assert evidence.permanent_content_error
        assert set(state.inspections.offsets) == {5, 6}
        client.seek.assert_awaited_once_with(0, 5, expected_epoch=7)
        harness.processing.inspect_only.assert_not_awaited()
        client.commit.assert_not_awaited()
    finally:
        await created.stop()


@pytest.mark.parametrize("replace_runner", [False, True], ids=["reassignment", "same-publication-replacement"])
async def test_valid_oversized_match_still_guards_checkpoint_after_handover(
    harness, monkeypatch, replace_runner
) -> None:
    context, processing, admission, _raw, _logs = filtered_context(
        monkeypatch, {"expression": "input.payload.value.matches"}
    )
    runner, client = harness.runner, harness.client
    runner.snapshot, runner._processing = context.snapshot, processing
    client.topic, client.group_id = context.snapshot.configuration.topic, context.snapshot.configuration.group_id
    client.assignment = frozenset({2})
    await runner.on_partitions_assigned(client.assignment, 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    first = event(harness, 5, 2, b'{"matches":true,"large":"' + b"a" * 512 + b'"}')
    later = event(harness, 6, 2, b'{"matches":false}')
    harness.settings.event_queue_max_bytes = 64
    await runner._enqueue({2: [first]}, 7)
    assert state.pending_failure is not None
    assert state.pending_failure.validated
    assert runner.pending_inspections()[2].requires_delivery(5)

    if replace_runner:
        await runner.stop()
        replacement = KafkaRecordRunner(
            runner.snapshot,
            client,
            MagicMock(),
            MagicMock(spec=EventExecutionPreparationService),
            admission,
            processing=processing,
            positions=harness.positions,
        )
        replacement.restore_inspections(runner.pending_inspections())
        await replacement.start()
        harness.runner = runner = replacement
    else:
        await runner.on_partitions_revoked(client.assignment, 7)
    client.epoch = 8
    await runner.on_partitions_assigned(client.assignment, 8)
    try:
        state = runner._partitions[2]
        await runner._advance(state)
        await runner._enqueue({2: [later]}, 8)
        await runner._advance(state)
        await runner._commit_positions((state,))
        assert state.inspections.requires_delivery(5)
        client.commit.assert_not_awaited()
        admission.schedule.assert_not_awaited()

        # The original Kafka payload was compacted, but its identity is still known.
        client.fetch.return_value = {2: [later]}
        token = uuid4()
        request = runner._request(state)
        assert not (await runner.close_and_drain(request, token=token, boundary=6)).quiescent
        identity = runner._identity(first)
        admission.recover_accepted.return_value = terminal(identity)
        evidence = await runner.close_and_drain(request, token=token, boundary=6)
        assert evidence.quiescent
        assert not evidence.permanent_content_error
        assert state.inspections.first == 6
        assert all(call.args == (identity,) for call in admission.recover_accepted.await_args_list)
        client.fetch.assert_not_awaited()
    finally:
        if replace_runner:
            await runner.stop()


@pytest.mark.parametrize("oversized_replay", [False, True], ids=["buffered", "oversized"])
async def test_replay_filter_skip_cannot_clear_a_previously_matched_offset(
    harness, monkeypatch, oversized_replay
) -> None:
    context, processing, admission, _raw, _logs = filtered_context(
        monkeypatch, {"expression": 'input.metadata.received_at.startsWith("2026-01-01")'}
    )
    runner, client = harness.runner, harness.client
    runner.snapshot, runner._processing = context.snapshot, processing
    client.assignment = frozenset({2})
    await runner.on_partitions_assigned(client.assignment, 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    harness.settings.event_queue_max_bytes = 64
    raw = event(harness, 5, 2, b'{"text":"' + b"a" * 512 + b'"}')
    first_metadata = raw.source_metadata.model_copy(update={"received_at": datetime(2026, 1, 1, tzinfo=UTC)})
    first = raw.model_copy(update={"source_metadata": first_metadata})
    await runner._enqueue({2: [first]}, 7)
    assert state.inspections.requires_delivery(5)
    await runner.on_partitions_revoked(client.assignment, 7)
    client.epoch = 8
    await runner.on_partitions_assigned(client.assignment, 8)
    state = runner._partitions[2]
    assert state.inspections.requires_delivery(5)
    if not oversized_replay:
        harness.settings.event_queue_max_bytes = 8192
    replay_metadata = raw.source_metadata.model_copy(update={"received_at": datetime(2026, 1, 2, tzinfo=UTC)})
    replay = raw.model_copy(update={"source_metadata": replay_metadata})
    await runner._advance(state)
    await runner._enqueue({2: [replay]}, 8)
    await runner._advance(state)
    identity = runner._identity(first)
    if oversized_replay:
        assert state.held.reason == "queue_capacity"
        assert state.inspections.requires_delivery(5)
        await runner._commit_positions((state,))
        client.commit.assert_not_awaited()
        admission.recover_accepted.return_value = terminal(identity)
        state.held = None
        await runner._advance(state)
    else:
        # Capacity is available now. Retry the saved match with the original timestamp.
        admission.schedule.assert_awaited_once()
        assert admission.schedule.await_args.args[0].input_data["metadata"]["received_at"] == "2026-01-01T00:00:00Z"
    await runner._commit_positions((state,))
    assert state.inspections.first is None
    assert state.local_skip_next_offset is None
    client.commit.assert_awaited_once_with({2: 6}, expected_epoch=8)
    admission.recover_accepted.assert_awaited_with(identity)
    if oversized_replay:
        admission.schedule.assert_not_awaited()


@pytest.mark.parametrize("oversized_successor", [False, True], ids=["buffered", "oversized"])
async def test_later_record_can_progress_after_confirming_the_missing_match(
    harness, monkeypatch, oversized_successor
) -> None:
    context, processing, admission, _raw, _logs = filtered_context(
        monkeypatch, {"expression": "input.payload.value.matches"}
    )
    runner, client = harness.runner, harness.client
    runner.snapshot, runner._processing = context.snapshot, processing
    client.assignment = frozenset({2})
    await runner.on_partitions_assigned(client.assignment, 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    harness.settings.event_queue_max_bytes = 64
    first = event(harness, 5, 2, b'{"matches":true,"text":"' + b"a" * 512 + b'"}')
    await runner._enqueue({2: [first]}, 7)
    await runner.on_partitions_revoked(client.assignment, 7)
    client.epoch = 8
    await runner.on_partitions_assigned(client.assignment, 8)
    state = runner._partitions[2]
    assert state.inspections.requires_delivery(5)
    identity = runner._identity(first)
    admission.recover_accepted.reset_mock()
    admission.recover_accepted.return_value = terminal(identity)
    value = b'{"matches":false}' + (b" " * 128 if oversized_successor else b"")
    await runner._advance(state)
    later = event(harness, 6, 2, value)
    await runner._enqueue({2: [later]}, 8)
    await runner._advance(state)
    if oversized_successor:
        # The earlier proof runs independently, then the oversized payload is reread.
        await runner._enqueue({2: [later]}, 8)
    await runner._commit_positions((state,))
    assert state.inspections.first is None
    admission.recover_accepted.assert_awaited_once_with(identity)
    admission.schedule.assert_not_awaited()
    client.commit.assert_awaited_once_with({2: 7}, expected_epoch=8)


@pytest.mark.parametrize("failure_at", ["lookup", "definitive-rejection"])
async def test_failed_match_replays_with_the_original_filter_decision(harness, monkeypatch, failure_at) -> None:
    context, processing, admission, raw, _logs = filtered_context(
        monkeypatch, {"expression": 'input.metadata.received_at.startsWith("2026-01-01")'}
    )
    runner, client = harness.runner, harness.client
    runner.snapshot, runner._processing = context.snapshot, processing
    client.assignment = frozenset({2})
    await runner.on_partitions_assigned(client.assignment, 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    identity = runner._identity(raw)
    original_time = datetime(2026, 1, 1, tzinfo=UTC)

    def delivered_at(when: datetime) -> RawEvent:
        return raw.model_copy(update={"source_metadata": raw.source_metadata.model_copy(update={"received_at": when})})

    if failure_at == "lookup":
        admission.lookup_execution.return_value = BlockedDelivery(error_code=SchedulingFailureCode.STORAGE_UNAVAILABLE)
    else:
        admission.schedule.return_value = BlockedDelivery(
            error_code=SchedulingFailureCode.TEMPORAL_UNAVAILABLE, start_rejected=True
        )
    await runner._enqueue({2: [delivered_at(original_time)]}, 7)
    await runner._advance(state)
    assert state.inspections.matches == {5: original_time}
    assert state.handoff is None
    await runner._commit_positions((state,))
    client.commit.assert_not_awaited()
    await runner.on_partitions_revoked(client.assignment, 7)

    client.epoch = 8
    await runner.on_partitions_assigned(client.assignment, 8)
    state = runner._partitions[2]
    admission.lookup_execution.return_value = None
    admission.schedule.reset_mock()
    admission.schedule.return_value = terminal(identity)
    await runner._advance(state)
    await runner._enqueue({2: [delivered_at(original_time + timedelta(days=1))]}, 8)
    await runner._advance(state)
    await runner._commit_positions((state,))
    admission.schedule.assert_awaited_once()
    assert admission.schedule.await_args.args[0].binding.received_at == original_time
    assert not state.inspections.matches
    assert state.local_skip_next_offset is None
    client.commit.assert_awaited_once_with({2: 6}, expected_epoch=8)


@pytest.mark.parametrize("oversized", [False, True], ids=["buffered", "oversized"])
async def test_no_match_in_pending_inspection_stays_local(harness, monkeypatch, oversized) -> None:
    context, processing, admission, raw, _logs = filtered_context(monkeypatch, {"expression": "false"})
    runner, client = harness.runner, harness.client
    runner.snapshot, runner._processing = context.snapshot, processing
    client.assignment = frozenset({2})
    runner.restore_inspections({2: PendingInspections({5}, matches={6: datetime.now(UTC)})})
    await runner.on_partitions_assigned(client.assignment, 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    if oversized:
        harness.settings.event_queue_max_bytes = raw_event_size(raw) - 1
    await runner._enqueue({2: [raw]}, 7)
    await runner._advance(state)
    await runner._commit_positions((state,))
    client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)
    assert state.inspections.first == 6
    assert state.inspections.requires_delivery(6)
    admission.lookup_execution.assert_not_awaited()
    admission.recover_accepted.assert_not_awaited()
    admission.schedule.assert_not_awaited()


async def test_unbuffered_recovery_outlives_fetch_budget_and_leaves_sibling_fetchable(harness, monkeypatch) -> None:
    context, processing, admission, raw, _logs = filtered_context(monkeypatch, {"expression": "true"})
    runner, client = harness.runner, harness.client
    runner.snapshot, runner._processing = context.snapshot, processing
    client.assignment = frozenset({2, 3})
    await runner.on_partitions_assigned(client.assignment, 7)
    for key in client.assignment:
        runner._partitions[key].ready = runner._partitions[key].eligible = True
    harness.settings.event_queue_max_bytes = 1
    harness.settings.event_fetch_timeout_ms = 1
    entered, release = asyncio.Event(), asyncio.Event()

    async def recover(identity: DeliveryIdentity) -> ResolvedDelivery:
        entered.set()
        await release.wait()
        return terminal(identity)

    admission.recover_accepted.side_effect = recover
    await runner._enqueue({2: [raw]}, 7)
    admission.recover_accepted.assert_not_awaited()
    state = runner._partitions[2]
    state.task = asyncio.create_task(runner._advance(state))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        await asyncio.sleep(0.01)
        assert not state.task.done()
        await runner._tick()
        assert client.fetch.await_args.args[0] == [3]
    finally:
        release.set()
        await state.task
    await runner._commit_positions((state,))
    client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)
    assert not state.inspections.matches
    admission.schedule.assert_not_awaited()


async def test_later_oversized_fetch_does_not_prevent_retry_of_a_rejected_match(harness, monkeypatch) -> None:
    context, processing, admission, first, _logs = filtered_context(monkeypatch, {"expression": "true"})
    runner, client = harness.runner, harness.client
    runner.snapshot, runner._processing = context.snapshot, processing
    client.assignment = frozenset({2})
    await runner.on_partitions_assigned(client.assignment, 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    harness.settings.event_queue_max_bytes = 8192
    entered, release = asyncio.Event(), asyncio.Event()

    async def reject(_prepared: PreparedExecution) -> BlockedDelivery:
        entered.set()
        await release.wait()
        return BlockedDelivery(error_code=SchedulingFailureCode.TEMPORAL_UNAVAILABLE, start_rejected=True)

    admission.schedule.side_effect = reject
    await runner._enqueue({2: [first]}, 7)
    state.task = asyncio.create_task(runner._advance(state))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        await runner._enqueue({2: [event(harness, 6, 2, b" " * 8193)]}, 7)
        assert state.probe_before == 6
    finally:
        release.set()
        await state.task
    assert state.handoff is None
    assert state.inspections.requires_delivery(5)

    admission.schedule.side_effect = None
    admission.schedule.return_value = terminal(context.identity)
    state.held = None
    await runner._advance(state)
    assert state.probe_before is None
    assert state.inspections.requires_delivery(5)
    state.held = None
    await runner._enqueue({2: [first]}, 7)
    await runner._advance(state)
    await runner._commit_positions((state,))
    assert admission.schedule.await_count == 2
    client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)


async def test_inspection_limit_pauses_only_the_blocked_partition_and_preserves_sparse_offsets(harness) -> None:
    runner, client = harness.runner, harness.client
    state = runner._partitions[0]
    harness.settings.event_queue_max_records = 1
    recovered: set[int] = set()

    def process(_snapshot, identity, record, **_kwargs: object) -> ResolvedDelivery | HeldRecord:
        if record is None:
            return terminal(identity) if identity.record.offset in recovered else HeldRecord(reason="admission_closed")
        if identity.record.offset == 5:
            return HeldRecord(reason="dependency_unavailable", retry_at=datetime.now(UTC))
        return terminal(identity)

    harness.processing.process.side_effect = process
    await runner._enqueue({0: [event(harness, 5)]}, 7)
    await runner._advance(state)
    state.held = None
    await runner._enqueue({0: [event(harness, 7)]}, 7)
    await runner._advance(state)
    assert state.inspections.offsets == {5, 7}

    def fetch(partitions: list[int], *_args: object, **_kwargs: object) -> dict[int, list[RawEvent]]:
        # The inspection read sees the first retained record after compaction.
        return {0: [event(harness, 9)]} if partitions == [0] else {}

    client.fetch.side_effect = fetch
    for _ in range(3):
        state.held = None
        await runner._tick()
        assert state.task is not None
        await state.task
        assert runner.queued_bytes == runner.queued_records == 0
        assert state.inspections.offsets == {5, 7, 9}
    requested = [call.args[0] for call in client.fetch.await_args_list]
    assert requested.count([0]) == 1
    assert requested.count([1]) == 3
    assert state.inspections.first == 5

    # The replay read found the gap from 5 through 8. Reassignment should
    # retain that evidence and avoid consuming a new Kafka record on retry.
    await runner.on_partitions_revoked(frozenset({0}), 7)
    client.assignment = frozenset({0})
    client.epoch = 8
    harness.positions.initialize.side_effect = None
    harness.positions.initialize.return_value = PositionResult(
        status=PositionStatus.READY, next_offset=5, assignment_epoch=8
    )
    await runner.on_partitions_assigned(client.assignment, 8)
    state = runner._partitions[0]
    await runner._advance(state)
    client.fetch.reset_mock()
    await runner._advance(state)
    client.fetch.assert_not_awaited()
    assert state.inspections.offsets == {5, 7, 9}

    # Both compacted records are confirmed. The remaining records replay
    # normally even though Kafka never delivered an offset 10.
    recovered.update((5, 7))
    for _ in recovered:
        state.held = None
        await runner._advance(state)
    assert state.inspections.offsets == {9}
    for offset in (9, 11):
        await runner._enqueue({0: [event(harness, offset)]}, 8)
        await runner._advance(state)
    await runner._commit_positions((state,))
    assert not state.inspections
    client.commit.assert_awaited_once_with({0: 12}, expected_epoch=8)


async def test_inspection_limit_replays_an_earlier_verified_prefix(harness) -> None:
    runner, client = harness.runner, harness.client
    harness.settings.event_queue_max_records = 1
    state = runner._partitions[0]
    state.inspections = PendingInspections({5, 7, 9}, read_gap=(5, 9))
    request = runner._request(state)
    token = uuid4()
    evidence = await runner.close_and_drain(request, token=token, boundary=3)
    assert evidence.quiescent
    assert not evidence.permanent_content_error
    harness.positions.initialize.side_effect = None
    harness.positions.initialize.return_value = PositionResult(
        status=PositionStatus.READY, next_offset=3, assignment_epoch=7
    )
    assert await runner.resume_after_recovery(request, token=token)
    prefix = event(harness, 3)
    client.fetch.return_value = {0: [prefix]}
    await runner._run_partition(state)
    await runner._commit_positions((state,))
    client.seek.assert_awaited_once_with(0, 3, expected_epoch=7)
    client.commit.assert_awaited_once_with({0: 4}, expected_epoch=7)
    assert state.inspections.offsets == {5, 7, 9}


async def test_repeated_empty_replay_polls_keep_the_position(harness) -> None:
    runner, client = harness.runner, harness.client
    harness.settings.event_queue_max_records = 1
    state = runner._partitions[0]
    state.inspections = PendingInspections({5, 7})
    client.fetch.side_effect = [{}, {}, {0: [event(harness, 5)]}]
    for _ in range(3):
        state.held = None
        await runner._run_partition(state)
    await runner._commit_positions((state,))
    client.seek.assert_awaited_once_with(0, 5, expected_epoch=7)
    client.commit.assert_awaited_once_with({0: 6}, expected_epoch=7)
    assert state.inspections.offsets == {7}


async def test_full_inspection_budget_keeps_replay_after_repeated_verified_rewinds(harness) -> None:
    runner, client = harness.runner, harness.client
    harness.settings.event_queue_max_records = 1
    client.assignment = frozenset({0})
    state = runner._partitions[0]
    original_time = datetime.now(UTC)
    state.inspections = PendingInspections({7, 9}, matches={5: original_time}, read_gap=(5, 9))
    healthy = False

    def process(
        _snapshot,
        identity,
        raw,
        *,
        remember_match: Callable[[datetime], None] | None = None,
        **_kwargs: object,
    ) -> ResolvedDelivery | HeldRecord:
        if raw is not None and not healthy and remember_match is not None:
            remember_match(raw.source_metadata.received_at)
        if raw is None or not healthy:
            return HeldRecord(reason="dependency_unavailable")
        return terminal(identity)

    harness.processing.process.side_effect = process
    for checkpoint, epoch in ((4, 8), (3, 9)):
        await runner.on_partitions_revoked(client.assignment, epoch - 1)
        client.epoch = epoch
        await runner.on_partitions_assigned(client.assignment, epoch)
        state = runner._partitions[0]
        harness.positions.initialize.return_value = PositionResult(
            status=PositionStatus.READY, next_offset=checkpoint, assignment_epoch=epoch
        )
        harness.positions.initialize.side_effect = None
        await runner._advance(state)
        client.fetch.return_value = {0: [event(harness, checkpoint)]}
        await runner._run_partition(state)
        assert state.inspections.requires_delivery(checkpoint)
    assert len(state.inspections) == 5

    healthy = True
    state.held = None
    await runner._run_partition(state)
    await runner._commit_positions((state,))
    before_resolution = state.inspections.copy()
    client.commit.assert_awaited_once_with({0: 4}, expected_epoch=9)
    assert state.inspections.first == 4
    assert state.inspections.matched_at(5) == original_time
    state.inspections.resolve(4)
    assert state.inspections.first == 5
    assert before_resolution.first == 4


async def test_spill_lookup_failure_keeps_every_offset_from_the_returned_batch(harness, monkeypatch) -> None:
    runner = harness.runner
    state = runner._partitions[0]
    state.inspections = PendingInspections({5})
    assert state.inspections.reserve_replay_read(1)
    find = inspection_spool.InspectionSpool.find

    def lookup(spool: inspection_spool.InspectionSpool, offset: int) -> tuple[bool, datetime | None]:
        if offset == 7:
            msg = "Temporary read failure"
            raise sqlite3.OperationalError(msg)
        return find(spool, offset)

    monkeypatch.setattr(inspection_spool.InspectionSpool, "find", lookup)
    await runner._enqueue({0: [event(harness, 7), event(harness, 8)]}, 7)
    assert runner.pending_inspections()[0].offsets == {7, 8}


async def test_inspection_staging_failure_keeps_later_partitions_from_same_fetch(harness, monkeypatch) -> None:
    runner = harness.runner
    harness.settings.event_queue_max_bytes = 8
    stage = AsyncMock(side_effect=sqlite3.OperationalError("Temporary lookup failure"))
    monkeypatch.setattr(runner, "_stage_content_failure", stage)

    healthy = event(harness, 8, 1)
    await runner._enqueue({0: [event(harness, 7, value=b'{"large":true}')], 1: [healthy]}, 7)

    stage.assert_awaited_once()
    assert runner._partitions[0].held.reason == "processing_unavailable"
    assert runner.pending_inspections()[0].offsets == {7}
    assert runner.pending_inspections()[1].offsets == {8}
    assert list(runner._partitions[1].records) == [healthy]


async def test_spill_error_blocks_only_its_position_recovery(harness, monkeypatch) -> None:
    runner, client = harness.runner, harness.client
    state = runner._partitions[0]
    state.inspections = PendingInspections({5})
    assert state.inspections.reserve_replay_read(1)
    token = uuid4()
    with monkeypatch.context() as patch:
        patch.setattr(inspection_spool.InspectionSpool, "find", Mock(side_effect=sqlite3.OperationalError))
        result = await runner.close_and_drain(runner._request(state), token=token, boundary=6)
    assert not result.quiescent
    assert state.inspections.first == 5
    assert state.fence == token
    client.commit.assert_not_awaited()


async def test_spill_error_does_not_leave_unaccounted_handoff_arguments(harness, monkeypatch) -> None:
    context, processing, admission, record, _logs = filtered_context(monkeypatch, {"expression": "true"})
    runner, client = harness.runner, harness.client
    runner.snapshot, runner._processing = context.snapshot, processing
    client.assignment = frozenset({2})
    await runner.on_partitions_assigned(client.assignment, 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    state.inspections = PendingInspections({9})
    assert state.inspections.reserve_replay_read(1)

    async def schedule(prepared: PreparedExecution) -> ResolvedDelivery:
        assert runner.queued_bytes == prepared.encoded_arguments_size()
        patch.setattr(inspection_spool.InspectionSpool, "find", Mock(side_effect=sqlite3.OperationalError))
        return terminal(prepared.identity)

    admission.schedule.side_effect = schedule
    await runner._enqueue({2: [record]}, 7)
    with monkeypatch.context() as patch:
        await runner._advance(state)
    assert state.handoff is None
    assert runner.queued_bytes == runner.queued_records == 0
    assert state.inspections.requires_delivery(5)
    await runner._commit_positions((state,))
    client.commit.assert_not_awaited()


async def test_spill_creation_failure_keeps_offsets_and_falls_back_to_proof(harness, monkeypatch) -> None:
    runner, client = harness.runner, harness.client
    harness.settings.event_queue_max_records = 1
    state = runner._partitions[0]
    state.inspections = PendingInspections({3, 5, 7, 9, 11})
    invalidate = Mock()
    monkeypatch.setattr(runner, "_invalidate_gate", invalidate)

    def no_space(**_kwargs: object) -> None:
        msg = "No space for temporary evidence"
        raise OSError(msg)

    monkeypatch.setattr(inspection_spool, "TemporaryDirectory", no_space)
    await runner._advance(state)
    client.fetch.assert_not_awaited()
    invalidate.assert_not_called()
    assert state.inspections.offsets == {3, 5, 7, 9, 11}
    assert harness.processing.process.await_args.args[1] == runner._delivery_identity(0, 3)


@pytest.mark.parametrize("offset_reset", [False, True], ids=["empty", "offset-reset"])
async def test_fenced_recovery_can_read_at_the_inspection_limit(harness, offset_reset) -> None:
    runner, client = harness.runner, harness.client
    harness.settings.event_queue_max_records = 1
    state = runner._partitions[0]
    state.inspections = PendingInspections({5, 7, 9, 11, 13})
    first_poll: dict[int, list[RawEvent]] | KafkaTransportError = (
        KafkaTransportError("Kafka offset reset requires position reconciliation") if offset_reset else {}
    )
    client.fetch.side_effect = [first_poll, {0: [event(harness, 5)]}]
    request = runner._request(state)
    token = uuid4()

    waiting = await runner.close_and_drain(request, token=token, boundary=6)
    assert waiting.permanent_content_error
    completed = await runner.close_and_drain(request, token=token, boundary=6)
    assert completed.quiescent
    assert not completed.permanent_content_error
    assert client.seek.await_count == (2 if offset_reset else 1)
    client.seek.assert_awaited_with(0, 5, expected_epoch=7)
    harness.processing.inspect_only.assert_awaited_once()
    assert state.inspections.first == 7
    assert len(state.inspections) == 4


async def test_proof_only_probes_leave_normal_processing_slots_available(harness) -> None:
    runner, client = harness.runner, harness.client
    harness.settings.event_queue_max_records = 1
    runner._work = asyncio.Semaphore(1)
    client.assignment = frozenset({0, 1, 2})
    await runner.on_partitions_assigned(client.assignment, 7)
    for partition, state in runner._partitions.items():
        state.ready = state.eligible = True
        if partition in (0, 1):
            state.inspections = PendingInspections({5, 7}, read_gap=(5, 9))
    await runner._enqueue({2: [event(harness, 12, 2)]}, 7)
    released = asyncio.Event()
    proofs = []

    async def process(_snapshot, identity, record, **_kwargs: object) -> ResolvedDelivery | HeldRecord:
        if record is None:
            proofs.append(identity.record.partition)
            await released.wait()
            return HeldRecord(reason="admission_closed")
        return terminal(identity)

    harness.processing.process.side_effect = process
    runner._start_due_tasks()
    healthy_task = runner._partitions[2].task
    assert healthy_task is not None
    try:
        await asyncio.wait_for(healthy_task, 1)
        assert runner._partitions[2].resolved_next_offset == 13
        assert proofs == [0]
        assert runner._partitions[1].task is None
    finally:
        released.set()
        await asyncio.gather(*(state.task for state in runner._partitions.values() if state.task is not None))
    runner._partitions[0].held = None
    runner._start_due_tasks()
    await asyncio.gather(*(state.task for state in runner._partitions.values() if state.task is not None))
    assert proofs == [0, 1]


async def test_buffered_prior_offset_lookup_leaves_normal_processing_slot_available(harness) -> None:
    runner = harness.runner
    runner._work = asyncio.Semaphore(1)
    blocked, healthy = (runner._partitions[partition] for partition in (0, 1))
    blocked.inspections = PendingInspections({5})
    await runner._enqueue({0: [event(harness, 7)], 1: [event(harness, 8, 1)]}, 7)
    checking, release = asyncio.Event(), asyncio.Event()

    async def process(_snapshot, identity, record, **_kwargs: object) -> ResolvedDelivery | HeldRecord:
        if record is None:
            checking.set()
            await release.wait()
            return HeldRecord(reason="admission_closed")
        return terminal(identity)

    harness.processing.process.side_effect = process
    runner._start_due_tasks()
    assert blocked.task is not None
    assert healthy.task is not None
    try:
        await asyncio.wait_for(checking.wait(), 1)
        await asyncio.wait_for(healthy.task, 1)
        assert healthy.resolved_next_offset == 9
        assert not blocked.task.done()
    finally:
        release.set()
        await asyncio.gather(blocked.task, healthy.task)
    assert blocked.inspections.first == 5


async def test_idle_handoff_is_retried_before_oversized_lookahead_proof(harness, monkeypatch) -> None:
    context, _, _, _, _ = filtered_context(monkeypatch, {"expression": "true"})
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    runner, client = harness.runner, harness.client
    runner.snapshot = context.snapshot
    client.assignment = frozenset({2})
    await runner.on_partitions_assigned(client.assignment, 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    state.handoff = prepared
    state.inspections = PendingInspections(matches={5: datetime.now(UTC)})
    state.probe_before = 7

    await runner._advance(state)
    assert state.handoff is None
    harness.processing.process.assert_awaited_once()
    assert harness.processing.process.await_args.kwargs["handoff"] == prepared


async def test_capacity_probes_are_rotated_and_do_not_queue_ahead_of_normal_fetches(harness) -> None:
    runner, client = harness.runner, harness.client
    harness.settings.event_queue_max_records = 2
    harness.settings.event_fetch_max_records = 2
    client.assignment = frozenset(range(5))
    await runner.on_partitions_assigned(client.assignment, 7)
    for partition, state in runner._partitions.items():
        state.ready = state.eligible = True
        if partition != 4:
            state.inspections = PendingInspections({5, 7, 9})

    for probe in range(4):
        client.fetch.reset_mock()
        for state in runner._partitions.values():
            state.held = None
        await runner._tick()
        await asyncio.gather(*(state.task for state in runner._partitions.values() if state.task is not None))
        calls = {tuple(call.args[0]): call.kwargs["max_records"] for call in client.fetch.await_args_list}
        assert calls == {(4,): 2, (probe,): 1}
        assert client.fetch.await_count == 2


async def test_capacity_probe_retains_a_record_returned_during_recovery_drain(harness) -> None:
    runner, client = harness.runner, harness.client
    harness.settings.event_queue_max_records = 1
    harness.settings.event_drain_timeout_seconds = 1
    state = runner._partitions[0]
    state.inspections = PendingInspections({5, 7})
    state.replay_next_offset = 3
    invalid = event(harness, 3, value=b"invalid JSON")
    harness.processing.inspect_only.side_effect = None
    harness.processing.inspect_only.return_value = HeldRecord(reason="dependency_unavailable")
    entered, release = asyncio.Event(), asyncio.Event()

    async def fetch(*_args: object, **_kwargs: object) -> dict[int, list[RawEvent]]:
        entered.set()
        await release.wait()
        return {0: [invalid]}

    client.fetch.side_effect = fetch
    state.task = asyncio.create_task(runner._advance(state))
    await asyncio.wait_for(entered.wait(), timeout=1)
    draining = asyncio.create_task(runner.close_and_drain(runner._request(state), token=uuid4(), boundary=5))
    await asyncio.sleep(0)
    release.set()
    evidence = await draining
    assert evidence.permanent_content_error
    assert state.inspections.first == 3
    client.commit.assert_not_awaited()


@pytest.mark.parametrize("path", ["replay", "recovery-compaction", "recovery-retention"])
async def test_unreadable_uninspected_offset_can_use_existing_execution(harness, monkeypatch, path) -> None:
    context, processing, admission, _, _ = filtered_context(monkeypatch, {"expression": "false"})
    runner, client = harness.runner, harness.client
    runner.snapshot, runner._processing = context.snapshot, processing
    client.assignment = frozenset({2})
    runner.restore_inspections({2: PendingInspections({8})})
    await runner.on_partitions_assigned(client.assignment, 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    identity = runner._identity(event(harness, 8, 2))
    admission.recover_accepted.return_value = terminal(identity)
    later = event(harness, 9, 2)
    if path == "replay":
        await runner._enqueue({2: [later]}, 7)
        await runner._advance(state)
        await runner._commit_positions((state,))
        client.commit.assert_awaited_once_with({2: 10}, expected_epoch=7)
    else:
        if path == "recovery-retention":
            client.fetch.side_effect = KafkaTransportError("Kafka offset reset requires position reconciliation")
        else:
            client.fetch.return_value = {2: [later]}
        evidence = await runner.close_and_drain(runner._request(state), token=uuid4(), boundary=9)
        assert evidence.quiescent
        assert not evidence.permanent_content_error
        client.commit.assert_not_awaited()
    assert state.inspections.offsets == ({9} if path == "recovery-compaction" else set())
    admission.recover_accepted.assert_awaited_once_with(identity)
    admission.schedule.assert_not_awaited()


@pytest.mark.parametrize("boundary", [6, 8], ids=["before-lookahead", "after-lookahead"])
async def test_position_recovery_retains_the_actual_offset_returned_by_a_lookup(harness, boundary) -> None:
    runner, client = harness.runner, harness.client
    state = runner._partitions[0]
    await runner._enqueue({0: [event(harness, 5)]}, 7)
    client.fetch.return_value = {0: [event(harness, 7, value=b"invalid JSON")]}
    harness.processing.inspect_only.side_effect = None
    harness.processing.inspect_only.return_value = HeldRecord(reason="dependency_unavailable")

    def process(_snapshot, identity, raw, **_kwargs: object) -> ResolvedDelivery | HeldRecord:
        if raw is None and identity.record.offset != 5:
            return HeldRecord(reason="admission_closed")
        return terminal(identity)

    harness.processing.process.side_effect = process
    token = uuid4()
    request = runner._request(state)
    evidence = await runner.close_and_drain(request, token=token, boundary=boundary)
    assert state.inspections.offsets == {7}
    if boundary == 8:
        assert evidence.permanent_content_error
        harness.processing.inspect_only.assert_awaited_once()
    else:
        assert evidence.quiescent
        assert not evidence.permanent_content_error
        harness.positions.initialize.side_effect = None
        harness.positions.initialize.return_value = PositionResult(
            status=PositionStatus.READY, next_offset=6, assignment_epoch=7
        )
        assert await runner.resume_after_recovery(request, token=token)
        # The lookahead record is compacted before normal replay starts.
        await runner._enqueue({0: [event(harness, 8)]}, 7)
        await runner._advance(state)
        await runner._commit_positions((state,))
        assert state.inspections.first == 7
        assert [call.args[1].record.offset for call in harness.processing.process.await_args_list] == [5, 7]
    client.commit.assert_not_awaited()


@pytest.mark.parametrize("lose_ownership", [False, True])
async def test_filtered_resolution_requires_current_ownership_before_commit(
    harness, monkeypatch, *, lose_ownership
) -> None:
    context, processing, admission, record, audit = filtered_context(monkeypatch, {"expression": "false"})
    runner = harness.runner
    runner.snapshot = context.snapshot
    runner._processing = processing
    harness.client.group_id = context.snapshot.configuration.group_id
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    await runner._enqueue({2: [record]}, 7)
    await runner._advance(state)
    eligible = processing.admission_eligible
    assert isinstance(eligible, AsyncMock)
    eligible.assert_not_awaited()
    admission.lookup_execution.assert_not_awaited()
    admission.recover_accepted.assert_not_awaited()
    assert context.session.mock_calls == []
    admission.schedule.assert_not_awaited()
    audit.error.assert_not_called()
    if lose_ownership:
        harness.client.epoch = 8
    await runner._commit_positions((state,))
    if lose_ownership:
        harness.client.commit.assert_not_awaited()
    else:
        harness.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)


async def test_filter_error_log_failure_does_not_prevent_offset_commit(harness, monkeypatch) -> None:
    context, processing, admission, record, logs = filtered_context(
        monkeypatch, {"expression": "input.payload.value.count"}
    )
    logs.error.side_effect = OSError("Log destination unavailable")
    runner = harness.runner
    runner.snapshot = context.snapshot
    runner._processing = processing
    harness.client.group_id = context.snapshot.configuration.group_id
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    await runner._enqueue({2: [record]}, 7)
    await runner._advance(state)
    assert context.session.mock_calls == []
    await runner._commit_positions((state,))
    assert state.held is None
    eligible = processing.admission_eligible
    assert isinstance(eligible, AsyncMock)
    eligible.assert_not_awaited()
    admission.lookup_execution.assert_not_awaited()
    admission.recover_accepted.assert_not_awaited()
    logs.error.assert_called_once()
    admission.schedule.assert_not_awaited()
    harness.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)


async def test_matching_record_commits_only_after_handoff_retry_confirms_execution(harness, monkeypatch) -> None:
    context, processing, admission, record, _logs = filtered_context(monkeypatch, {"expression": "true"})
    runner = harness.runner
    runner.snapshot = context.snapshot
    runner._processing = processing
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    harness.settings.event_queue_max_records = 1
    admission.schedule.return_value = RetryDelivery(
        error_code=SchedulingFailureCode.STORAGE_UNAVAILABLE,
        next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
        circuit_open=False,
    )
    await runner._enqueue({2: [record]}, 7)
    await runner._advance(state)
    assert state.handoff is not None
    arguments = state.handoff.workflow_arguments()
    await runner._commit_positions((state,))
    harness.client.commit.assert_not_awaited()
    assert not state.records  # The existing park path rewinds and releases the raw bytes.
    assert runner.queued_records == 1
    assert runner.queued_bytes == state.handoff.encoded_arguments_size()
    harness.client.seek.assert_awaited_with(2, 5, expected_epoch=7)

    admission.recover_accepted.return_value = terminal(context.identity)
    admission.lookup_execution.return_value = terminal(context.identity)
    runner._start_due_tasks()
    assert state.task is not None
    await state.task
    await runner._enqueue({2: [record]}, 7)
    await runner._advance(state)
    admission.recover_accepted.assert_awaited_once_with(context.identity)
    admission.schedule.assert_awaited_once()
    assert admission.schedule.await_args.args[0].workflow_arguments() == arguments
    assert state.handoff is None
    assert runner.queued_records == runner.queued_bytes == 0
    await runner._commit_positions((state,))
    harness.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)


@pytest.mark.parametrize("rejected", [False, True])
async def test_drain_distinguishes_cancelled_accepted_start_from_rejection(harness, monkeypatch, *, rejected) -> None:
    context, processing, admission, record, _logs = filtered_context(monkeypatch, {"expression": "true"})
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    harness.settings.event_queue_max_bytes = max(raw_event_size(record), prepared.encoded_arguments_size())
    runner = harness.runner
    runner.snapshot, runner._processing = context.snapshot, processing
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    starting = asyncio.Event()

    async def schedule(prepared: PreparedExecution) -> BlockedDelivery:
        assert runner._handoffs[prepared.identity.digest].prepared is prepared
        assert runner.queued_records == 1
        assert not state.records
        assert state.byte_count == 0
        assert runner.queued_bytes == prepared.encoded_arguments_size()
        starting.set()
        if rejected:
            return BlockedDelivery(error_code=SchedulingFailureCode.TEMPORAL_UNAVAILABLE, start_rejected=True)
        # Temporal accepted; Execution persistence is still pending.
        return await asyncio.Future[BlockedDelivery]()

    admission.schedule.side_effect = schedule
    await runner._enqueue({2: [record]}, 7)
    state.task = asyncio.create_task(runner._advance(state))
    await asyncio.wait_for(starting.wait(), timeout=1)
    if rejected:
        await state.task
        assert state.inspections.requires_delivery(5)
        harness.client.seek.assert_awaited_with(2, 5, expected_epoch=7)
        await runner.stop()
        admission.recover_accepted.assert_not_awaited()
    else:
        with pytest.raises(SubscriptionRuntimeError, match="stop_incomplete"):
            await runner.stop()
        assert state.task.cancelled()
        assert state.handoff is not None
        assert not state.records
        assert state.byte_count == 0
        assert runner.queued_bytes == state.handoff.encoded_arguments_size()
        admission.recover_accepted.return_value = terminal(context.identity)
        await runner.stop()
        admission.recover_accepted.assert_awaited_with(context.identity)
    assert runner._stopped
    assert not runner._handoffs
    harness.client.commit.assert_not_awaited()


async def test_full_handoff_byte_budget_prevents_new_temporal_start(harness, monkeypatch) -> None:
    context, processing, admission, record, _logs = filtered_context(monkeypatch, {"expression": "true"})
    runner = harness.runner
    runner.snapshot, runner._processing = context.snapshot, processing
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    harness.settings.event_queue_max_bytes = raw_event_size(record)
    await runner._enqueue({2: [record]}, 7)
    await runner._advance(state)
    assert state.held.reason == "queue_capacity"
    admission.schedule.assert_not_awaited()
    assert runner.queued_bytes == 0
    assert not runner._handoffs
    await runner._commit_positions((state,))
    harness.client.commit.assert_not_awaited()


async def test_matching_head_and_preparation_share_a_single_byte_reservation(harness, monkeypatch) -> None:
    context, processing, admission, record, _logs = filtered_context(monkeypatch, {"expression": "true"})
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    monkeypatch.setattr(processing._preparation, "prepare_delivery", AsyncMock(return_value=prepared))
    runner = harness.runner
    runner.snapshot, runner._processing = context.snapshot, processing
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    budget = max(raw_event_size(record), prepared.encoded_arguments_size())
    harness.settings.event_queue_max_bytes = budget

    async def schedule(attempt: PreparedExecution) -> ResolvedDelivery:
        assert not state.records
        assert runner.queued_bytes == attempt.encoded_arguments_size()
        return terminal(attempt.identity)

    admission.schedule.side_effect = schedule
    await runner._enqueue({2: [record]}, 7)
    await runner._advance(state)
    admission.schedule.assert_awaited_once_with(prepared)
    assert runner.queued_bytes == 0
    await runner._commit_positions((state,))
    harness.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)


async def test_detached_handoff_counts_against_partition_fetch_and_enqueue_limits(harness, monkeypatch) -> None:
    context, processing, admission, record, _logs = filtered_context(monkeypatch, {"expression": "true"})
    runner, client = harness.runner, harness.client
    runner.snapshot, runner._processing = context.snapshot, processing
    client.assignment = frozenset({2})
    await runner.on_partitions_assigned(client.assignment, 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    harness.settings.event_partition_max_records = 1
    starting, release = asyncio.Event(), asyncio.Event()

    async def schedule(prepared: PreparedExecution) -> ResolvedDelivery:
        starting.set()
        await release.wait()
        return terminal(prepared.identity)

    admission.schedule.side_effect = schedule
    await runner._enqueue({2: [record]}, 7)
    state.task = asyncio.create_task(runner._advance(state))
    try:
        await asyncio.wait_for(starting.wait(), timeout=1)
        await runner._tick()
        assert client.fetch.await_args.args[0] == []

        # A fetch started before the reservation may still return a record.
        await runner._enqueue({2: [event(harness, 6, 2)]}, 7)
        assert not state.records
        assert runner.queued_records == 1
        assert state.held is None
        client.seek.assert_awaited_once_with(2, 6, expected_epoch=7)
    finally:
        release.set()
        await state.task
    await runner._commit_positions((state,))
    client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)
    await runner._tick()
    assert client.fetch.await_args.args[0] == [2]


@pytest.mark.parametrize("refetched_offset", [41, 45], ids=["earlier-checkpoint", "later-compacted-record"])
async def test_reload_finishes_original_handoff_before_processing_a_different_record(
    harness, monkeypatch, refetched_offset
) -> None:
    context, processing, admission, record, _logs = filtered_context(
        monkeypatch, {"expression": "input.payload.value.count == 2"}
    )
    runner = harness.runner
    runner.snapshot = context.snapshot
    runner._processing = processing
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    earlier = record.model_copy(update={"source_metadata": record.source_metadata.model_copy(update={"offset": "41"})})
    admission.lookup_execution.side_effect = (
        lambda identity: terminal(identity) if identity.record.offset == 41 else None
    )
    attempted = record.model_copy(
        update={"source_metadata": record.source_metadata.model_copy(update={"offset": "44"})}
    )
    attempted_identity = runner._identity(attempted)
    retry = RetryDelivery(
        error_code=SchedulingFailureCode.TEMPORAL_UNAVAILABLE,
        next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
        circuit_open=False,
    )
    admission.schedule.return_value = retry
    await runner._enqueue({2: [earlier, attempted]}, 7)
    await runner._advance(state)
    harness.client.commit.side_effect = KafkaTransportError("Commit unavailable")
    await runner._commit_positions((state,))
    assert state.resolved_next_offset == 42

    harness.client.seek.side_effect = KafkaTransportError("Rewind unavailable")
    await runner._advance(state)
    assert state.reload_required
    assert state.handoff is not None
    arguments = state.handoff.workflow_arguments()
    harness.client.seek.side_effect = None
    harness.positions.initialize.side_effect = lambda request: PositionResult(
        status=PositionStatus.READY, next_offset=41, assignment_epoch=request.assignment_epoch
    )
    admission.recover_accepted.side_effect = [retry, terminal(attempted_identity)]
    state.held = None
    await runner._advance(state)
    assert state.handoff is not None
    # Reload discards the old commit candidate while retaining the handoff.
    # The earlier prefix remains available from the verified broker cursor.
    assert state.resolved_next_offset is None
    await runner._commit_positions((state,))
    harness.client.commit.assert_awaited_once_with({2: 42}, expected_epoch=7)

    state.held = None
    await runner._advance(state)
    assert state.handoff is None
    assert state.ready
    refetched = earlier.model_copy(
        update={
            "value": b'{"count":0}',
            "source_metadata": earlier.source_metadata.model_copy(update={"offset": str(refetched_offset)}),
        }
    )
    await runner._enqueue({2: [refetched]}, 7)
    await runner._advance(state)
    admission.schedule.assert_awaited_once()
    assert admission.schedule.await_args.args[0].workflow_arguments() == arguments
    assert [call.args[0] for call in admission.recover_accepted.await_args_list] == [attempted_identity] * 2
    assert [call.args[0] for call in admission.lookup_execution.await_args_list] == [
        runner._identity(earlier),
        attempted_identity,
    ]
    harness.client.commit.side_effect = None
    await runner._commit_positions((state,))
    assert harness.client.commit.await_args.args == ({2: refetched_offset + 1},)


@pytest.mark.parametrize("failure", ["epoch", "dependency", "evidence"])
async def test_finishing_a_different_handoff_preserves_commit_guards(harness, monkeypatch, failure) -> None:
    context, processing, admission, record, _logs = filtered_context(
        monkeypatch, {"expression": "input.payload.value.count == 2"}
    )
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    runner = harness.runner
    runner.snapshot = context.snapshot
    runner._processing = processing
    gate = MagicMock(spec=RecordProcessingGate)
    gate.admission_open.return_value = gate.resolution_open.return_value = True
    runner._gate = processing._gate = gate
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    state.handoff = prepared
    later = record.model_copy(
        update={"value": b'{"count":0}', "source_metadata": record.source_metadata.model_copy(update={"offset": "6"})}
    )
    await runner._enqueue({2: [later]}, 7)

    async def recover(identity: DeliveryIdentity) -> ResolvedDelivery:
        if failure == "epoch":
            harness.client.epoch += 1
        elif failure == "dependency":
            gate.resolution_open.return_value = False
        else:
            return terminal(identity.model_copy(update={"workflow_id": uuid4()}))
        return terminal(identity)

    admission.recover_accepted.side_effect = recover
    await runner._advance(state)
    await runner._commit_positions((state,))
    # Valid persistence frees the reservation independently of commit authority.
    assert state.handoff is (prepared if failure == "evidence" else None)
    assert state.resolved_next_offset is None
    harness.client.commit.assert_not_awaited()
    admission.schedule.assert_not_awaited()


async def test_gap_recovery_preserves_handoff_before_its_offset(harness, monkeypatch) -> None:
    refetched_offset = 3
    context, processing, admission, record, _logs = filtered_context(
        monkeypatch, {"expression": "input.payload.value.count == 2"}
    )
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    arguments = prepared.workflow_arguments()
    prepare = AsyncMock(side_effect=AssertionError("Recovery must retain the attempted arguments"))
    monkeypatch.setattr(context.service, "prepare_delivery", prepare)
    runner = harness.runner
    runner.snapshot = context.snapshot
    runner._processing = processing
    harness.settings.event_drain_timeout_seconds = 1
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    state.handoff = prepared
    request, token = runner._request(state), uuid4()
    evidence = await runner.close_and_drain(request, token=token, boundary=refetched_offset)
    assert evidence.quiescent
    assert not evidence.permanent_content_error
    assert state.handoff is prepared
    harness.positions.initialize.side_effect = lambda request: PositionResult(
        status=PositionStatus.READY, next_offset=refetched_offset, assignment_epoch=request.assignment_epoch
    )
    assert await runner.resume_after_recovery(request, token=token)
    assert state.handoff is prepared
    assert state.handoff.workflow_arguments() == arguments

    refetched = record.model_copy(
        update={
            "value": b'{"count":0}',
            "source_metadata": record.source_metadata.model_copy(update={"offset": str(refetched_offset)}),
        }
    )
    finish = AsyncMock(wraps=runner._finish_handoff)
    monkeypatch.setattr(runner, "_finish_handoff", finish)
    admission.recover_accepted.return_value = terminal(prepared.identity)
    await runner._enqueue({2: [refetched]}, 7)
    await runner._advance(state)
    finish.assert_awaited_once_with(state)
    admission.recover_accepted.assert_awaited_once_with(prepared.identity)
    assert state.handoff is None
    assert list(state.records) == [refetched]
    assert state.resolved_next_offset is None
    await runner._commit_positions((state,))
    harness.client.commit.assert_not_awaited()

    await runner._advance(state)
    await runner._commit_positions((state,))
    harness.client.commit.assert_awaited_once_with({2: refetched_offset + 1}, expected_epoch=7)
    prepare.assert_not_awaited()
    admission.lookup_execution.assert_not_awaited()
    admission.schedule.assert_not_awaited()


async def test_unbufferable_local_skip_needs_no_database_marker(harness, monkeypatch) -> None:
    context, processing, admission, record, logs = filtered_context(monkeypatch, {"expression": "false"})
    runner = harness.runner
    runner.snapshot = context.snapshot
    runner._processing = processing
    harness.client.group_id = context.snapshot.configuration.group_id
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    harness.settings.event_queue_max_bytes = 1
    await runner._enqueue({2: [record]}, 7)
    await runner._commit_positions((state,))
    context.session.add.assert_not_called()
    admission.lookup_execution.assert_not_awaited()
    admission.recover_accepted.assert_not_awaited()
    assert state.pending_failure is None
    assert state.held is None
    admission.schedule.assert_not_awaited()
    logs.info.assert_called_once()
    harness.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)


@pytest.mark.parametrize("lose_ownership", [False, True])
async def test_invalid_content_commit_requires_current_partition_ownership(
    harness, monkeypatch, *, lose_ownership
) -> None:
    context, processing, admission, record = processing_context(monkeypatch)
    monkeypatch.setattr(processing, "admission_eligible", AsyncMock(return_value=True))
    runner = harness.runner
    runner.snapshot = context.snapshot
    runner._processing = processing
    harness.client.group_id = context.snapshot.configuration.group_id
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    audit = MagicMock()
    if lose_ownership:
        audit.side_effect = lambda _event, **_kwargs: setattr(harness.client, "epoch", 8)
    monkeypatch.setattr(AuditEventDispatcher, "dispatch", audit)

    await runner._enqueue({2: [record.model_copy(update={"value": b"invalid"})]}, 7)
    await runner._advance(state)
    await runner._commit_positions((state,))

    audit.assert_called_once()
    admission.recover_accepted.assert_awaited_once_with(context.identity)
    admission.schedule.assert_not_awaited()
    context.session.add.assert_not_called()
    if lose_ownership:
        assert state.resolved_next_offset is None
        harness.client.commit.assert_not_awaited()
    else:
        harness.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)


async def test_unresolved_offset_gap_does_not_stop_another_partition(harness) -> None:
    runner = harness.runner
    blocked = runner._partitions[0]
    blocked.ready = False
    blocked.initialization = PositionResult(
        status=PositionStatus.RECOVERY_GAP, assignment_epoch=7, reason="missing_commit"
    )
    harness.positions.recover_automatically.return_value = blocked.initialization
    await runner._recover_requested(blocked)

    await runner._enqueue({1: [event(harness, 41, partition=1)]}, 7)
    await runner._advance(runner._partitions[1])
    await runner._commit_positions(tuple(runner._partitions.values()))

    assert blocked.initialization.status == PositionStatus.RECOVERY_GAP
    assert blocked.resolved_next_offset is None
    harness.client.commit.assert_awaited_once_with({1: 42}, expected_epoch=7)


async def test_failed_skip_commit_is_reevaluated_after_restart_and_filter_revision(harness, monkeypatch) -> None:
    context, processing, admission, record, _logs = filtered_context(monkeypatch, {"expression": "false"})
    runner = harness.runner
    runner.snapshot = context.snapshot
    runner._processing = processing
    monkeypatch.setattr(processing, "admission_eligible", AsyncMock(return_value=True))
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    await runner._enqueue({2: [record]}, 7)
    await runner._advance(state)
    harness.client.commit.side_effect = KafkaTransportError("Commit unavailable")
    await runner._commit_positions((state,))
    assert state.resolved_next_offset == 6
    context.session.add.assert_not_called()
    admission.schedule.assert_not_awaited()
    await runner.stop()

    revised = SubscriptionSnapshot.model_validate(
        {
            **context.snapshot.model_dump(mode="json"),
            "configuration_revision": context.snapshot.configuration_revision + 1,
            "filter": {"expression": "true"},
        }
    )
    prepare = AsyncMock(return_value=terminal(context.identity))
    monkeypatch.setattr(processing, "_prepare_and_schedule", prepare)
    harness.client.topic = revised.configuration.topic
    harness.client.group_id = revised.configuration.group_id
    harness.client.epoch = 8
    harness.client.commit.side_effect = None
    restarted = KafkaRecordRunner(
        revised,
        harness.client,
        lambda: context.session,
        context.service,
        admission,
        processing=processing,
        positions=harness.positions,
    )
    try:
        await restarted.start()
        await restarted.on_partitions_assigned(frozenset({2}), 8)
        await restarted._advance(restarted._partitions[2])
        await restarted._enqueue({2: [record]}, 8)
        await restarted._advance(restarted._partitions[2])
        prepare.assert_awaited_once()
        assert prepare.call_args.args[0].configuration_revision == revised.configuration_revision
        await restarted._commit_positions((restarted._partitions[2],))
        assert harness.client.commit.await_args_list[-1].kwargs == {"expected_epoch": 8}
        assert harness.client.commit.await_args_list[-1].args == ({2: 6},)
    finally:
        await restarted.stop()


@pytest.mark.parametrize("expression", ["false", "input.payload.value.count"])
@pytest.mark.parametrize("closure", ["stop", "pause", "lease"])
async def test_completed_filter_skip_commits_during_drain_without_processing_the_tail(
    harness,
    monkeypatch,
    expression: str,
    closure: str,
) -> None:
    context, processing, admission, record, logs = filtered_context(monkeypatch, {"expression": expression})
    runner = harness.runner
    runner.snapshot = context.snapshot
    runner._processing = processing
    gate = Mock()
    gate.admission_open.return_value = gate.resolution_open.return_value = True
    runner._gate = processing._gate = gate
    monkeypatch.setattr(processing, "admission_eligible", AsyncMock(return_value=True))
    harness.settings.event_drain_timeout_seconds = 1
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    tail = record.model_copy(update={"source_metadata": record.source_metadata.model_copy(update={"offset": "8"})})
    await runner._enqueue({2: [record, tail]}, 7)
    await runner._advance(state)
    assert state.resolved_next_offset == 6
    assert list(state.records) == [tail]

    if closure == "pause":
        gate.admission_open.return_value = False
    elif closure == "lease":
        runner._placement_authority = lambda: False
    await runner.close_admission()
    assert not runner._admission_open()
    await runner._advance(state)
    await runner._commit_positions((state,))
    harness.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)
    assert state.resolved_next_offset is None
    assert list(state.records) == [tail]
    (logs.info if expression == "false" else logs.error).assert_called_once()
    admission.schedule.assert_not_awaited()


@pytest.mark.parametrize("failure", ["epoch", "assignment", "dependency", "fence", "deadline"])
async def test_completed_filter_skip_cannot_bypass_commit_safety_during_drain(
    harness,
    monkeypatch,
    failure: str,
) -> None:
    context, processing, _admission, record, _logs = filtered_context(monkeypatch, {"expression": "false"})
    runner = harness.runner
    runner.snapshot = context.snapshot
    runner._processing = processing
    gate = Mock()
    gate.admission_open.return_value = gate.resolution_open.return_value = True
    runner._gate = processing._gate = gate
    monkeypatch.setattr(processing, "admission_eligible", AsyncMock(return_value=True))
    harness.settings.event_drain_timeout_seconds = 1
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    await runner._enqueue({2: [record]}, 7)
    await runner._advance(state)
    assert state.resolved_next_offset == 6

    if failure == "epoch":
        harness.client.epoch += 1
    elif failure == "assignment":
        harness.client.assignment = frozenset()
    elif failure == "dependency":
        gate.resolution_open.return_value = False
    elif failure == "fence":
        state.fence = uuid4()
    else:
        runner._drain_deadline = asyncio.get_running_loop().time() - 1
    await runner.close_admission()
    harness.client.commit.assert_not_awaited()
    assert state.resolved_next_offset == 6


async def test_filter_skip_finishing_after_admission_closes_is_not_a_completed_prefix(harness, monkeypatch) -> None:
    context, processing, _admission, record, logs = filtered_context(monkeypatch, {"expression": "false"})
    runner = harness.runner
    runner.snapshot = context.snapshot
    runner._processing = processing
    monkeypatch.setattr(processing, "admission_eligible", AsyncMock(return_value=True))
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    logs.info.side_effect = lambda *_args, **_kwargs: setattr(runner, "_closing", True)
    await runner._enqueue({2: [record]}, 7)
    await runner._advance(state)
    assert state.held is not None
    assert state.held.reason == "admission_closed"
    assert state.resolved_next_offset is None
    await runner._commit_positions((state,))
    harness.client.commit.assert_not_awaited()


@pytest.mark.parametrize("expression", ["false", "input.payload.value.count"])
async def test_unbufferable_record_with_closed_admission_retries_before_filtering(
    harness, monkeypatch, expression
) -> None:
    context, processing, admission, record, logs = filtered_context(monkeypatch, {"expression": expression})
    runner = harness.runner
    runner.snapshot = context.snapshot
    runner._processing = processing
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    harness.settings.event_queue_max_bytes = 1
    gate = Mock()
    gate.admission_open.return_value = False
    gate.resolution_open.return_value = True
    processing._gate = gate

    await runner._enqueue({2: [record]}, 7)
    assert state.held is not None
    assert state.held.reason == "admission_closed"
    assert state.pending_failure is None
    assert state.resolved_next_offset is None
    assert state.inspections.offsets
    logs.info.assert_not_called()
    logs.error.assert_not_called()
    harness.client.seek.assert_awaited_with(2, 5, expected_epoch=7)

    # Retry only after the shared lifecycle/dependency gate reopens.
    gate.admission_open.return_value = True
    state.held = None
    await runner._advance(state)
    await runner._enqueue({2: [record]}, 7)
    await runner._commit_positions((state,))
    assert state.held is None
    assert state.pending_failure is None
    admission.schedule.assert_not_awaited()
    (logs.info if expression == "false" else logs.error).assert_called_once()
    harness.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)


@pytest.mark.parametrize("expression", ["false", "input.payload.value.count"])
@pytest.mark.parametrize("oversized", [False, True])
async def test_republish_before_skip_checkpoint_leaves_the_batch_uncommitted(
    harness, monkeypatch, expression, *, oversized
) -> None:
    context, processing, admission, record, _logs = filtered_context(monkeypatch, {"expression": expression})
    runner = harness.runner
    runner.snapshot, runner._processing = context.snapshot, processing
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    if oversized:
        harness.settings.event_queue_max_bytes = 1
    await runner._enqueue({2: [record]}, 7)
    # Publish on the same source while the old runner's local gate is open.
    context.subscription.configuration_revision += 1
    context.subscription.filter = {"expression": "true"}
    await runner._advance(state)
    assert state.resolved_next_offset == 6
    await runner._commit_positions((state,))
    harness.client.commit.assert_not_awaited()
    assert state.resolved_next_offset == 6
    admission.lookup_execution.assert_not_awaited()
    admission.recover_accepted.assert_not_awaited()
    admission.schedule.assert_not_awaited()


async def test_skip_batch_holds_publication_lock_until_broker_commit_finishes(harness, monkeypatch) -> None:
    context, processing, admission, record, _logs = filtered_context(monkeypatch, {"expression": "false"})
    lifecycle = AsyncMock(return_value=(context.subscription, context.source))
    monkeypatch.setattr(record_processing_service, "lock_source_lifecycle", lifecycle)
    runner = harness.runner
    runner.snapshot, runner._processing = context.snapshot, processing
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    tail = record.model_copy(update={"source_metadata": record.source_metadata.model_copy(update={"offset": "6"})})
    context.events.clear()
    await runner._enqueue({2: [record, tail]}, 7)
    await runner._run_partition(state)
    assert context.events == []
    entered, release = asyncio.Event(), asyncio.Event()

    async def commit(_offsets: dict[int, int], *, expected_epoch: int) -> None:
        assert expected_epoch == 7
        assert context.events == ["begin"]
        context.transaction.__aexit__.assert_not_awaited()
        entered.set()
        await release.wait()

    harness.client.commit.side_effect = commit
    task = asyncio.create_task(runner._commit_positions((state,)))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        assert context.events == ["begin"]
    finally:
        release.set()
        await task
    assert context.events == ["begin", "commit"]
    lifecycle.assert_awaited_once_with(context.session, context.snapshot.source_id)
    assert state.local_skip_next_offset is None
    admission.lookup_execution.assert_not_awaited()
    admission.recover_accepted.assert_not_awaited()


async def test_failed_skip_commit_fences_runner_before_later_execution_completion(harness, monkeypatch) -> None:
    context, processing, admission, record, _logs = filtered_context(
        monkeypatch, {"expression": "input.payload.value.count == 2"}
    )
    runner = harness.runner
    runner.snapshot, runner._processing = context.snapshot, processing
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    skipped = record.model_copy(update={"value": b'{"count":0}'})
    matched = record.model_copy(update={"source_metadata": record.source_metadata.model_copy(update={"offset": "6"})})
    admission.lookup_execution.return_value = terminal(runner._identity(matched))
    await runner._enqueue({2: [skipped, matched]}, 7)
    await runner._advance(state)
    harness.client.commit.side_effect = KafkaCommitUncertainError("Commit unavailable", asyncio.Event())
    await runner._commit_positions((state,))
    assert state.local_skip_next_offset == 6
    assert runner._closing
    harness.client.fence_commits.assert_awaited_once()
    await runner._advance(state)
    assert state.resolved_next_offset == 6
    assert list(state.records) == [matched]
    context.subscription.configuration_revision += 1
    harness.client.commit.reset_mock(side_effect=True)
    await runner._commit_positions((state,))
    harness.client.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "checkpoint", ["normal", "recovery", "recovery_with_tail", "reassigned_recovery", "oversized", "idle"]
)
async def test_unresolved_handoff_blocks_every_checkpoint_crossing_its_offset(harness, monkeypatch, checkpoint) -> None:
    context, processing, admission, record, _logs = filtered_context(
        monkeypatch, {"expression": "input.payload.value.count == 2"}
    )
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    runner = harness.runner
    runner.snapshot, runner._processing = context.snapshot, processing
    runner._placement_authority = lambda: True
    harness.settings.event_drain_timeout_seconds = 1
    harness.settings.event_fetch_timeout_ms = 1000
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    state.handoff = prepared
    admission.recover_accepted.return_value = RetryDelivery(
        error_code=SchedulingFailureCode.STORAGE_UNAVAILABLE,
        next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
        circuit_open=False,
    )
    if checkpoint == "normal":
        state.resolved_next_offset = 6
    elif checkpoint in {"recovery", "recovery_with_tail", "reassigned_recovery"}:
        if checkpoint == "reassigned_recovery":
            await runner.on_partitions_revoked(frozenset({2}), 7)
            harness.client.epoch = 8
            await runner.on_partitions_assigned(frozenset({2}), 8)
            state = runner._partitions[2]
            assert state.handoff == prepared
        if checkpoint == "recovery_with_tail":
            later = record.model_copy(
                update={
                    "value": b"invalid",
                    "source_metadata": record.source_metadata.model_copy(update={"offset": "6"}),
                }
            )
            await runner._enqueue({2: [later]}, 7)
        request, token = runner._request(state), uuid4()
        evidence = await runner.close_and_drain(request, token=token, boundary=6)
        assert not evidence.quiescent
        if checkpoint == "recovery_with_tail":
            assert state.inspections.offsets
            assert set(state.inspections.offsets) == {6}
    elif checkpoint == "oversized":
        harness.settings.event_queue_max_bytes = 1
        later = record.model_copy(
            update={
                "value": b'{"count":0}',
                "source_metadata": record.source_metadata.model_copy(update={"offset": "6"}),
            }
        )
        await runner._enqueue({2: [later]}, 7)
        await runner._advance(state)
    else:
        state.ready = False
        runner._start_due_tasks()
        assert state.task is not None
        await state.task
        harness.positions.initialize.assert_not_awaited()
        harness.client.fetch.assert_not_awaited()
    if checkpoint != "normal":
        admission.recover_accepted.assert_awaited_once_with(prepared.identity)
    await runner._commit_positions((state,))
    harness.client.commit.assert_not_awaited()
    assert state.handoff is prepared
    admission.schedule.assert_not_awaited()


async def test_recovery_persists_saved_handoff_before_allowing_a_later_boundary(harness, monkeypatch) -> None:
    context, processing, admission, _record, _logs = filtered_context(monkeypatch, {"expression": "true"})
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    runner = harness.runner
    runner.snapshot, runner._processing = context.snapshot, processing
    harness.settings.event_drain_timeout_seconds = 1
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    state.handoff = prepared
    admission.recover_accepted.return_value = terminal(prepared.identity)
    evidence = await runner.close_and_drain(runner._request(state), token=uuid4(), boundary=6)
    assert evidence.quiescent
    assert not evidence.permanent_content_error
    assert state.handoff is None
    admission.recover_accepted.assert_awaited_once_with(prepared.identity)
    admission.schedule.assert_not_awaited()


@pytest.mark.parametrize("failure", ["epoch", "fence", "dependency", "deadline"])
async def test_skip_checkpoint_rechecks_local_safety_after_waiting_for_revision_lock(
    harness, monkeypatch, failure
) -> None:
    context, processing, _admission, record, _logs = filtered_context(monkeypatch, {"expression": "false"})
    runner = harness.runner
    runner.snapshot, runner._processing = context.snapshot, processing
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    await runner._enqueue({2: [record]}, 7)
    await runner._advance(state)

    async def lock(_session: object, _source_id: object) -> object:
        if failure == "epoch":
            harness.client.epoch += 1
        elif failure == "fence":
            state.fence = uuid4()
        elif failure == "dependency":
            gate = Mock()
            gate.resolution_open.return_value = False
            runner._gate = gate
        else:
            runner._drain_deadline = asyncio.get_running_loop().time() - 1
        return context.subscription, context.source

    monkeypatch.setattr(record_processing_service, "lock_source_lifecycle", AsyncMock(side_effect=lock))
    await runner._commit_positions((state,))
    harness.client.commit.assert_not_awaited()
    assert state.resolved_next_offset == 6


@pytest.mark.parametrize("submitted", [False, True], ids=["waiting-for-publication-lock", "broker-write-issued"])
async def test_cursor_reload_fences_a_captured_checkpoint(harness, monkeypatch, submitted) -> None:
    runner, client = harness.runner, harness.client
    state = runner._partitions[0]
    sibling = runner._partitions[1]
    runner._work = asyncio.Semaphore(1)
    state.resolved_next_offset = state.local_skip_next_offset = 42
    harness.settings.event_queue_max_bytes = 64
    entered, release = asyncio.Event(), asyncio.Event()

    async def wait() -> None:
        entered.set()
        await release.wait()

    @asynccontextmanager
    async def revision_guard(_snapshot) -> AsyncIterator[bool]:
        if not submitted:
            await wait()
        yield True

    async def commit(_offsets, *, expected_epoch: int) -> None:
        assert expected_epoch == 7
        await wait()

    monkeypatch.setattr(harness.processing, "local_skip_commit_guard", revision_guard)
    client.commit.side_effect = commit
    committed = 42 if submitted else 4
    harness.positions.initialize.side_effect = None
    harness.positions.initialize.return_value = PositionResult(
        status=PositionStatus.READY, next_offset=committed, assignment_epoch=7
    )
    batch = asyncio.create_task(runner._commit_batch((state,)))
    reloading = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        client.seek.side_effect = KafkaTransportError("seek unavailable")
        await runner._enqueue({0: [event(harness, 43, value=b"{}" + b" " * 128)]}, 7)
        reloading = asyncio.create_task(runner._advance(state))
        await asyncio.sleep(0)
        assert state.resolved_next_offset is None
        harness.positions.initialize.assert_not_awaited()
        await runner._enqueue({1: [event(harness, 8, partition=1)]}, 7)
        await asyncio.wait_for(runner._advance(sibling), timeout=1)
        assert sibling.resolved_next_offset == 9
    finally:
        release.set()
        await batch
        if reloading is not None:
            await reloading
    harness.positions.initialize.assert_awaited_once()
    if submitted:
        client.commit.assert_awaited_once_with({0: 42}, expected_epoch=7)
    else:
        client.commit.assert_not_awaited()
    assert state.resolved_next_offset is None
    assert state.inspections.requires_delivery(43)


async def test_new_skip_during_commit_keeps_its_revision_fence(harness) -> None:
    runner = harness.runner
    state = runner._partitions[0]
    harness.processing.process.side_effect = lambda snapshot, identity, _event, **_kwargs: SkippedRecord(
        identity=identity, configuration_revision=snapshot.configuration_revision, outcome="no_match"
    )
    await runner._enqueue({0: [event(harness, 5), event(harness, 6)]}, 7)
    await runner._advance(state)

    async def commit(offsets: dict[int, int], *, expected_epoch: int) -> None:
        assert offsets == {0: 6}
        assert expected_epoch == 7
        await runner._advance(state)

    harness.client.commit.side_effect = commit
    await runner._commit_positions((state,))
    assert state.resolved_next_offset == state.local_skip_next_offset == 7
    harness.processing.local_skip_commit_guard.return_value.__aenter__.return_value = False
    harness.client.commit.reset_mock(side_effect=True)
    await runner._commit_positions((state,))
    harness.client.commit.assert_not_awaited()


@pytest.mark.parametrize("cancel_observer", [False, True])
async def test_skip_commit_keeps_revision_lock_after_observer_timeout_or_cancel(  # noqa: PLR0915 - One commit/publication race.
    harness, monkeypatch, *, cancel_observer: bool
) -> None:
    runner = harness.runner
    state = runner._partitions[0]
    state.resolved_next_offset = state.local_skip_next_offset = 6
    monkeypatch.setattr(EventStreamLimits, "COMMITTED_POSITION_TIMEOUT_SECONDS", 0.01)
    publication_lock = asyncio.Lock()
    entered, release = asyncio.Event(), asyncio.Event()
    published: list[int] = []

    @asynccontextmanager
    async def guard(_snapshot: SubscriptionSnapshot) -> AsyncIterator[bool]:
        async with publication_lock:
            yield True

    monkeypatch.setattr(harness.processing, "local_skip_commit_guard", guard)

    async def broker_commit() -> None:
        await release.wait()
        assert publication_lock.locked()
        assert published == []

    broker = asyncio.create_task(broker_commit())

    async def commit(_offsets: dict[int, int], *, expected_epoch: int) -> None:
        assert expected_epoch == 7
        entered.set()
        await asyncio.shield(broker)  # Reproduce aiokafka's independently shielded operation.

    async def publish() -> None:
        async with publication_lock:
            published.append(2)

    harness.client.commit.side_effect = commit
    observer = asyncio.create_task(runner._commit_positions((state,)))
    publication = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        if cancel_observer:
            observer.cancel()
            with pytest.raises(asyncio.CancelledError):
                await observer
        else:
            await observer
        assert publication_lock.locked()
        assert runner._commit_task is not None
        assert not runner._commit_task.done()
        publication = asyncio.create_task(publish())
        await runner._commit_positions((state,))
        assert not publication.done()
        harness.client.commit.assert_awaited_once()
        with pytest.raises(SubscriptionRuntimeError, match="stop_incomplete"):
            await runner.stop()
        harness.client.stop.assert_not_awaited()
    finally:
        release.set()
        await broker
        await asyncio.gather(observer, return_exceptions=True)
        if runner._commit_task is not None:
            await runner._commit_task
        if publication is not None:
            await publication
    assert published == [2]


@pytest.mark.parametrize("uncertain", [False, True], ids=["group-authorization-denied", "ambiguous-write"])
async def test_skip_commit_fences_only_unsettled_writes(harness, monkeypatch, *, uncertain: bool) -> None:
    runner = harness.runner
    state = runner._partitions[0]
    state.resolved_next_offset = state.local_skip_next_offset = 6
    monkeypatch.setattr(EventStreamLimits, "COMMITTED_POSITION_TIMEOUT_SECONDS", 0.01)
    lock = asyncio.Lock()
    fencing, acknowledged = asyncio.Event(), asyncio.Event()

    @asynccontextmanager
    async def guard(_snapshot: SubscriptionSnapshot) -> AsyncIterator[bool]:
        async with lock:
            yield True

    async def fence(_failure: KafkaCommitUncertainError) -> None:
        fencing.set()
        await acknowledged.wait()
        assert lock.locked()

    monkeypatch.setattr(harness.processing, "local_skip_commit_guard", guard)
    failure = (
        KafkaCommitUncertainError("Commit failed", asyncio.Event())
        if uncertain
        else KafkaTransportError("Commit failed")
    )
    if not uncertain:
        failure.__cause__ = GroupAuthorizationFailedError()
    harness.client.commit.side_effect = failure
    harness.client.fence_commits.side_effect = fence
    observer = asyncio.create_task(runner._commit_positions((state,)))
    try:
        if uncertain:
            await asyncio.wait_for(fencing.wait(), timeout=1)
        await observer
        if not uncertain and runner._commit_task is not None:
            await runner._commit_task
        assert fencing.is_set() is uncertain
        assert lock.locked() is uncertain
        assert runner._closing is uncertain
    finally:
        acknowledged.set()
        await observer
        if runner._commit_task is not None:
            await runner._commit_task
    assert not lock.locked()
    assert state.local_skip_next_offset == 6
    assert state.resolved_next_offset == 6


async def test_stop_retains_parked_handoff_across_revocation_until_execution_is_confirmed(harness, monkeypatch) -> None:
    context, processing, admission, _record, _logs = filtered_context(monkeypatch, {"expression": "true"})
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    runner = harness.runner
    runner.snapshot, runner._processing = context.snapshot, processing
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    state.handoff = prepared
    admission.recover_accepted.return_value = RetryDelivery(
        error_code=SchedulingFailureCode.STORAGE_UNAVAILABLE, next_attempt_at=datetime.now(UTC), circuit_open=False
    )
    filtering = Mock(side_effect=AssertionError("A saved handoff must bypass filtering"))
    monkeypatch.setattr(processing, "evaluate_filter", filtering)

    async def revoke() -> None:
        if harness.client.assignment:
            await runner.on_partitions_revoked(frozenset({2}), 7)
            harness.client.assignment = frozenset()
            harness.client.epoch += 1

    harness.client.stop.side_effect = revoke
    with pytest.raises(SubscriptionRuntimeError, match="stop_incomplete"):
        await runner.stop()
    assert 2 not in runner._partitions
    assert runner._handoffs[prepared.identity.digest].prepared.workflow_arguments() == prepared.workflow_arguments()
    assert runner.queued_records == 1
    assert runner.queued_bytes == prepared.encoded_arguments_size()
    assert not runner._stopped
    admission.recover_accepted.return_value = terminal(prepared.identity)
    await runner.stop()
    assert runner._stopped
    assert not runner._handoffs
    admission.schedule.assert_not_awaited()
    filtering.assert_not_called()


@pytest.mark.parametrize("probe_fails", [False, True], ids=["resume-fetching", "retry-on-stop"])
async def test_detached_handoff_releases_full_queue_for_a_healthy_partition(
    harness, monkeypatch, *, probe_fails
) -> None:
    context, processing, admission, record, _logs = filtered_context(monkeypatch, {"expression": "true"})
    runner = harness.runner
    runner.snapshot, runner._processing = context.snapshot, processing
    harness.settings.event_queue_max_records = 1
    harness.settings.event_drain_timeout_seconds = 1
    harness.client.assignment = frozenset({2, 3})
    await runner.on_partitions_assigned(harness.client.assignment, 7)
    for partition in (2, 3):
        runner._partitions[partition].ready = runner._partitions[partition].eligible = True
    admission.schedule.return_value = BlockedDelivery(error_code=SchedulingFailureCode.STORAGE_UNAVAILABLE)
    await runner._enqueue({2: [record]}, 7)
    await runner._advance(runner._partitions[2])
    await runner.on_partitions_revoked(frozenset({2}), 7)
    harness.client.assignment = frozenset({3})
    assert runner.queued_records == 1

    confirmed = terminal(context.identity)
    if probe_fails:
        admission.recover_accepted.side_effect = [RuntimeError("probe failed"), confirmed]
    else:
        admission.recover_accepted.return_value = confirmed
    await runner._tick()
    assert runner._detached_handoff_task is not None
    await asyncio.wait_for(runner._detached_handoff_task, timeout=1)
    if probe_fails:
        assert runner.queued_records == 1
        await runner.stop()
        assert runner._stopped
        assert runner.queued_records == 0
        assert admission.recover_accepted.await_count == 2
        admission.schedule.assert_awaited_once()
        return
    assert runner.queued_records == runner.queued_bytes == 0
    await runner._tick()
    assert harness.client.fetch.await_args.args[0] == [3]
    admission.recover_accepted.assert_awaited_once_with(context.identity)
    admission.schedule.assert_awaited_once()
    harness.client.commit.assert_not_awaited()


async def test_due_detached_handoff_does_not_starve_behind_a_failed_probe(harness, monkeypatch) -> None:
    context, _processing, _admission, _record, _logs = filtered_context(monkeypatch, {"expression": "true"})
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    second_identity = prepared.identity.model_copy(
        update={"record": prepared.identity.record.model_copy(update={"partition": 3})}
    )
    second = prepared.model_copy(update={"identity": second_identity})
    runner = harness.runner
    runner.snapshot = context.snapshot
    harness.client.assignment = frozenset({2, 3})
    await runner.on_partitions_assigned(harness.client.assignment, 7)
    runner._partitions[2].handoff = prepared
    runner._partitions[3].handoff = second
    await runner.on_partitions_revoked(harness.client.assignment, 7)
    harness.client.assignment = frozenset()
    monkeypatch.setattr(EventSchedulingDefaults, "TRANSIENT_PROBE_SECONDS", 0)
    harness.processing.process.side_effect = [HeldRecord(reason="storage_unavailable"), terminal(second_identity)]

    for _ in range(2):
        runner._poll_detached_handoffs()
        assert runner._detached_handoff_task is not None
        await runner._detached_handoff_task
    assert [call.args[1] for call in harness.processing.process.await_args_list] == [prepared.identity, second_identity]
    assert runner.queued_records == 1


async def test_stop_retains_a_task_that_returns_a_handoff_after_drain_timeout(harness, monkeypatch) -> None:
    context, _processing, _admission, record, _logs = filtered_context(monkeypatch, {"expression": "true"})
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    runner = harness.runner
    runner.snapshot = context.snapshot
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True
    entered, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def process(_snapshot, _identity, _event, **_kwargs: object) -> HeldRecord:
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            await release.wait()
        return HeldRecord(reason="storage_unavailable", handoff=prepared)

    harness.processing.process.side_effect = process
    await runner._enqueue({2: [record]}, 7)
    state.task = asyncio.create_task(runner._advance(state))
    try:
        await entered.wait()
        with pytest.raises(SubscriptionRuntimeError, match="stop_incomplete"):
            await runner.stop()
        assert cancelled.is_set()
        harness.client.stop.assert_not_awaited()
    finally:
        release.set()
        await state.task
    assert runner._handoffs[prepared.identity.digest].prepared == prepared
    with pytest.raises(SubscriptionRuntimeError, match="stop_incomplete"):
        await runner.stop()
    assert not runner._stopped
    harness.processing.process.side_effect = lambda _snapshot, identity, _event, **_kwargs: terminal(identity)
    await runner.stop()
    assert runner._stopped
