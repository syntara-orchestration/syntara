"""Process gate composition with isolated placement and lifecycle dependencies."""

from types import SimpleNamespace

import pytest
import pytest_asyncio

from syntara.eventstreams.services.worker_gate import EventWorkerGate
from tests.helpers.eventstream_worker import IsolatedPlacementPool, IsolatedPlacementService
from tests.unit.eventstreams.test_connection_provider import connection_context


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
    assert not context.gate.scheduling_open


@pytest.mark.parametrize("already_blocked", [False, True])
async def test_source_failure_requires_kafka_verification_despite_fresh_reconciliation(
    gate_context, *, already_blocked: bool
):
    context = gate_context
    if already_blocked:
        assert context.gate.reconciled(
            [context.snapshot], {context.snapshot.source_id}, generation=context.gate.generation, started=100.0
        )
    previous = context.gate.generation
    context.gate.source_failed(context.snapshot)
    assert context.gate.scheduling_open
    assert context.gate.transport_open(context.snapshot)
    assert not context.gate.admission_open(context.snapshot)
    assert not context.gate.resolution_open(context.snapshot)
    assert context.gate.reconciled([context.snapshot], set(), generation=previous, started=100.0)
    current = context.gate.generation
    assert current == previous
    context.gate.membership_confirmed(160.0, generation=current)
    assert context.gate.reconciled([context.snapshot], {context.snapshot.source_id}, generation=current, started=100.0)
    assert not context.gate.admission_open(context.snapshot)
    assert context.gate.reconciled([context.snapshot], set(), generation=current, started=100.0)
    assert not context.gate.admission_open(context.snapshot)
    context.gate.source_verified(context.snapshot)
    assert context.gate.admission_open(context.snapshot)


async def test_source_failure_leaves_other_sources_open(gate_context) -> None:
    context = gate_context
    other = context.snapshot.model_copy(update={"source_id": context.snapshot.integration_identity})
    assert context.gate.reconciled([context.snapshot, other], set(), generation=context.gate.generation, started=100.0)
    context.gate.source_failed(context.snapshot)
    assert not context.gate.admission_open(context.snapshot)
    assert context.gate.admission_open(other)
    assert context.gate.resolution_open(other)
