"""PostgreSQL repository behavior; no broker, Temporal or production durability claims."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from syntara.eventstreams.core.deduplication import (
    ClaimBusy,
    ClaimLost,
    DeliveryClaim,
    DeliveryState,
    RevisionChanged,
    StorageBackpressure,
    TemporalAcceptance,
    TerminalDelivery,
)
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.services.deduplication_store import EventDeliveryStore
from syntara.eventstreams.services.subscription_service import lock_source_lifecycle
from syntara.workflows.models.execution import Execution, ExecutionStatus

if TYPE_CHECKING:
    from tests.integration.eventstreams.conftest import DeliveryContext

pytestmark = pytest.mark.integration


async def _attempt(context: DeliveryContext, claim: DeliveryClaim) -> DeliveryClaim:
    async with context.session_factory() as session, session.begin():
        result = await context.store(session).record_start_attempt(claim)
        assert isinstance(result, DeliveryClaim)
        return result


def _acceptance(claim: DeliveryClaim) -> TemporalAcceptance:
    """Supply launcher evidence as a test double; no Temporal acceptance is exercised."""
    assert claim.binding is not None
    return TemporalAcceptance(
        execution_id=claim.identity.execution_id,
        temporal_workflow_id=claim.identity.temporal_workflow_id,
        temporal_run_id="test-confirmed-run",
        input_fingerprint=claim.binding.input_fingerprint,
    )


async def test_unique_acquisition_busy_and_renewal(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await context.claim()
    async with context.session_factory() as session, session.begin():
        assert isinstance(
            await context.store(session).acquire(context.identity(), context.expectation(), "other"), ClaimBusy
        )
        renewed = await context.store(session).renew(claim)
        assert isinstance(renewed, DeliveryClaim)
        assert renewed.token == claim.token
        assert renewed.lease_until >= claim.lease_until
        assert (await session.exec(select(func.count()).select_from(EventDelivery))).one() == 1


async def test_preparation_freezes_real_platform_execution(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await context.claim(prepare=True)
    assert claim.binding is not None
    assert claim.binding.execution_principal_id == context.principal_id
    async with context.session_factory() as session, session.begin():
        execution = await session.get(Execution, claim.identity.execution_id)
        row = await session.get(EventDelivery, claim.identity.digest)
        assert execution is not None
        assert row is not None
        assert execution.status == ExecutionStatus.PENDING
        assert execution.created_by == context.principal_id
        assert row.execution_id == execution.id
        assert row.resolved_at is None
        assert row.frozen_binding == claim.binding
        assert "input_data" not in row.model_dump()


async def test_first_attempt_and_counter_persist(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await context.claim(prepare=True)
    first = await _attempt(context, claim)
    second = await _attempt(context, first)
    assert first.attempt_count == 1
    assert second.attempt_count == 2
    assert first.first_start_attempt_at is not None
    assert second.first_start_attempt_at == first.first_start_attempt_at
    async with context.session_factory() as session, session.begin():
        row = await session.get(EventDelivery, claim.identity.digest)
        assert row is not None
        assert row.attempt_count == 2
        assert row.first_start_attempt_at == first.first_start_attempt_at


async def test_expired_takeover_preserves_frozen_and_acceptance_evidence(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    original = await _attempt(context, await context.claim(prepare=True))
    async with context.session_factory() as session, session.begin():
        recorded = await context.store(session).record_acceptance(original, _acceptance(original))
        assert isinstance(recorded, DeliveryClaim)
    await context.expire(original)
    async with context.session_factory() as session, session.begin():
        lifecycle = await lock_source_lifecycle(session, context.snapshot.source_id)
        assert lifecycle is not None
        subscription, source = lifecycle
        subscription.paused = True
        subscription.desired_enabled = False
        subscription.retired = True
        source.retired_at = (await session.exec(select(func.clock_timestamp()))).one()
    async with context.session_factory() as session, session.begin():
        store = context.store(session)
        taken = await store.acquire(context.identity(), context.expectation(), "recovery-worker")
        assert isinstance(taken, DeliveryClaim)
        assert taken.token != original.token
        assert taken.binding == original.binding
        assert taken.attempt_count == original.attempt_count
        assert taken.first_start_attempt_at == original.first_start_attempt_at
        assert taken.temporal_run_id == "test-confirmed-run"
        assert isinstance(await store.renew(original), ClaimLost)
        assert isinstance(await store.record_start_attempt(original), ClaimLost)
        assert isinstance(await store.finalize_scheduled(original, _acceptance(original)), ClaimLost)
        assert isinstance(await store.finalize_scheduled(taken, _acceptance(taken)), TerminalDelivery)


async def test_expired_token_cannot_be_renewed_or_finalized(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await _attempt(context, await context.claim(prepare=True))
    await context.expire(claim)
    async with context.session_factory() as session, session.begin():
        store = context.store(session)
        assert isinstance(await store.renew(claim), ClaimLost)
        assert isinstance(await store.record_start_attempt(claim), ClaimLost)
        assert isinstance(await store.record_acceptance(claim, _acceptance(claim)), ClaimLost)
        assert isinstance(await store.finalize_scheduled(claim, _acceptance(claim)), ClaimLost)
        row = await session.get(EventDelivery, claim.identity.digest, populate_existing=True)
        assert row is not None
        assert row.state == DeliveryState.IN_PROGRESS
        assert row.attempt_count == 1
        assert row.temporal_run_id is None


async def test_finalization_rolls_back_with_execution_confirmation(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await _attempt(context, await context.claim(prepare=True))
    async with context.session_factory() as session, session.begin():
        await context.store(session).record_acceptance(claim, _acceptance(claim))
    with pytest.raises(RuntimeError, match="rollback finalization"):
        async with context.session_factory() as session, session.begin():
            terminal = await context.store(session).finalize_scheduled(claim, _acceptance(claim))
            assert isinstance(terminal, TerminalDelivery)
            message = "rollback finalization"
            raise RuntimeError(message)
    async with context.session_factory() as session, session.begin():
        row = await session.get(EventDelivery, claim.identity.digest)
        execution = await session.get(Execution, claim.identity.execution_id)
        assert row is not None
        assert execution is not None
        assert execution.execution_metadata is not None
        assert row.state == DeliveryState.IN_PROGRESS
        assert row.temporal_run_id == "test-confirmed-run"
        assert row.execution_confirmed_at is None
        assert execution.execution_metadata["event_delivery"]["scheduling_state"] == "prepared"
        assert isinstance(await context.store(session).finalize_scheduled(claim, _acceptance(claim)), TerminalDelivery)


async def test_finalization_preserves_advanced_execution_status(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await _attempt(context, await context.claim(prepare=True))
    async with context.session_factory() as session, session.begin():
        execution = await session.get(Execution, claim.identity.execution_id)
        assert execution is not None
        execution.status = ExecutionStatus.RUNNING
    async with context.session_factory() as session, session.begin():
        store = context.store(session)
        first = await store.finalize_scheduled(claim, _acceptance(claim))
        assert isinstance(first, TerminalDelivery)
        assert await store.finalize_scheduled(claim, _acceptance(claim)) == first
        execution = await session.get(Execution, claim.identity.execution_id)
        assert execution is not None
        assert execution.execution_metadata is not None
        assert execution.status == ExecutionStatus.RUNNING
        assert execution.execution_metadata["event_delivery"]["scheduling_state"] == "confirmed"


async def test_terminal_admission_cannot_be_overwritten(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await context.claim()
    async with context.session_factory() as session, session.begin():
        terminal = await context.store(session).finalize_without_execution(claim, DeliveryState.REJECTED)
        assert isinstance(terminal, TerminalDelivery)
    async with context.session_factory() as session, session.begin():
        result = await context.store(session).acquire(
            claim.identity,
            context.expectation().model_copy(update={"configuration_revision": 999}),
            "new",
        )
        assert result == terminal
        assert isinstance(
            await context.store(session).finalize_without_execution(claim, DeliveryState.FILTERED), ClaimLost
        )


async def test_terminal_identity_survives_execution_deletion(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await _attempt(context, await context.claim(prepare=True))
    async with context.session_factory() as session, session.begin():
        await context.store(session).finalize_scheduled(claim, _acceptance(claim))
    async with context.session_factory() as session, session.begin():
        execution = await session.get(Execution, claim.identity.execution_id)
        assert execution is not None
        await session.delete(execution)
    async with context.session_factory() as session, session.begin():
        row = await session.get(EventDelivery, claim.identity.digest)
        assert row is not None
        assert row.execution_id is None
        terminal = await context.store(session).lookup_terminal(claim.identity)
        assert terminal is not None
        assert terminal.execution_id == claim.identity.execution_id
        assert terminal.temporal_run_id == "test-confirmed-run"


async def test_unresolved_execution_deletion_is_blocked(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await context.claim(prepare=True)
    with pytest.raises(IntegrityError):
        async with context.session_factory() as session, session.begin():
            execution = await session.get(Execution, claim.identity.execution_id)
            assert execution is not None
            await session.delete(execution)
            await session.flush()
    async with context.session_factory() as session, session.begin():
        assert await session.get(Execution, claim.identity.execution_id) is not None


async def test_frozen_binding_cannot_be_replaced(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await context.claim(prepare=True)
    assert claim.binding is not None
    replacement = claim.binding.model_copy(update={"workflow_version_id": uuid4()})
    async with context.session_factory() as session, session.begin():
        execution = await session.get(Execution, claim.identity.execution_id)
        assert execution is not None
        with pytest.raises(ValueError, match="cannot be replaced"):
            await context.store(session).freeze(claim, replacement, execution)


async def test_revision_or_source_mismatch_does_not_insert(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    async with context.session_factory() as session, session.begin():
        store = context.store(session)
        wrong_revision = context.expectation().model_copy(update={"configuration_revision": 999})
        assert isinstance(await store.acquire(context.identity(), wrong_revision, "worker"), RevisionChanged)
        wrong_deployment = context.identity().model_copy(update={"deployment_id": uuid4()})
        assert isinstance(await store.acquire(wrong_deployment, context.expectation(), "worker"), RevisionChanged)
        assert (await session.exec(select(func.count()).select_from(EventDelivery))).one() == 0


async def test_due_scan_is_bounded_and_preserves_frozen_context(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    due = [await context.claim(offset, prepare=True) for offset in range(3)]
    active = await context.claim(3)
    delayed = await context.claim(4)
    for claim in due:
        await context.expire(claim)
    await context.expire(delayed)
    async with context.session_factory() as session, session.begin():
        await session.execute(
            update(EventDelivery)
            .where(col(EventDelivery.identity_digest) == delayed.identity.digest)
            .values(next_attempt_at=func.clock_timestamp() + timedelta(hours=1))
        )
        lifecycle = await lock_source_lifecycle(session, context.snapshot.source_id)
        assert lifecycle is not None
        lifecycle[0].paused = True
    async with context.session_factory() as session, session.begin():
        claims = await context.store(session).claim_due("recovery", limit=2)
        assert len(claims) == 2
        assert {claim.identity.digest for claim in claims} <= {claim.identity.digest for claim in due}
        assert all(claim.binding is not None for claim in claims)
        assert all(claim.owner_worker_id == "recovery" for claim in claims)
        assert active.identity.digest not in {claim.identity.digest for claim in claims}


async def test_unowned_retry_is_selected_without_changing_attempt_evidence(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await _attempt(context, await context.claim(prepare=True))
    async with context.session_factory() as session, session.begin():
        now = (await session.exec(select(func.clock_timestamp()))).one()
        assert await context.store(session).defer(claim, next_attempt_at=now, error_code="ambiguous_start") is None
    async with context.session_factory() as session, session.begin():
        claims = await context.store(session).claim_due("recovery", limit=1)
        assert len(claims) == 1
        assert claims[0].first_start_attempt_at == claim.first_start_attempt_at
        assert claims[0].attempt_count == 1
        assert claims[0].binding == claim.binding


async def test_capacity_pressure_never_blocks_existing_recovery(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await context.claim(prepare=True)
    await context.expire(claim)

    class FullCapacity:
        async def permits_new_delivery(self) -> bool:
            return False

    async with context.session_factory() as session, session.begin():
        store = EventDeliveryStore(session, capacity_check=FullCapacity())
        assert isinstance(
            await store.acquire(context.identity(1), context.expectation(), "worker"), StorageBackpressure
        )
        assert isinstance(await store.acquire(claim.identity, context.expectation(), "recovery"), DeliveryClaim)
