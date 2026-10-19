"""Retained-evidence integration behavior; injected verifiers do not exercise Kafka."""

from __future__ import annotations

import importlib
from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, update
from sqlmodel import col, select

from syntara.eventstreams.core.deduplication import DeliveryClaim, DeliveryIdentity, DeliveryState, TerminalDelivery
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.recovery_hold import EventDeliveryRecoveryHold
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.services.delivery_cache import EventDeliveryTerminalLookup
from syntara.eventstreams.services.delivery_retention_service import EventDeliveryRetentionService

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

    from tests.integration.eventstreams.conftest import DeliveryContext

pytestmark = pytest.mark.integration


class PositionVerifier:
    """Test committed-position evidence; no fetched position is supplied."""

    def __init__(self, next_offset: int | None) -> None:
        """Supply a known committed next offset or explicitly unavailable evidence."""
        self.next_offset = next_offset

    async def is_committed_beyond(self, identity: DeliveryIdentity) -> bool:
        return self.next_offset is not None and self.next_offset > identity.record.offset


async def terminal(context: DeliveryContext, *, offset: int = 0, age: int = 7200) -> DeliveryClaim:
    """Commit a real no-trigger outcome and age it without a wall-clock wait."""
    claim = await context.claim(offset)
    async with context.session_factory() as session, session.begin():
        result = await context.store(session).finalize_without_execution(claim, DeliveryState.REJECTED)
        assert isinstance(result, TerminalDelivery)
        await session.execute(
            update(EventDelivery)
            .where(col(EventDelivery.identity_digest) == claim.identity.digest)
            .values(resolved_at=func.clock_timestamp() - timedelta(seconds=age))
        )
    return claim


@pytest.mark.parametrize(("next_offset", "removed"), [(None, False), (40, False), (41, False), (42, True)])
async def test_cleanup_requires_verified_committed_next_offset(
    delivery_context: DeliveryContext,
    next_offset: int | None,
    *,
    removed: bool,
) -> None:
    context = delivery_context
    claim = await terminal(context, offset=41)
    service = EventDeliveryRetentionService(
        context.session_factory,
        verifier=PositionVerifier(next_offset),
        retention_seconds=3600,
    )
    assert await service.cleanup_one(claim.identity) is removed
    async with context.session_factory() as session, session.begin():
        assert (await session.get(EventDelivery, claim.identity.digest) is None) is removed


@pytest.mark.parametrize(("age", "removed"), [(0, False), (3599, False), (3601, True)])
async def test_retention_is_minimum_from_resolved_at(
    delivery_context: DeliveryContext,
    age: int,
    *,
    removed: bool,
) -> None:
    context = delivery_context
    claim = await terminal(context, age=age)
    service = EventDeliveryRetentionService(
        context.session_factory,
        verifier=PositionVerifier(100),
        retention_seconds=3600,
    )
    assert await service.cleanup_one(claim.identity) is removed


async def test_missing_verifier_retains_old_evidence(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await terminal(context, age=30 * 86400)
    service = EventDeliveryRetentionService(context.session_factory, retention_seconds=3600)
    assert await service.cleanup(limit=100) == 0
    assert not await service.cleanup_one(claim.identity)
    async with context.session_factory() as session, session.begin():
        assert await session.get(EventDelivery, claim.identity.digest) is not None


async def test_unresolved_ambiguous_work_never_expires(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await context.claim(prepare=True)
    async with context.session_factory() as session, session.begin():
        attempted = await context.store(session).record_start_attempt(claim)
        assert isinstance(attempted, DeliveryClaim)
        await session.execute(
            update(EventDelivery)
            .where(col(EventDelivery.identity_digest) == claim.identity.digest)
            .values(
                created_at=func.clock_timestamp() - timedelta(days=30),
                lease_until=func.clock_timestamp() - timedelta(days=20),
            )
        )
    service = EventDeliveryRetentionService(
        context.session_factory,
        verifier=PositionVerifier(100),
        retention_seconds=1,
    )
    assert await service.cleanup(limit=100) == 0
    assert not await service.cleanup_one(claim.identity)
    async with context.session_factory() as session, session.begin():
        row = await session.get(EventDelivery, claim.identity.digest)
        assert row is not None
        assert row.frozen_binding == claim.binding
        assert row.first_start_attempt_at is not None


async def test_multiple_holds_persist_until_each_is_released(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await terminal(context)
    service = EventDeliveryRetentionService(
        context.session_factory,
        verifier=PositionVerifier(100),
        retention_seconds=3600,
    )
    first = await service.reserve_recovery(context.snapshot.source_id)
    second = await service.reserve_recovery(context.snapshot.source_id)
    assert first is not None
    assert second is not None
    assert first != second
    # A fresh instance sees the durable reservation rather than process memory.
    other = EventDeliveryRetentionService(
        context.session_factory,
        verifier=PositionVerifier(100),
        retention_seconds=3600,
    )
    assert not await other.cleanup_one(claim.identity)
    assert await other.release_recovery(first)
    assert not await other.cleanup_one(claim.identity)
    assert await other.release_recovery(second)
    assert await other.release_recovery(second)
    assert await other.cleanup_one(claim.identity)


async def test_hold_registration_during_verification_fences_cleanup(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await terminal(context)
    reservations = EventDeliveryRetentionService(context.session_factory, retention_seconds=3600)

    class InterleavingVerifier:
        async def is_committed_beyond(self, _: DeliveryIdentity) -> bool:
            hold = await reservations.reserve_recovery(context.snapshot.source_id)
            assert hold is not None
            assert await reservations.release_recovery(hold)
            return True

    service = EventDeliveryRetentionService(
        context.session_factory,
        verifier=InterleavingVerifier(),
        retention_seconds=3600,
    )
    assert not await service.cleanup_one(claim.identity)
    async with context.session_factory() as session, session.begin():
        source = await session.get(EventSubscriptionSource, context.snapshot.source_id)
        assert source is not None
        assert source.delivery_evidence_revision == 2
        assert await session.get(EventDelivery, claim.identity.digest) is not None
    fresh = EventDeliveryRetentionService(
        context.session_factory,
        verifier=PositionVerifier(100),
        retention_seconds=3600,
    )
    assert await fresh.cleanup_one(claim.identity)


async def test_reservation_tokens_are_idempotent_and_cannot_be_reactivated(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    service = EventDeliveryRetentionService(context.session_factory, retention_seconds=3600)
    token = uuid4()
    reservation = await service.reserve_recovery(context.snapshot.source_id, token=token)
    assert reservation is not None
    assert await service.reserve_recovery(context.snapshot.source_id, token=token) == reservation
    assert await service.release_recovery(reservation)
    assert await service.reserve_recovery(context.snapshot.source_id, token=token) is None
    assert await service.reserve_recovery(uuid4()) is None
    async with context.session_factory() as session, session.begin():
        source = await session.get(EventSubscriptionSource, context.snapshot.source_id)
        assert source is not None
        assert source.delivery_evidence_revision == 2
        assert (await session.exec(select(func.count()).select_from(EventDeliveryRecoveryHold))).one() == 1


async def test_cleanup_batch_is_bounded(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    for offset in range(3):
        await terminal(context, offset=offset)
    service = EventDeliveryRetentionService(
        context.session_factory,
        verifier=PositionVerifier(100),
        retention_seconds=3600,
    )
    assert await service.cleanup(limit=2) == 2
    async with context.session_factory() as session, session.begin():
        assert (await session.exec(select(func.count()).select_from(EventDelivery))).one() == 1


async def test_stale_cache_is_checked_against_real_database(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    cache = AsyncMock()
    cache.get.return_value = context.identity().digest
    lookup = EventDeliveryTerminalLookup(context.session_factory, cache=cache)
    assert await lookup.lookup(context.identity()) is None
    await terminal(context)
    cache.put.side_effect = TimeoutError()
    result = await lookup.lookup(context.identity())
    assert result is not None
    assert result.state == DeliveryState.REJECTED
    cache.put.assert_awaited_once()


async def test_downgrade_refuses_retained_evidence(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    await terminal(context)
    migration = importlib.import_module(
        "syntara.core.database.migrations.versions.673435210536_add_event_deliveries_and_recovery_holds"
    )

    def downgrade(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()

    with pytest.raises(RuntimeError, match="Unsafe downgrade"):
        async with context.session_factory() as session, session.begin():
            connection = await session.connection()
            await connection.run_sync(downgrade)
