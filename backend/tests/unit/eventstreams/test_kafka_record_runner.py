"""Kafka runner orchestration and injected failures using isolated adapters."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from aiokafka.errors import AuthenticationFailedError, KafkaConnectionError, KafkaTimeoutError
from sqlalchemy.exc import SQLAlchemyError

from syntara.core.config.base import get_settings
from syntara.core.constants import EventStreamLimits
from syntara.eventstreams.adapters import kafka_record_runner as module
from syntara.eventstreams.adapters.kafka_committed_position import KafkaCommittedPositionVerifier
from syntara.eventstreams.adapters.kafka_consumer import KafkaPartitionConsumer
from syntara.eventstreams.adapters.kafka_delivery_reader import KafkaDeliveryReader
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
from syntara.eventstreams.core.deduplication import DeliveryState
from syntara.eventstreams.core.envelope import RawEvent, RawEventHeader
from syntara.eventstreams.core.handler import ResolvedDelivery
from syntara.eventstreams.core.processing import CONTENT_INSPECTION_PENDING, HeldRecord, InspectedRecord
from syntara.eventstreams.core.results import EventDecodeFailure, EventFailureCode
from syntara.eventstreams.core.runtime import RuntimeState, SubscriptionRuntimeError
from syntara.eventstreams.core.serialization import JsonEventDecoder
from syntara.eventstreams.exceptions import KafkaTransportError
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.services.admission_service import EventAdmissionService
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.eventstreams.services.record_processing_service import EventRecordProcessingService
from tests.unit.eventstreams.test_connection_provider import connection_context
from tests.unit.eventstreams.test_record_processing_service import processing_context, retained, terminal


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
    processing.process.side_effect = lambda _snapshot, identity, _event, _owner: terminal(identity)
    processing.hold_content_failure.return_value = HeldRecord(
        reason="activity_log_unavailable", permanent_content_error=True
    )

    def inspect(_snapshot, identity, record, _owner) -> HeldRecord | InspectedRecord:
        decoded = JsonEventDecoder().decode(record)
        return (
            HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
            if isinstance(decoded, EventDecodeFailure)
            else InspectedRecord(identity=identity)
        )

    processing.inspect_only.side_effect = inspect
    deliveries = MagicMock(spec=KafkaDeliveryReader)
    deliveries.first_pending.return_value = None
    deliveries.has_content_gate.return_value = False
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
        owner_worker_id="worker",
        processing=processing,
        positions=positions,
        deliveries=deliveries,
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
        deliveries=deliveries,
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


async def test_prepared_recovery_precedes_initialization_and_later_record(harness) -> None:
    runner = harness.runner
    state = runner._partitions[0]
    state.ready = False
    pending = runner._identity(event(harness, 41))
    harness.deliveries.first_pending.side_effect = [pending, None]
    trace = []

    async def process(_snapshot, identity, record, _owner) -> ResolvedDelivery:
        trace.append("recover" if record is None else "record")
        return terminal(identity)

    async def initialize(request) -> PositionResult:
        trace.append("initialize")
        return PositionResult(status=PositionStatus.READY, next_offset=44, assignment_epoch=request.assignment_epoch)

    harness.processing.process.side_effect = process
    harness.positions.initialize.side_effect = initialize
    await runner._enqueue({0: [event(harness, 44)]}, 7)
    await runner._advance(state)
    assert trace == ["recover", "initialize", "record"]
    assert state.resolved_next_offset == 45
    harness.client.commit.assert_not_awaited()


async def test_repair_without_delivered_record_does_not_create_commit_position(harness) -> None:
    runner = harness.runner
    identity = runner._identity(event(harness, 41))
    harness.deliveries.first_pending.side_effect = [identity, None]
    harness.processing.admission_eligible.return_value = False
    await runner._advance(runner._partitions[0])
    harness.processing.process.assert_awaited_once_with(runner.snapshot, identity, None, "worker")
    await runner._commit_positions(tuple(runner._partitions.values()))
    harness.client.commit.assert_not_awaited()
    assert runner._partitions[0].held.reason == "admission_closed"


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
        harness.runner.snapshot, harness.runner._identity(event(harness, 41)), None, "worker"
    )
    harness.processing.hold_content_failure.assert_not_awaited()
    harness.client.seek.assert_awaited_once_with(0, 41, expected_epoch=7)
    harness.client.commit.assert_not_awaited()


async def test_busy_partition_releases_queue_capacity_and_healthy_partition_continues(harness) -> None:
    runner = harness.runner

    async def process(_snapshot, identity, _record, _owner) -> ResolvedDelivery | HeldRecord:
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

    async def process(_snapshot, identity, _record, _owner) -> ResolvedDelivery:
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

    async def process(_snapshot, identity, _record, _owner) -> ResolvedDelivery:
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
    pending = runner._identity(event(harness, 41))
    harness.deliveries.first_pending.return_value = pending
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
    assert isinstance(runner.retention.verifier, KafkaCommittedPositionVerifier)


async def test_recovery_fence_discards_commit_candidates_and_unknown_evidence_blocks(harness) -> None:
    runner = harness.runner
    state = runner._partitions[0]
    state.resolved_next_offset = 100
    token = uuid4()
    request = runner._request(state)
    harness.deliveries.has_content_gate.side_effect = OSError("unavailable")
    evidence = await runner.close_and_drain(request, token=token, boundary=50)
    assert evidence.permanent_content_error
    assert not evidence.retained_evidence_complete
    assert await runner.is_fenced(request, token=token)
    await runner._commit_positions((state,))
    harness.client.commit.assert_not_awaited()
    harness.processing.admission_eligible.return_value = False
    assert not await runner.resume_after_recovery(request, token=token)
    harness.processing.admission_eligible.return_value = True
    assert not await runner.resume_after_recovery(request, token=token)
    harness.deliveries.has_content_gate.side_effect = None
    harness.deliveries.has_content_gate.return_value = False
    assert await runner.resume_after_recovery(request, token=token)
    assert not await runner.is_fenced(request, token=token)


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
    await harness.runner._tick()
    assert harness.client.fetch.await_args.args[0] == []
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


async def test_rejected_resolution_cannot_authorize_commit_even_from_an_adapter(harness) -> None:
    runner = harness.runner
    record = event(harness, 41)
    harness.processing.process.side_effect = None
    harness.processing.process.return_value = terminal(runner._identity(record), DeliveryState.REJECTED)
    await runner._enqueue({0: [record]}, 7)
    await runner._advance(runner._partitions[0])
    assert runner._partitions[0].held.permanent_content_error
    await runner.drain()
    harness.client.commit.assert_not_awaited()


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

    async def process(_snapshot, identity, _event, _owner) -> ResolvedDelivery:
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
            await asyncio.sleep(0)  # Fresh eligibility closes while cached eligibility allowed fetch.
        offset = cursor
        cursor = 90 if cursor == 44 else 91
        return {0: [event(harness, offset)]} if offset < 91 else {}

    async def seek(_partition, offset, **_kwargs: object) -> None:
        nonlocal cursor
        cursor = offset

    async def process(_snapshot, identity, _event, _owner) -> ResolvedDelivery:
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
    service = KafkaInitialPositionService(MagicMock(), harness.client, MagicMock(), runner)
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


async def test_oversized_content_stages_bounded_evidence_and_persists_before_gate_release(harness) -> None:
    runner = harness.runner
    record = event(harness, 41, value=b"x" * (harness.settings.event_queue_max_bytes + 1))
    await runner._enqueue({0: [record, event(harness, 90)]}, 7)
    state = runner._partitions[0]
    assert runner.queued_bytes == 0
    assert runner.queued_records == 0
    harness.processing.inspect_only.assert_awaited_once_with(
        runner.snapshot, runner._identity(record), record, "worker"
    )
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
    service = KafkaInitialPositionService(MagicMock(), harness.client, MagicMock(), runner)
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


async def test_real_processing_service_retains_oversized_gate_across_local_restart(harness, monkeypatch) -> None:
    context, processing, admission, _ = processing_context(monkeypatch)
    runner = harness.runner
    runner.snapshot = context.snapshot
    runner._processing = processing
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    state = runner._partitions[2]
    state.ready = state.eligible = True

    async def defer(claim, *, next_attempt_at: datetime, error_code: str) -> None:
        assert claim.identity == context.identity
        context.rows[EventDelivery] = retained(
            context.identity, last_error_code=error_code, next_attempt_at=next_attempt_at
        )

    context.store.defer.side_effect = defer
    record = RawEvent(
        value=b"x" * (harness.settings.event_queue_max_bytes + 1),
        source_metadata=context.envelope.source_metadata,
    )
    await runner._enqueue({2: [record]}, 7)
    await runner._advance(state)
    assert state.held.permanent_content_error
    assert context.rows[EventDelivery].last_error_code == EventFailureCode.value_too_large.value
    assert context.events[-1] == "commit"
    await runner.on_partitions_revoked(frozenset({2}), 7)
    runner._processing = EventRecordProcessingService(lambda: context.session, context.service, admission)
    harness.deliveries.first_pending.return_value = context.identity
    harness.deliveries.has_content_gate.return_value = True
    await runner.on_partitions_assigned(frozenset({2}), 7)
    restarted = runner._partitions[2]
    await runner._advance(restarted)
    assert restarted.held.permanent_content_error
    harness.positions.initialize.assert_not_awaited()
    assert context.store.defer.await_count == 1
    evidence = await runner.close_and_drain(runner._request(restarted), token=uuid4(), boundary=91)
    assert evidence.permanent_content_error
    await runner.stop()
    admission.schedule.assert_not_awaited()
    harness.client.commit.assert_not_awaited()


@pytest.mark.parametrize("decision", [DeliveryState.SCHEDULED, DeliveryState.FILTERED, DeliveryState.CANCELLED])
async def test_oversized_terminal_redelivery_resolves_without_retaining_payload(harness, decision) -> None:
    runner = harness.runner
    record = event(harness, 41, value=b"x" * (harness.settings.event_queue_max_bytes + 1))
    identity = runner._identity(record)
    harness.processing.inspect_only.side_effect = None
    harness.processing.inspect_only.return_value = terminal(identity, decision)
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


@pytest.mark.parametrize("failure", ["rejected", "mismatched", "exhausted"])
async def test_oversized_terminal_evidence_must_match_a_committable_identity(harness, failure) -> None:
    runner = harness.runner
    offset = MAX_POSITION_OFFSET if failure == "exhausted" else 41
    record = event(harness, offset, value=b"x" * (harness.settings.event_queue_max_bytes + 1))
    identity = runner._identity(event(harness, 44) if failure == "mismatched" else record)
    decision = DeliveryState.REJECTED if failure == "rejected" else DeliveryState.SCHEDULED
    harness.processing.inspect_only.side_effect = None
    harness.processing.inspect_only.return_value = terminal(identity, decision)
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
    harness.processing.process.assert_awaited_once_with(runner.snapshot, runner._identity(record), None, "worker")
    harness.processing.hold_content_failure.assert_not_awaited()
    harness.client.commit.assert_awaited_once_with({0: 42}, expected_epoch=7)


async def test_completion_behind_recovery_fence_cannot_restore_old_commit_position(harness) -> None:
    runner = harness.runner
    entered, release = asyncio.Event(), asyncio.Event()

    async def process(_snapshot, identity, _record, _owner) -> ResolvedDelivery:
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


@pytest.mark.parametrize("operation", ["stop", "revoke"])
async def test_drain_persists_staged_content_before_worker_start_and_fresh_runner_blocks_recovery(
    harness, monkeypatch, operation
) -> None:
    context, processing, admission, _ = processing_context(monkeypatch)
    runner = harness.runner
    runner.snapshot = context.snapshot
    runner._processing = processing
    harness.client.group_id = context.snapshot.configuration.group_id
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)

    async def defer(claim, *, next_attempt_at: datetime, error_code: str) -> None:
        context.rows[EventDelivery] = retained(
            claim.identity, last_error_code=error_code, next_attempt_at=next_attempt_at
        )

    context.store.defer.side_effect = defer
    record = RawEvent(
        value=b"x" * (harness.settings.event_queue_max_bytes + 1),
        source_metadata=context.envelope.source_metadata,
    )
    await runner._enqueue({2: [record]}, 7)
    original = runner._partitions[2]
    assert original.task is None
    if operation == "revoke":
        await runner.on_partitions_revoked(frozenset({2}), 7)
        assert 2 not in runner._partitions
    await runner.stop()
    context.store.defer.assert_awaited_once()
    assert context.events[-1] == "commit"
    assert original.pending_failure is None
    harness.client.epoch = 8
    harness.deliveries.first_pending.return_value = context.identity
    harness.deliveries.has_content_gate.return_value = True
    restarted = KafkaRecordRunner(
        context.snapshot,
        harness.client,
        lambda: context.session,
        context.service,
        admission,
        owner_worker_id="new-worker",
        processing=EventRecordProcessingService(lambda: context.session, context.service, admission),
        positions=harness.positions,
        deliveries=harness.deliveries,
    )
    try:
        await restarted.start()
        await restarted.on_partitions_assigned(frozenset({2}), 8)
        state = restarted._partitions[2]
        await restarted._advance(state)
        assert state.held is not None
        assert state.held.permanent_content_error
        harness.positions.initialize.assert_not_awaited()
        request = RecoveryRequest(
            **restarted._request(state).model_dump(),
            expected_recovery_revision=0,
            policy=RecoveryPolicy.CURRENT_END,
            reason="administrator_recovery",
        )
        recovery = KafkaInitialPositionService(MagicMock(), harness.client, admission, restarted)
        with pytest.raises(KafkaPositionError, match="permanent_content_error"):
            await recovery._drain(request, uuid4(), 91)
        admission.schedule.assert_not_awaited()
        harness.client.commit.assert_not_awaited()
    finally:
        await restarted.stop()


async def test_staged_content_persistence_respects_shutdown_deadline(harness) -> None:
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


async def test_committed_inspection_marker_survives_failed_finalization_stop_and_restart(harness, monkeypatch) -> None:
    context, processing, admission, _ = processing_context(monkeypatch)
    context.store.finish_inspection.side_effect = SQLAlchemyError("unavailable")
    runner = harness.runner
    runner.snapshot = context.snapshot
    runner._processing = processing
    harness.client.group_id = context.snapshot.configuration.group_id
    harness.client.assignment = frozenset({2})
    await runner.on_partitions_assigned(frozenset({2}), 7)
    record = RawEvent(
        value=b"x" * (harness.settings.event_queue_max_bytes + 1),
        source_metadata=context.envelope.source_metadata,
    )
    await runner._enqueue({2: [record]}, 7)
    assert context.rows[EventDelivery].last_error_code == CONTENT_INSPECTION_PENDING
    assert not runner._partitions[2].held.permanent_content_error
    await runner.stop()
    assert context.rows[EventDelivery].last_error_code == CONTENT_INSPECTION_PENDING
    harness.client.epoch = 8
    harness.deliveries.has_content_gate.return_value = True
    restarted = KafkaRecordRunner(
        context.snapshot,
        harness.client,
        lambda: context.session,
        context.service,
        admission,
        owner_worker_id="new-worker",
        processing=processing,
        positions=harness.positions,
        deliveries=harness.deliveries,
    )
    try:
        await restarted.start()
        await restarted.on_partitions_assigned(frozenset({2}), 8)
        request = RecoveryRequest(
            **restarted._request(restarted._partitions[2]).model_dump(),
            expected_recovery_revision=0,
            policy=RecoveryPolicy.CURRENT_END,
            reason="administrator_recovery",
        )
        recovery = KafkaInitialPositionService(MagicMock(), harness.client, admission, restarted)
        with pytest.raises(KafkaPositionError, match="permanent_content_error"):
            await recovery._drain(request, uuid4(), 91)
        context.store.finalize_without_execution.assert_not_awaited()
        admission.schedule.assert_not_awaited()
        harness.client.commit.assert_not_awaited()
    finally:
        await restarted.stop()


@pytest.mark.parametrize("returned_offset", [41, 44])
async def test_pending_inspection_requires_its_exact_record_before_later_admission(harness, returned_offset) -> None:
    runner = harness.runner
    runner._work = asyncio.Semaphore(1)
    state = runner._partitions[0]
    identity = runner._identity(event(harness, 41))
    harness.deliveries.first_pending.side_effect = [identity, None]
    harness.processing.process.side_effect = None
    harness.processing.process.return_value = HeldRecord(reason=CONTENT_INSPECTION_PENDING)
    harness.client.fetch.return_value = {0: [event(harness, returned_offset)]}
    async with asyncio.timeout(1):
        await runner._advance(state)
    assert state.resolved_next_offset is None
    assert runner.queued_records == runner.queued_bytes == 0
    await runner._commit_positions((state,))
    harness.client.commit.assert_not_awaited()
    if returned_offset == 41:
        harness.positions.initialize.assert_awaited_once()
        harness.processing.inspect_only.assert_awaited_once()
        assert state.ready
    else:
        harness.positions.initialize.assert_not_awaited()
        harness.processing.inspect_only.assert_not_awaited()
        assert not state.ready
        assert state.held.reason == "inspection_record_unavailable"


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


async def test_public_status_waits_for_first_assignment_before_reporting_active(harness):
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
        owner_worker_id="assignment-review",
        processing=harness.processing,
        positions=harness.positions,
        deliveries=harness.deliveries,
    )

    try:
        await runner.start()
        assert runner.status.state == RuntimeState.STARTING
        harness.positions.initialize.assert_not_awaited()
        await runner.on_partitions_assigned(frozenset(), client.epoch)
        assert runner.status.state == RuntimeState.ACTIVE
        harness.positions.initialize.assert_not_awaited()
        client.epoch, client.assignment = 1, frozenset({0})
        await runner.on_partitions_assigned(client.assignment, client.epoch)
        assert runner.status.state == RuntimeState.STARTING
        await runner._advance(runner._partitions[0])
        harness.positions.initialize.assert_awaited_once()
        assert runner.status.state == RuntimeState.ACTIVE
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


async def test_persisted_recovery_dispatch_does_not_drain_its_own_shielded_caller(harness, monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from syntara.eventstreams.services.recovery_request_service import EventRecoveryRequestService

    runner = harness.runner
    state = runner._partitions[0]
    requests = MagicMock(spec=EventRecoveryRequestService)
    request = RecoveryRequest(
        **runner._request(state).model_dump(),
        expected_recovery_revision=0,
        policy=RecoveryPolicy.CURRENT_END,
        reason="offset_expired",
    )
    requests.read.return_value = request
    runner._recovery_requests = requests
    observations = []

    async def recover(value, *, owner_worker_id) -> PositionResult:
        assert value.assignment_epoch == harness.client.epoch
        assert owner_worker_id == "worker"

        async def shielded_operation() -> PositionResult:
            evidence = await runner.close_and_drain(value, token=uuid4(), boundary=0)
            observations.append(evidence)
            return PositionResult(status=PositionStatus.READY, assignment_epoch=value.assignment_epoch)

        return await asyncio.shield(asyncio.create_task(shielded_operation()))

    harness.positions.recover.side_effect = recover
    monkeypatch.setattr(runner, "resume_after_recovery", AsyncMock(return_value=True))
    state.control_task = asyncio.create_task(runner._recover_requested(state))
    await asyncio.wait_for(state.control_task, timeout=1)
    assert observations[0].quiescent
    requests.record.assert_awaited_once()
    assert requests.record.call_args.args[1].status == PositionStatus.READY


async def test_recovery_request_cannot_dispatch_after_assignment_loss(harness) -> None:
    from syntara.eventstreams.services.recovery_request_service import EventRecoveryRequestService

    runner = harness.runner
    state = runner._partitions[0]
    requests = MagicMock(spec=EventRecoveryRequestService)
    requests.read.return_value = RecoveryRequest(
        **runner._request(state).model_dump(),
        expected_recovery_revision=0,
        policy=RecoveryPolicy.CURRENT_END,
        reason="offset_expired",
    )
    runner._recovery_requests = requests
    harness.client.epoch += 1
    await runner._recover_requested(state)
    harness.positions.recover.assert_not_awaited()
    requests.record.assert_not_awaited()


async def test_revocation_preserves_known_content_gate_after_partition_state_is_removed(harness) -> None:
    runner = harness.runner
    state = runner._partitions[0]
    state.held = HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
    await runner.on_partitions_revoked(frozenset({0}), state.epoch)
    assert 0 not in runner._partitions
    assert runner.status.permanent_content_error
    assert not runner._accepting_work()
    await runner.stop()
    assert runner.status.permanent_content_error
