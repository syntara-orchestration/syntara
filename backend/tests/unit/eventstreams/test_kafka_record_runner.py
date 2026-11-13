"""Kafka runner orchestration and injected failures using isolated adapters."""

import asyncio
import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
import pytest_asyncio
from aiokafka.errors import AuthenticationFailedError, KafkaConnectionError, KafkaTimeoutError

from syntara.core.config.base import get_settings
from syntara.core.constants import EventStreamLimits
from syntara.eventstreams.adapters import kafka_record_runner as module
from syntara.eventstreams.adapters.kafka_consumer import KafkaPartitionConsumer
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
from syntara.eventstreams.core.consumer import MAX_POSITION_OFFSET
from syntara.eventstreams.core.deduplication import DeliveryIdentity
from syntara.eventstreams.core.envelope import RawEvent, RawEventHeader
from syntara.eventstreams.core.handler import ResolvedDelivery, RetryDelivery, SchedulingFailureCode
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.core.processing import HeldRecord, InspectedRecord, RecordProcessingGate
from syntara.eventstreams.core.results import EventDecodeFailure
from syntara.eventstreams.core.runtime import RuntimeState, SubscriptionRuntimeError
from syntara.eventstreams.core.serialization import JsonEventDecoder
from syntara.eventstreams.exceptions import KafkaTransportError
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
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
    processing.admission_eligible.return_value = True
    processing.process.side_effect = lambda _snapshot, identity, _event: terminal(identity)
    processing.hold_content_failure.return_value = HeldRecord(
        reason="activity_log_unavailable", permanent_content_error=True
    )

    def inspect(_snapshot, identity, record) -> HeldRecord | InspectedRecord:
        decoded = JsonEventDecoder().decode(record)
        return (
            HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
            if isinstance(decoded, EventDecodeFailure)
            else InspectedRecord(identity=identity)
        )

    processing.inspect_only.side_effect = inspect
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

    async def process(_snapshot, identity, _record) -> ResolvedDelivery | HeldRecord:
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

    async def process(_snapshot, identity, _record) -> ResolvedDelivery:
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

    async def process(_snapshot, identity, _record) -> ResolvedDelivery:
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

    async def process(*_args: object) -> None:
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
        reason="activity_log_unavailable", permanent_content_error=True
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

    async def process(*_args: object) -> HeldRecord:
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
    assert not state.content_gate_unknown
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

    async def process(_snapshot, identity, _event) -> ResolvedDelivery:
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

    async def process(_snapshot, identity, _event) -> ResolvedDelivery:
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


async def test_oversized_content_holds_without_committing(harness) -> None:
    runner = harness.runner
    record = event(harness, 41, value=b"x" * (harness.settings.event_queue_max_bytes + 1))
    await runner._enqueue({0: [record, event(harness, 90)]}, 7)
    state = runner._partitions[0]
    assert runner.queued_bytes == 0
    assert runner.queued_records == 0
    harness.processing.inspect_only.assert_awaited_once_with(runner.snapshot, runner._identity(record), record)
    assert state.pending_failure is None
    assert state.held.permanent_content_error
    evidence = await runner.close_and_drain(runner._request(state), token=uuid4(), boundary=91)
    assert evidence.quiescent
    assert evidence.permanent_content_error
    await runner.stop()
    harness.processing.process.assert_not_awaited()
    harness.client.commit.assert_not_awaited()


async def test_pending_oversized_error_blocks_actual_recovery_even_if_database_is_unavailable(harness) -> None:
    runner = harness.runner
    harness.processing.inspect_only.side_effect = None
    harness.processing.inspect_only.return_value = HeldRecord(
        reason="dependency_unavailable", retry_at=datetime.now(UTC)
    )
    harness.processing.process.side_effect = None
    harness.processing.process.return_value = HeldRecord(reason="delivery_evidence_unavailable")
    await runner._enqueue({0: [event(harness, 41, value=b"x" * (harness.settings.event_queue_max_bytes + 1))]}, 7)
    state = runner._partitions[0]
    await runner._advance(state)
    assert state.pending_failure is not None
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
    runner = harness.runner
    await runner._enqueue({0: [event(harness, 41)]}, 7)
    state = runner._partitions[0]
    evidence = await runner.close_and_drain(runner._request(state), token=uuid4(), boundary=91)
    assert not evidence.permanent_content_error
    assert runner.queued_records == 0
    assert runner.queued_bytes == 0
    harness.processing.inspect_only.assert_awaited_once()


async def test_oversized_tail_waits_for_earlier_record_resolution(harness) -> None:
    runner = harness.runner
    oversized = event(harness, 44, value=b"x" * (harness.settings.event_queue_max_bytes + 1))
    await runner._enqueue({0: [event(harness, 41), oversized, event(harness, 90)]}, 7)
    state = runner._partitions[0]
    assert state.pending_failure is None
    assert state.content_gate_unknown
    assert runner.queued_records == 1
    await runner._advance(state)
    assert state.resolved_next_offset == 42
    harness.processing.hold_content_failure.assert_not_awaited()
    await runner._enqueue({0: [oversized, event(harness, 90)]}, 7)
    await runner._advance(state)
    assert state.held.permanent_content_error
    assert harness.processing.process.await_count == 1
    assert harness.processing.inspect_only.await_count == 1
    await runner._commit_positions((state,))
    harness.client.commit.assert_awaited_once_with({0: 42}, expected_epoch=7)


async def test_oversized_terminal_redelivery_resolves_without_retaining_payload(harness) -> None:
    runner = harness.runner
    record = event(harness, 41, value=b"x" * (harness.settings.event_queue_max_bytes + 1))
    identity = runner._identity(record)
    harness.processing.inspect_only.side_effect = None
    harness.processing.inspect_only.return_value = terminal(identity)
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
    harness.processing.inspect_only.side_effect = None
    harness.processing.inspect_only.return_value = terminal(identity)
    await runner._enqueue({0: [record]}, 7)
    state = runner._partitions[0]
    await runner._commit_positions((state,))
    assert state.pending_failure is not None
    assert state.held is not None
    assert state.resolved_next_offset is None
    harness.client.commit.assert_not_awaited()


async def test_terminal_redelivery_exceeding_only_queue_capacity_uses_existing_evidence(harness) -> None:
    harness.settings.event_queue_max_bytes = 1
    runner = harness.runner
    record = event(harness, 41)
    await runner._enqueue({0: [record]}, 7)
    state = runner._partitions[0]
    await runner._advance(state)
    assert state.pending_failure is None
    assert not state.content_gate_unknown
    assert state.resolved_next_offset == 42
    await runner._commit_positions((state,))
    harness.processing.process.assert_awaited_once_with(runner.snapshot, runner._identity(record), None)
    harness.processing.hold_content_failure.assert_not_awaited()
    harness.client.commit.assert_awaited_once_with({0: 42}, expected_epoch=7)


async def test_completion_behind_recovery_fence_cannot_restore_old_commit_position(harness) -> None:
    runner = harness.runner
    entered, release = asyncio.Event(), asyncio.Event()

    async def process(_snapshot, identity, _record) -> ResolvedDelivery:
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


async def test_fenced_inspection_retries_dependency_failure_without_admitting_work(harness) -> None:
    runner = harness.runner
    record = event(harness, 41)
    await runner._enqueue({0: [record]}, 7)
    harness.client.fetch.return_value = {0: [record]}
    harness.processing.inspect_only.side_effect = [
        HeldRecord(reason="dependency_unavailable", retry_at=datetime.now(UTC)),
        InspectedRecord(identity=runner._identity(record)),
    ]
    state = runner._partitions[0]
    token = uuid4()
    request = runner._request(state)
    first = await runner.close_and_drain(request, token=token, boundary=91)
    assert first.quiescent
    assert first.permanent_content_error
    assert state.inspection_next_offset == 41
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
    assert [call.args[1] for call in harness.client.seek.await_args_list] == [41, 42, 45]
    assert [call.args[1].record.offset for call in harness.processing.inspect_only.await_args_list] == [41, 44, 90]
    assert state.resolved_next_offset is None
    assert runner.queued_records == runner.queued_bytes == 0
    harness.processing.process.assert_not_awaited()
    harness.client.commit.assert_not_awaited()


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
    runner._partitions[1].held = HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
    observed = runner.status
    assert observed.state == RuntimeState.BLOCKED
    assert observed.reason == "activity_log_unavailable"
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

    async def complete(_snapshot, identity, _record, *, admission_guard) -> ResolvedDelivery:
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


async def test_revocation_preserves_known_content_gate_after_partition_state_is_removed(harness) -> None:
    runner = harness.runner
    state = runner._partitions[0]
    state.held = HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
    await runner.on_partitions_revoked(frozenset({0}), state.epoch)
    assert 0 not in runner._partitions
    assert runner.status.permanent_content_error
    assert runner._accepting_work()  # The healthy sibling remains independent.
    await runner._enqueue({1: [event(harness, 41, partition=1)]}, harness.client.epoch)
    await runner._advance(runner._partitions[1])
    assert runner._partitions[1].resolved_next_offset == 42
    await runner.stop()
    assert runner.status.permanent_content_error


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
    await runner._commit_positions((state,))
    assert state.held is None
    eligible = processing.admission_eligible
    assert isinstance(eligible, AsyncMock)
    eligible.assert_not_awaited()
    admission.lookup_execution.assert_not_awaited()
    admission.recover_accepted.assert_not_awaited()
    assert context.session.mock_calls == []
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
    harness.client.seek.assert_awaited_with(2, 5, expected_epoch=7)

    admission.recover_accepted.return_value = terminal(context.identity)
    runner._start_due_tasks()
    assert state.task is not None
    await state.task
    await runner._enqueue({2: [record]}, 7)
    await runner._advance(state)
    admission.recover_accepted.assert_awaited_once_with(context.identity)
    admission.schedule.assert_awaited_once()
    assert admission.schedule.await_args.args[0].workflow_arguments() == arguments
    assert state.handoff is None
    await runner._commit_positions((state,))
    harness.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)


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
    earlier = record.model_copy(
        update={"value": b'{"count":0}', "source_metadata": record.source_metadata.model_copy(update={"offset": "41"})}
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
    state.held = None
    await runner._advance(state)
    refetched = earlier.model_copy(
        update={"source_metadata": earlier.source_metadata.model_copy(update={"offset": str(refetched_offset)})}
    )
    admission.recover_accepted.side_effect = [retry, terminal(attempted_identity)]
    await runner._enqueue({2: [refetched]}, 7)
    await runner._advance(state)
    assert state.handoff is not None
    assert state.handoff.workflow_arguments() == arguments
    assert state.resolved_next_offset == 42
    await runner._commit_positions((state,))
    assert all(call.args == ({2: 42},) for call in harness.client.commit.await_args_list)

    state.held = None
    await runner._enqueue({2: [refetched]}, 7)
    await runner._advance(state)
    assert state.handoff is None
    assert list(state.records) == [refetched]
    assert state.resolved_next_offset == 42
    await runner._advance(state)
    admission.schedule.assert_awaited_once()
    assert admission.schedule.await_args.args[0].workflow_arguments() == arguments
    assert [call.args[0] for call in admission.recover_accepted.await_args_list] == [attempted_identity] * 2
    admission.lookup_execution.assert_awaited_once_with(attempted_identity)
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
    assert state.handoff is prepared
    assert state.resolved_next_offset is None
    harness.client.commit.assert_not_awaited()
    admission.schedule.assert_not_awaited()


@pytest.mark.parametrize("refetched_offset", [3, 6], ids=["earlier-boundary", "boundary-skips-handoff"])
async def test_gap_recovery_preserves_handoff_for_divergent_refetch(harness, monkeypatch, refetched_offset) -> None:
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
    assert state.content_gate_unknown
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
