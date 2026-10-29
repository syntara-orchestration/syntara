"""Actual runner/cache integration with isolated PostgreSQL, Redis and Temporal ports."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from syntara.core.config.base import get_settings
from syntara.eventstreams.adapters import kafka_record_runner as runner_module
from syntara.eventstreams.adapters.kafka_consumer import KafkaPartitionConsumer
from syntara.eventstreams.adapters.kafka_delivery_reader import KafkaDeliveryReader
from syntara.eventstreams.adapters.kafka_initial_position import InitializationKind, PositionResult, PositionStatus
from syntara.eventstreams.adapters.kafka_initial_position_service import KafkaInitialPositionService
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.core.deduplication import DeliveryIdentity, DeliveryState, TerminalProofStorage
from syntara.eventstreams.core.envelope import RawEvent
from syntara.eventstreams.core.handler import BlockedDelivery, ResolvedDelivery, SchedulingFailureCode
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.core.processing import CONTENT_INSPECTION_PENDING, HeldRecord, PendingContentFailure
from syntara.eventstreams.core.serialization import JsonEventDecoder
from syntara.eventstreams.core.terminal_proof import TerminalProof
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services import delivery_cache, delivery_cache_auth
from syntara.eventstreams.services.delivery_cache import EventDeliveryTerminalLookup
from syntara.eventstreams.services.delivery_cache_auth import sign_terminal_proof
from syntara.eventstreams.services.record_processing_service import EventRecordProcessingService
from tests.unit.eventstreams.test_kafka_initial_positions import Harness as PositionHarness
from tests.unit.eventstreams.test_record_processing_service import processing_context, retained, terminal
from tests.unit.eventstreams.test_terminal_proof import NOW, policy, proof


@dataclass
class Gate:
    """Test-only shared gate; process composition owns the real reconciler/leases."""

    placement_trusted: bool = True
    placement_expires_at: float = float("inf")
    durable_available: bool = True
    source_verified: bool = True
    recovery_open: bool = True
    failures: int = 0

    def admission_open(self, snapshot: SubscriptionSnapshot) -> bool:
        return self.placement_trusted and asyncio.get_running_loop().time() < self.placement_expires_at

    def resolution_open(self, snapshot: SubscriptionSnapshot) -> bool:
        return self.durable_available and self.source_verified and self.recovery_open

    def dependency_failed(self, snapshot: SubscriptionSnapshot) -> None:
        self.durable_available = False
        self.failures += 1


def signed(identity: DeliveryIdentity, **changes: object) -> str:
    """Authenticate complete historical evidence for the actual requested identity."""
    value = TerminalProof.model_validate(
        {
            **proof().model_dump(),
            "identity": identity,
            "identity_digest": identity.digest,
            "execution_id": identity.execution_id,
            "temporal_workflow_id": identity.temporal_workflow_id,
            **changes,
        }
    )
    return sign_terminal_proof(value).model_dump_json()


def record(context: SimpleNamespace, offset: int = 5, partition: int = 2, value: bytes = b"invalid") -> RawEvent:
    original: RawEvent = context.record
    return original.model_copy(
        update={
            "value": value,
            "source_metadata": original.source_metadata.model_copy(
                update={"offset": str(offset), "partition": partition}
            ),
        }
    )


@pytest_asyncio.fixture
async def cached_runner(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SimpleNamespace]:
    context, _, admission, original = processing_context(monkeypatch)
    settings = get_settings().model_copy(update={"event_drain_timeout_seconds": 1, "event_fetch_timeout_ms": 1})
    monkeypatch.setattr(runner_module, "get_settings", lambda: settings)
    monkeypatch.setattr(delivery_cache_auth, "_derive_signing_key", lambda: b"test-only-runner-proof-key")
    monkeypatch.setattr(delivery_cache, "EventDeliveryStore", lambda _session: context.store)
    factory = MagicMock(return_value=context.session)
    storage = AsyncMock(spec=TerminalProofStorage)
    storage.get.return_value = signed(context.identity)
    lookup = EventDeliveryTerminalLookup(factory, cache=storage, policy=policy(), now=lambda: NOW)
    monkeypatch.setattr(lookup, "lookup", AsyncMock(wraps=lookup.lookup))
    gate = Gate()
    decoder = MagicMock(spec=JsonEventDecoder, wraps=JsonEventDecoder())
    context.service.prepare_delivery = AsyncMock(wraps=context.service.prepare_delivery)
    processing = EventRecordProcessingService(
        factory, context.service, admission, decoder=decoder, lookup=lookup, gate=gate
    )
    terminal_result = MagicMock(wraps=processing._terminal)
    monkeypatch.setattr(processing, "_terminal", terminal_result)
    client = MagicMock(spec=KafkaPartitionConsumer)
    client.topic = context.snapshot.configuration.topic
    client.group_id = context.snapshot.configuration.group_id
    client.epoch, client.assignment = 7, frozenset({2})
    client.fetch.return_value = {}
    positions = MagicMock(spec=KafkaInitialPositionService)
    positions.initialize.side_effect = lambda request: PositionResult(
        status=PositionStatus.READY, next_offset=0, assignment_epoch=request.assignment_epoch
    )
    deliveries = MagicMock(spec=KafkaDeliveryReader)
    deliveries.first_pending.return_value = None
    deliveries.has_content_gate.return_value = False
    runner = runner_module.KafkaRecordRunner(
        context.snapshot,
        client,
        factory,
        context.service,
        admission,
        owner_worker_id="worker",
        processing=processing,
        positions=positions,
        deliveries=deliveries,
        lookup=lookup,
        gate=gate,
    )
    await runner.start()
    await runner.on_partitions_assigned(client.assignment, client.epoch)
    await runner._advance(runner._partitions[2])
    assert runner.ready_partitions == frozenset({2})
    # Warm reconciliation is permitted to use PostgreSQL. Everything after
    # this boundary measures the actual admitted duplicate path.
    for port in (
        factory,
        context.session,
        context.store,
        context.service.prepare_delivery,
        admission,
        positions,
        deliveries,
        client,
    ):
        port.reset_mock()
    yield SimpleNamespace(
        runner=runner,
        client=client,
        context=context,
        processing=processing,
        admission=admission,
        decoder=decoder,
        factory=factory,
        storage=storage,
        lookup=lookup,
        gate=gate,
        positions=positions,
        deliveries=deliveries,
        record=original,
        terminal_result=terminal_result,
    )
    await runner.stop()


async def test_warmed_actual_runner_hits_skip_all_per_record_postgresql_and_temporal(cached_runner) -> None:
    context = cached_runner
    runner = context.runner
    records = [record(context, offset) for offset in [5, 8, 12]]
    encoded = {runner._identity(item).digest: signed(runner._identity(item)) for item in records}
    context.storage.get.side_effect = lambda key: encoded[key.rsplit(":", 1)[-1]]
    await runner._enqueue({2: records}, 7)
    state = runner._partitions[2]
    for _ in records:
        await runner._tick()
        await state.task
    await runner._commit_positions((state,))

    assert not state.records
    assert context.client.commit.await_args_list[-1].args == ({2: 13},)
    assert context.storage.get.await_count == 3
    assert all(call.args[0].temporal_run_id == "confirmed-run" for call in context.terminal_result.call_args_list)
    context.factory.assert_not_called()
    context.context.session.get.assert_not_awaited()
    context.context.session.exec.assert_not_awaited()
    context.context.session.execute.assert_not_awaited()
    context.context.store.acquire.assert_not_awaited()
    context.context.store.acquire_inspection.assert_not_awaited()
    context.context.service.prepare_delivery.assert_not_awaited()
    context.admission.schedule.assert_not_awaited()
    context.decoder.decode.assert_not_called()
    context.deliveries.first_pending.assert_not_awaited()
    context.deliveries.has_content_gate.assert_not_awaited()
    context.positions.initialize.assert_not_awaited()


@pytest.mark.parametrize("failure", [RedisError(), OSError(), TimeoutError(), ValueError()])
async def test_lookup_errors_fall_back_to_postgresql_without_invalidating_gate(cached_runner, failure) -> None:
    context = cached_runner
    context.lookup.lookup.side_effect = failure
    original = terminal(context.context.identity).terminal
    context.context.store.lookup_terminal.return_value = original
    await context.runner._enqueue({2: [record(context)]}, 7)
    state = context.runner._partitions[2]
    await context.runner._advance(state)
    await context.runner._commit_positions((state,))

    context.lookup.lookup.assert_awaited_once_with(context.context.identity)
    context.context.store.lookup_terminal.assert_awaited_once_with(context.context.identity)
    context.factory.assert_called_once()
    context.terminal_result.assert_called_once_with(original)
    assert context.gate.durable_available
    assert context.gate.failures == 0
    context.decoder.decode.assert_not_called()
    context.context.service.prepare_delivery.assert_not_awaited()
    context.admission.schedule.assert_not_awaited()
    context.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)


async def test_database_failure_after_lookup_error_still_invalidates_gate(cached_runner) -> None:
    context = cached_runner
    context.lookup.lookup.side_effect = OSError("cache unavailable")
    context.context.store.lookup_terminal.side_effect = SQLAlchemyError("database unavailable")
    await context.runner._enqueue({2: [record(context)]}, 7)
    state = context.runner._partitions[2]
    await context.runner._advance(state)
    await context.runner._commit_positions((state,))
    context.context.store.lookup_terminal.assert_awaited_once_with(context.context.identity)
    assert not context.gate.durable_available
    assert context.gate.failures == 1
    context.client.commit.assert_not_awaited()
    context.decoder.decode.assert_not_called()


async def test_lookup_without_shared_gate_uses_postgresql_in_actual_runner(cached_runner) -> None:
    context = cached_runner
    context.runner._gate = None
    context.processing._gate = None
    context.context.store.lookup_terminal.return_value = terminal(context.context.identity).terminal
    await context.runner._enqueue({2: [record(context)]}, 7)
    state = context.runner._partitions[2]
    await context.runner._advance(state)
    await context.runner._commit_positions((state,))

    context.lookup.lookup.assert_not_awaited()
    context.storage.get.assert_not_awaited()
    context.context.store.lookup_terminal.assert_awaited_once_with(context.context.identity)
    context.factory.assert_called()
    context.decoder.decode.assert_not_called()
    context.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)


@pytest.mark.parametrize("with_gate", [False, True])
@pytest.mark.parametrize("hold", ["permanent", "pending", "unknown"])
async def test_prior_resolved_prefix_commits_after_a_later_content_hold(cached_runner, with_gate, hold) -> None:
    context = cached_runner
    if not with_gate:
        context.runner._gate = None
        context.processing._gate = None
        context.context.store.lookup_terminal.return_value = terminal(context.context.identity).terminal
    await context.runner._enqueue({2: [record(context)]}, 7)
    state = context.runner._partitions[2]
    await context.runner._advance(state)
    assert state.resolved_next_offset == 6

    later = record(context, 8)
    context.processing.process = AsyncMock(
        return_value=HeldRecord(reason="activity_log_unavailable", permanent_content_error=hold == "permanent")
    )
    await context.runner._enqueue({2: [later]}, 7)
    await context.runner._advance(state)
    if hold == "pending":
        state.pending_failure = PendingContentFailure(identity=context.runner._identity(later))
    elif hold == "unknown":
        state.content_gate_unknown = True

    assert state.held is not None
    assert state.reconciled_until == 0
    assert state.resolved_next_offset == 6
    await context.runner._commit_positions((state,))
    context.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)
    assert state.resolved_next_offset is None


@pytest.mark.parametrize("cached", ["expired", "identity", "epoch", "missing", "error"])
async def test_invalid_or_missing_proof_falls_back_to_original_database_outcome(cached_runner, cached) -> None:
    context = cached_runner
    identity = context.context.identity
    if cached == "expired":
        context.storage.get.return_value = signed(
            identity,
            resolved_at=NOW - timedelta(seconds=120),
            valid_until=NOW - timedelta(seconds=60),
            execution_confirmed_at=NOW - timedelta(seconds=120),
        )
    elif cached == "identity":
        context.storage.get.return_value = signed(identity.model_copy(update={"source_generation": 2}))
    elif cached == "epoch":
        context.storage.get.return_value = signed(identity, cache_epoch=uuid4())
    elif cached == "missing":
        context.storage.get.return_value = None
    else:
        context.storage.get.side_effect = OSError("redis unavailable")
    original = terminal(identity).terminal
    context.context.store.lookup_terminal.return_value = original
    await context.runner._enqueue({2: [record(context)]}, 7)
    state = context.runner._partitions[2]
    await context.runner._advance(state)
    await context.runner._commit_positions((state,))

    context.factory.assert_called()
    context.context.store.lookup_terminal.assert_awaited_once_with(identity)
    context.decoder.decode.assert_not_called()
    context.context.service.prepare_delivery.assert_not_awaited()
    context.admission.schedule.assert_not_awaited()
    context.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)


async def test_cancelled_database_outcome_is_never_a_cached_proof(cached_runner) -> None:
    context = cached_runner
    context.storage.get.return_value = None
    context.context.store.lookup_terminal.return_value = terminal(
        context.context.identity, DeliveryState.CANCELLED
    ).terminal
    await context.runner._enqueue({2: [record(context)]}, 7)
    state = context.runner._partitions[2]
    await context.runner._advance(state)
    await context.runner._commit_positions((state,))
    context.factory.assert_called()
    context.storage.put.assert_not_awaited()
    context.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)
    context.decoder.decode.assert_not_called()


async def test_miss_recovers_frozen_preparation_without_decoding_redelivery(cached_runner) -> None:
    context = cached_runner
    prepared = await context.context.prepare()
    assert isinstance(prepared, PreparedExecution)
    context.context.rows[EventDelivery] = retained(context.context.identity, frozen_binding=prepared.claim.binding)
    context.context.store.acquire.side_effect = None
    context.context.store.acquire.return_value = prepared.claim
    context.context.service.prepare_delivery.reset_mock()
    context.storage.get.return_value = None
    await context.runner._enqueue({2: [record(context)]}, 7)
    await context.runner._advance(context.runner._partitions[2])
    context.context.service.prepare_delivery.assert_awaited_once_with(
        context.runner.snapshot, context.context.identity, None, "worker"
    )
    context.admission.schedule.assert_awaited_once()
    context.decoder.decode.assert_not_called()


async def test_frozen_repair_needs_neither_placement_nor_consumer_ownership(cached_runner) -> None:
    context = cached_runner
    prepared = await context.context.prepare()
    assert isinstance(prepared, PreparedExecution)
    context.context.rows[EventDelivery] = retained(context.context.identity, frozen_binding=prepared.claim.binding)
    context.context.store.acquire.side_effect = None
    context.context.store.acquire.return_value = prepared.claim
    context.gate.placement_trusted = False
    context.client.assignment = frozenset()
    result = await context.processing.process(context.runner.snapshot, context.context.identity, None, "worker")
    assert isinstance(result, ResolvedDelivery)
    context.admission.schedule.assert_awaited_once()
    context.storage.get.assert_not_awaited()
    context.decoder.decode.assert_not_called()
    context.client.commit.assert_not_awaited()


async def test_rejected_database_outcome_stays_held_without_activity_log(cached_runner) -> None:
    context = cached_runner
    context.storage.get.return_value = None
    context.context.store.lookup_terminal.return_value = terminal(
        context.context.identity, DeliveryState.REJECTED
    ).terminal
    await context.runner._enqueue({2: [record(context)]}, 7)
    state = context.runner._partitions[2]
    await context.runner._advance(state)
    await context.runner._commit_positions((state,))
    assert state.held.permanent_content_error
    context.storage.put.assert_not_awaited()
    context.decoder.decode.assert_not_called()
    context.admission.schedule.assert_not_awaited()
    context.client.commit.assert_not_awaited()


async def test_pending_preparation_blocks_a_later_cached_record(cached_runner) -> None:
    context = cached_runner
    prepared = await context.context.prepare()
    assert isinstance(prepared, PreparedExecution)
    context.context.rows[EventDelivery] = retained(context.context.identity, frozen_binding=prepared.claim.binding)
    context.context.store.acquire.side_effect = None
    context.context.store.acquire.return_value = prepared.claim
    context.admission.schedule.return_value = BlockedDelivery(error_code=SchedulingFailureCode.TEMPORAL_UNAVAILABLE)
    context.deliveries.first_pending.return_value = context.context.identity
    state = context.runner._partitions[2]
    state.reconciled_until = 0
    await context.runner._enqueue({2: [record(context, 8)]}, 7)
    await context.runner._advance(state)
    await context.runner._commit_positions((state,))
    assert state.held is not None
    context.admission.schedule.assert_awaited_once()
    context.storage.get.assert_not_awaited()
    context.client.commit.assert_not_awaited()


@pytest.mark.parametrize("closed", ["database", "source", "recovery"])
async def test_shared_gate_blocks_cached_advancement_without_a_database_probe(cached_runner, closed) -> None:
    context = cached_runner
    state = context.runner._partitions[2]
    await context.runner._enqueue({2: [record(context)]}, 7)
    attribute = {"database": "durable_available", "source": "source_verified", "recovery": "recovery_open"}[closed]
    setattr(context.gate, attribute, False)
    await context.runner._advance(state)
    await context.runner._commit_positions((state,))
    context.storage.get.assert_not_awaited()
    context.factory.assert_not_called()
    context.client.commit.assert_not_awaited()


@pytest.mark.parametrize("gate_kind", ["unknown", "permanent", "administrative", "expired_reconciliation"])
async def test_partition_gates_cannot_be_bypassed_by_a_valid_proof(cached_runner, gate_kind) -> None:
    context = cached_runner
    state = context.runner._partitions[2]
    await context.runner._enqueue({2: [record(context)]}, 7)
    if gate_kind == "unknown":
        context.context.rows[EventDelivery] = retained(
            context.context.identity, last_error_code=CONTENT_INSPECTION_PENDING
        )
        state.content_gate_unknown = True
    elif gate_kind == "permanent":
        state.held = HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
        state.reconciled_until = 0
        context.deliveries.has_content_gate.return_value = True
    elif gate_kind == "administrative":
        state.fence = uuid4()
    else:
        state.reconciled_until = 0
        context.deliveries.has_content_gate.return_value = True
    await context.runner._advance(state)
    await context.runner._commit_positions((state,))
    context.storage.get.assert_not_awaited()
    context.admission.schedule.assert_not_awaited()
    context.client.commit.assert_not_awaited()


async def test_failed_required_write_closes_the_shared_gate_for_cached_commits(cached_runner) -> None:
    context = cached_runner
    context.client.assignment = frozenset({2, 3})
    await context.runner.on_partitions_assigned(context.client.assignment, 7)
    other = context.runner._partitions[3]
    await context.runner._advance(other)
    completed = record(context, 11, partition=3)
    context.storage.get.return_value = signed(context.runner._identity(completed))
    await context.runner._enqueue({3: [completed]}, 7)
    await context.runner._advance(other)
    assert other.resolved_next_offset == 12
    context.storage.get.return_value = None
    context.context.store.finish_inspection.side_effect = SQLAlchemyError("commit unavailable")
    await context.runner._enqueue({2: [record(context, value=b'{"count":2}')]}, 7)
    state = context.runner._partitions[2]
    await context.runner._advance(state)
    assert not context.gate.durable_available
    assert context.gate.failures == 1
    # The other partition's already validated proof cannot bypass this outage.
    await context.runner._commit_positions((state, other))
    context.client.commit.assert_not_awaited()
    assert context.context.rows[EventDelivery].last_error_code == CONTENT_INSPECTION_PENDING


async def test_stale_assignment_during_cache_read_prevents_late_commit(cached_runner) -> None:
    context = cached_runner

    async def read(_key: str) -> str:
        context.client.epoch = 8
        return signed(context.context.identity)

    context.storage.get.side_effect = read
    await context.runner._enqueue({2: [record(context)]}, 7)
    state = context.runner._partitions[2]
    await context.runner._advance(state)
    await context.runner._commit_positions((state,))
    assert state.resolved_next_offset is None
    context.factory.assert_not_called()
    context.client.commit.assert_not_awaited()


async def test_noncontiguous_completion_cannot_skip_the_received_head(cached_runner) -> None:
    context = cached_runner
    later = context.runner._identity(record(context, 8))
    context.processing.process = AsyncMock(return_value=terminal(later))
    await context.runner._enqueue({2: [record(context), record(context, 8)]}, 7)
    state = context.runner._partitions[2]
    await context.runner._advance(state)
    await context.runner._commit_positions((state,))
    assert state.held.reason == "evidence_mismatch"
    context.client.commit.assert_not_awaited()


@pytest.mark.parametrize("loss", ["expired", "untrusted"])
async def test_placement_loss_closes_new_records_and_pauses_fetching(cached_runner, loss) -> None:
    context = cached_runner
    if loss == "expired":
        context.gate.placement_expires_at = asyncio.get_running_loop().time()
    else:
        context.gate.placement_trusted = False
    await context.runner._tick()
    assert context.runner._closing
    assert all(state.closing and state.paused for state in context.runner._partitions.values())
    context.client.fetch.assert_not_awaited()
    context.factory.assert_not_called()
    context.storage.get.assert_not_awaited()


@pytest.mark.parametrize("still_assigned", [False, True])
async def test_local_placement_loss_port_drains_admitted_handoff_only_while_assigned(
    cached_runner, still_assigned
) -> None:
    context = cached_runner
    context.storage.get.return_value = None
    entered, release = asyncio.Event(), asyncio.Event()

    async def schedule(prepared: PreparedExecution) -> ResolvedDelivery:
        assert prepared.claim.binding is not None
        entered.set()
        await release.wait()
        return terminal(prepared.claim.identity)

    context.admission.schedule.side_effect = schedule
    await context.runner._enqueue({2: [record(context, value=b'{"count":2}'), record(context, 8)]}, 7)
    state = context.runner._partitions[2]
    state.task = asyncio.create_task(context.runner._advance(state))
    async with asyncio.timeout(2):
        await entered.wait()
        context.gate.placement_expires_at = asyncio.get_running_loop().time()
        closing = asyncio.create_task(context.runner.close_admission())
        await asyncio.sleep(0)
        if not still_assigned:
            context.client.epoch = 8
        release.set()
        await closing
    assert context.runner._closing
    context.admission.schedule.assert_awaited_once()
    if still_assigned:
        context.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)
        assert context.runner._identity(state.records[0]).record.offset == 8
    else:
        context.client.commit.assert_not_awaited()
    context.context.store.finalize_without_execution.assert_not_awaited()


async def test_known_database_outage_blocks_an_already_completed_cached_candidate(cached_runner) -> None:
    context = cached_runner
    await context.runner._enqueue({2: [record(context)]}, 7)
    state = context.runner._partitions[2]
    await context.runner._advance(state)
    assert state.resolved_next_offset == 6
    context.gate.durable_available = False
    await context.runner._commit_positions((state,))
    context.factory.assert_not_called()
    context.client.commit.assert_not_awaited()


async def test_administrative_fence_invalidates_shared_cached_candidates(cached_runner) -> None:
    context = cached_runner
    ready = context.runner._partitions[2]
    await context.runner._enqueue({2: [record(context)]}, 7)
    await context.runner._advance(ready)
    assert ready.resolved_next_offset == 6
    context.client.assignment = frozenset({2, 3})
    await context.runner.on_partitions_assigned(context.client.assignment, 7)
    recovery = context.runner._partitions[3]
    token = uuid4()
    await context.runner.close_and_drain(context.runner._request(recovery), token=token, boundary=20)
    assert recovery.fence == token
    assert not context.gate.resolution_open(context.runner.snapshot)
    await context.runner._commit_positions((ready,))
    context.client.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "reason",
    ["storage_unavailable", "source_recreated", "source_identity_unavailable", "waiting_for_source_recovery"],
)
async def test_initialization_failure_invalidates_other_partitions_cached_candidates(cached_runner, reason) -> None:
    context = cached_runner
    ready = context.runner._partitions[2]
    await context.runner._enqueue({2: [record(context)]}, 7)
    await context.runner._advance(ready)
    assert ready.resolved_next_offset == 6
    context.client.assignment = frozenset({2, 3})
    await context.runner.on_partitions_assigned(context.client.assignment, 7)
    context.positions.initialize.side_effect = lambda request: PositionResult(
        status=PositionStatus.BLOCKED, assignment_epoch=request.assignment_epoch, reason=reason
    )
    await context.runner._advance(context.runner._partitions[3])
    assert not context.gate.durable_available
    await context.runner._commit_positions((ready,))
    context.client.commit.assert_not_awaited()


async def test_discovered_lifecycle_change_closes_shared_cached_resolution(cached_runner) -> None:
    context = cached_runner
    ready = context.runner._partitions[2]
    await context.runner._enqueue({2: [record(context)]}, 7)
    await context.runner._advance(ready)
    context.context.subscription.paused = True
    assert not await context.processing.admission_eligible(context.runner.snapshot)
    assert not context.gate.durable_available
    await context.runner._commit_positions((ready,))
    context.client.commit.assert_not_awaited()


async def test_cache_population_error_does_not_undo_database_resolution(cached_runner) -> None:
    context = cached_runner
    context.storage.get.return_value = None
    context.storage.put.side_effect = OSError("redis unavailable")
    context.context.store.lookup_terminal.return_value = terminal(context.context.identity).terminal.model_copy(
        update={"resolved_at": NOW - timedelta(seconds=5), "execution_confirmed_at": NOW - timedelta(seconds=5)}
    )
    await context.runner._enqueue({2: [record(context)]}, 7)
    state = context.runner._partitions[2]
    await context.runner._advance(state)
    await context.runner._commit_positions((state,))
    context.storage.put.assert_awaited_once()
    assert context.gate.durable_available
    context.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)


async def test_placement_loss_deadline_retains_frozen_handoff_without_commit(cached_runner) -> None:
    context = cached_runner
    context.runner._settings.event_drain_timeout_seconds = 0.01
    context.storage.get.return_value = None
    entered = asyncio.Event()

    async def schedule(prepared: PreparedExecution) -> ResolvedDelivery:
        assert prepared.claim.binding is not None
        entered.set()
        await asyncio.Event().wait()
        return terminal(prepared.claim.identity)

    context.admission.schedule.side_effect = schedule
    await context.runner._enqueue({2: [record(context, value=b'{"count":2}')]}, 7)
    state = context.runner._partitions[2]
    state.task = asyncio.create_task(context.runner._advance(state))
    async with asyncio.timeout(2):
        await entered.wait()
        context.gate.placement_trusted = False
        await context.runner.close_admission()
    assert state.task.done()
    context.context.store.freeze.assert_awaited_once()
    context.context.store.finalize_without_execution.assert_not_awaited()
    context.client.commit.assert_not_awaited()


async def test_added_partition_initialization_does_not_reset_a_ready_partition(cached_runner) -> None:
    context = cached_runner
    ready = context.runner._partitions[2]
    context.client.epoch, context.client.assignment = 8, frozenset({2, 3})
    await context.runner.on_partitions_assigned(context.client.assignment, 8)
    assert context.runner.ready_partitions == frozenset({2})

    async def initialize(request) -> PositionResult:
        assert request.partition == 3
        return PositionResult(
            status=PositionStatus.BLOCKED,
            assignment_epoch=request.assignment_epoch,
            reason="committed_position_unavailable",
        )

    context.positions.initialize.side_effect = initialize
    await context.runner._advance(context.runner._partitions[3])
    assert context.runner.ready_partitions == frozenset({2})
    await context.runner._advance(context.runner._partitions[2])
    assert context.runner._partitions[2].ready == ready.ready
    context.positions.initialize.assert_awaited_once()
    context.runner._partitions[3].held = None
    context.positions.initialize.side_effect = lambda request: PositionResult(
        status=PositionStatus.READY, next_offset=20, assignment_epoch=request.assignment_epoch
    )
    await context.runner._advance(context.runner._partitions[3])
    assert context.runner.ready_partitions == frozenset({2, 3})
    assert context.runner._partitions[2].fence is None
    assert context.runner._partitions[3].fence is None


async def test_runner_consumes_first_and_added_partition_policies_from_initialization(cached_runner) -> None:
    context = cached_runner
    position = PositionHarness(initial_partition_ids=(0,), metadata_partition_ids=(0, 1))
    position.client.assignment = frozenset({0})
    snapshot = context.runner.snapshot.model_copy(
        update={
            "configuration": KafkaSourceConfiguration(
                topic="orders", group_id="syntara.test", initial_partition_ids=(0,)
            )
        }
    )
    processing = MagicMock(spec=EventRecordProcessingService)
    processing.admission_eligible.return_value = True
    runner = runner_module.KafkaRecordRunner(
        snapshot,
        position.client,
        MagicMock(),
        context.context.service,
        position.admission,
        owner_worker_id="worker",
        processing=processing,
        positions=position.service,
        deliveries=context.deliveries,
    )
    try:
        await runner.start()
        await runner.on_partitions_assigned(frozenset({0}), 7)
        await runner._advance(runner._partitions[0])
        assert runner.ready_partitions == frozenset({0})
        first = position.store.choose_initial.await_args_list[0]
        assert first.args[2] == position.end
        assert first.kwargs["initialization_kind"] == InitializationKind.FIRST_ACTIVATION
        # The isolated store now exposes the newly discovered partition only;
        # the already ready partition must never re-enter initialization.
        position.position = None
        position.committed = None
        position.client.assignment = frozenset({0, 1})
        await runner.on_partitions_assigned(frozenset({0, 1}), 7)
        await runner._advance(runner._partitions[1])
        assert runner.ready_partitions == frozenset({0, 1})
        assert position.store.choose_initial.await_count == 2
        added = position.store.choose_initial.await_args_list[1]
        assert added.args[2] == position.beginning
        assert added.kwargs["initialization_kind"] == InitializationKind.ADDED_PARTITION
        position.control.close_and_drain.assert_not_awaited()
        assert all(state.fence is None for state in runner._partitions.values())
    finally:
        await runner.stop()
