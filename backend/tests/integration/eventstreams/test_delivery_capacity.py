"""Shared PostgreSQL capacity latch using small test-only threshold overrides."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func
from sqlmodel import select

from syntara.core.constants import EventDeliveryDefaults
from syntara.eventstreams.core.deduplication import DeliveryClaim, StorageBackpressure
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.delivery_capacity import EventDeliveryCapacity
from syntara.eventstreams.services.deduplication_store import EventDeliveryStore
from syntara.eventstreams.services.delivery_capacity_service import PostgreSQLDeliveryCapacityCheck
from syntara.eventstreams.services.delivery_retention_service import EventDeliveryRetentionService
from tests.integration.eventstreams.test_delivery_retention import PositionVerifier, terminal

if TYPE_CHECKING:
    from tests.integration.eventstreams.conftest import DeliveryContext

pytestmark = pytest.mark.integration


async def test_shared_count_hysteresis_preserves_retention_and_unresolved_work(
    delivery_context: DeliveryContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = delivery_context
    monkeypatch.setattr(EventDeliveryDefaults, "CAPACITY_PAUSE_ROWS", 3)
    monkeypatch.setattr(EventDeliveryDefaults, "CAPACITY_RESUME_ROWS", 2)
    first = await terminal(context, offset=0)
    second = await terminal(context, offset=1)
    unresolved = await context.claim(2, prepare=True)
    async with context.session_factory() as session, session.begin():
        assert not await PostgreSQLDeliveryCapacityCheck(session).permits_new_delivery()
        state = await session.get(EventDeliveryCapacity, 1)
        assert state is not None
        assert state.paused
        assert state.retained_count == 3
    async with context.session_factory() as session, session.begin():
        # A separately created repository uses the persisted pause state.
        result = await EventDeliveryStore(session).acquire(context.identity(3), context.expectation(), "worker")
        assert isinstance(result, StorageBackpressure)
        assert isinstance(await context.store(session).renew(unresolved), DeliveryClaim)
        assert (await session.exec(select(func.count()).select_from(EventDelivery))).one() == 3
    retention = EventDeliveryRetentionService(
        context.session_factory,
        verifier=PositionVerifier(100),
        retention_seconds=3600,
    )
    assert await retention.cleanup_one(first.identity)
    async with context.session_factory() as session, session.begin():
        state = await session.get(EventDeliveryCapacity, 1)
        assert state is not None
        assert state.checked_at is not None
        state.checked_at -= timedelta(seconds=31)
        assert not await PostgreSQLDeliveryCapacityCheck(session).permits_new_delivery()
        assert state.retained_count == 2
    assert await retention.cleanup_one(second.identity)
    async with context.session_factory() as session, session.begin():
        state = await session.get(EventDeliveryCapacity, 1)
        assert state is not None
        assert state.checked_at is not None
        state.checked_at -= timedelta(seconds=31)
        assert await PostgreSQLDeliveryCapacityCheck(session).permits_new_delivery()
        assert not state.paused
        assert state.retained_count == 1
        row = await session.get(EventDelivery, unresolved.identity.digest)
        assert row is not None
        assert row.frozen_binding == unresolved.binding
