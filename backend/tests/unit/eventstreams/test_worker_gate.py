"""Process gate composition with actual runner/cache ports and isolated dependencies."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from syntara.eventstreams.adapters.kafka_initial_position import KafkaPartitionInitialPosition, PositionStatus
from syntara.eventstreams.adapters.kafka_initial_position_service import KafkaInitialPositionService
from syntara.eventstreams.core.handler import BlockedDelivery, ResolvedDelivery
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.services import admission_service as admission_module
from syntara.eventstreams.services.admission_service import EventAdmissionService
from syntara.eventstreams.services.worker_gate import EventWorkerGate
from syntara.eventstreams.services.worker_resources import EventWorkerResources
from tests.helpers.eventstream_worker import IsolatedPlacementPool, IsolatedPlacementService
from tests.unit.eventstreams import test_kafka_initial_positions as position_tests
from tests.unit.eventstreams import test_kafka_record_runner_cache as cache_tests
from tests.unit.eventstreams.test_admission_service import harness as admission_harness
from tests.unit.eventstreams.test_connection_provider import connection_context
from tests.unit.eventstreams.test_execution_preparation_service import preparation_context
from tests.unit.eventstreams.test_record_processing_service import terminal
from tests.unit.eventstreams.test_worker_resources import TrackingSessionFactory

cached_runner = cache_tests.cached_runner


async def gate_for(snapshot) -> SimpleNamespace:
    pool = IsolatedPlacementPool(snapshot.deployment_id, [snapshot.subscription_id])
    placement = IsolatedPlacementService(pool)
    await placement.heartbeat_worker(placement.worker, draining=False)
    await placement.claim_subscriptions(placement.worker, limit=1)
    clock = [100.0]
    gate = EventWorkerGate(placement, clock=lambda: clock[0])
    gate.membership_confirmed(160.0, generation=gate.generation)
    assert gate.reconciled([snapshot], set(), generation=gate.generation, started=100.0)
    return SimpleNamespace(gate=gate, placement=placement, clock=clock, snapshot=snapshot)


@pytest_asyncio.fixture
async def gate_context():
    return await gate_for(connection_context().snapshot)


async def test_gate_requires_current_lifecycle_membership_and_placement(gate_context):
    context = gate_context
    assert context.gate.admission_open(context.snapshot)
    changed = context.snapshot.model_copy(
        update={"configuration_revision": context.snapshot.configuration_revision + 1}
    )
    assert not context.gate.admission_open(changed)
    context.placement.authority(context.snapshot.subscription_id).invalidate()
    assert not context.gate.admission_open(context.snapshot)
    assert context.gate.resolution_open(context.snapshot)


async def test_membership_expiry_closes_intake_without_erasing_admitted_resolution(gate_context):
    context = gate_context
    context.clock[0] = 160.0
    assert not context.gate.admission_open(context.snapshot)
    assert context.gate.resolution_open(context.snapshot)
    context.gate.close_admission()
    assert context.gate.scheduling_open


async def test_reconciliation_cannot_clear_a_newer_required_write_failure(gate_context):
    context = gate_context
    generation = context.gate.generation
    context.gate.database_failed()
    assert not context.gate.reconciled([context.snapshot], set(), generation=generation, started=100.0)
    assert not context.gate.scheduling_open
    assert not context.gate.resolution_open(context.snapshot)
    assert not context.gate.reconciled(
        [context.snapshot], {context.snapshot.source_id}, generation=context.gate.generation, started=100.0
    )
    assert not context.gate.resolution_open(context.snapshot)


async def test_heartbeat_started_before_a_failure_cannot_restore_write_trust(gate_context):
    context = gate_context
    generation = context.gate.generation
    context.gate.database_failed()
    context.gate.membership_confirmed(160.0, generation=generation)
    assert not context.gate.reconciled([context.snapshot], set(), generation=context.gate.generation, started=100.0)
    assert not context.gate.cache_trusted()
    assert not context.gate.scheduling_open


async def test_actual_cached_hit_cannot_commit_after_shared_database_outage(cached_runner):
    context = cached_runner
    shared = await gate_for(context.context.snapshot)
    context.runner._gate = shared.gate
    context.processing._gate = shared.gate
    context.lookup._clock_is_safe = shared.gate.cache_trusted
    await context.runner._enqueue({2: [cache_tests.record(context)]}, 7)
    state = context.runner._partitions[2]
    await context.runner._advance(state)
    assert state.resolved_next_offset == 6
    context.storage.get.assert_awaited_once()
    shared.gate.database_failed()
    # Successful authoritative SELECTs do not prove required writes recovered.
    for _ in range(2):
        assert not shared.gate.reconciled([shared.snapshot], set(), generation=shared.gate.generation, started=100.0)
        await context.runner._commit_positions((state,))
    assert not shared.gate.cache_trusted()
    assert not shared.gate.scheduling_open
    await context.runner._commit_positions((state,))
    context.client.commit.assert_not_awaited()
    context.factory.assert_not_called()
    context.admission.schedule.assert_not_awaited()
    shared.gate.membership_confirmed(160.0, generation=shared.gate.generation)
    assert not shared.gate.scheduling_open
    assert shared.gate.reconciled([shared.snapshot], set(), generation=shared.gate.generation, started=100.0)
    assert shared.gate.cache_trusted()
    assert shared.gate.scheduling_open


async def test_redis_failure_uses_database_fallback_without_closing_shared_gate(cached_runner):
    context = cached_runner
    shared = await gate_for(context.context.snapshot)
    context.runner._gate = shared.gate
    context.processing._gate = shared.gate
    context.lookup._clock_is_safe = shared.gate.cache_trusted
    context.storage.get.side_effect = RedisError("isolated unavailable cache")
    context.context.store.lookup_terminal.return_value = terminal(context.context.identity).terminal
    await context.runner._enqueue({2: [cache_tests.record(context)]}, 7)
    state = context.runner._partitions[2]
    await context.runner._advance(state)
    await context.runner._commit_positions((state,))
    assert shared.gate.resolution_open(context.context.snapshot)
    assert context.factory.call_count > 0
    context.client.commit.assert_awaited_once_with({2: 6}, expected_epoch=7)


async def test_failed_confirmation_write_closes_gate_even_when_acceptance_is_recovered(gate_context, monkeypatch):
    context = preparation_context(monkeypatch)
    prepared = await context.prepare()
    sessions = TrackingSessionFactory()
    resources = EventWorkerResources(gate_context.gate)
    service = EventAdmissionService(sessions, MagicMock(), resources=resources)
    retained = terminal(prepared.claim.identity).terminal
    store = SimpleNamespace(
        finalize_scheduled=AsyncMock(side_effect=SQLAlchemyError("isolated write failure")),
        lookup_terminal=AsyncMock(return_value=retained),
        record_acceptance=AsyncMock(),
    )
    monkeypatch.setattr(admission_module, "EventDeliveryStore", lambda _session: store)
    result = await service._confirm(prepared, MagicMock())
    assert isinstance(result, ResolvedDelivery)
    assert not gate_context.gate.scheduling_open
    assert not gate_context.gate.resolution_open(gate_context.snapshot)
    assert not sessions.active
    assert not sessions.transactions


async def test_recovery_hold_allows_frozen_repair_before_hold_release(monkeypatch):
    context = preparation_context(monkeypatch)
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    shared = await gate_for(context.snapshot)
    service, launcher, _ = admission_harness(prepared, monkeypatch)
    service._resources = EventWorkerResources(shared.gate)
    positions = position_tests.Harness(position=position_tests.row(gap=True))
    positions.store.reconcile_claims.return_value = [prepared.claim]

    async def begin(request) -> KafkaPartitionInitialPosition:
        result: KafkaPartitionInitialPosition = await positions.begin_recovery(request)
        assert shared.gate.reconciled(
            [context.snapshot], {context.snapshot.source_id}, generation=shared.gate.generation, started=100.0
        )
        assert shared.gate.transport_open(context.snapshot)
        assert not shared.gate.admission_open(context.snapshot)
        assert not shared.gate.resolution_open(context.snapshot)
        return result

    async def confirm(request, token, boundary) -> None:
        assert positions.held
        service._confirm.assert_awaited_once()
        launcher.start.assert_awaited_once()
        await positions.confirm_recovery(request, token, boundary)

    positions.store.begin_recovery.side_effect = begin
    positions.store.confirm_recovery.side_effect = confirm
    recovery = KafkaInitialPositionService(
        positions.store, positions.client, service, positions.control, cache_coordination=positions.cache_coordination
    )
    request = position_tests.recovery().model_copy(update={"source_id": context.snapshot.source_id})
    result = await recovery.recover(request, owner_worker_id=prepared.claim.owner_worker_id)
    assert result.status == PositionStatus.READY
    assert not positions.held
    positions.store.stage_recovery.assert_awaited_once()
    positions.store.confirm_recovery.assert_awaited_once()
    service._reload.assert_awaited_once_with(prepared.claim)
    # Clearing the durable hold must still be observed before record advancement resumes.
    assert not shared.gate.admission_open(context.snapshot)
    assert shared.gate.reconciled([context.snapshot], set(), generation=shared.gate.generation, started=100.0)
    assert shared.gate.admission_open(context.snapshot)
    shared.gate.database_failed()
    result = await service.recover_claim(prepared.claim)
    assert isinstance(result, BlockedDelivery)
    service._reload.assert_awaited_once()
    launcher.start.assert_awaited_once()
