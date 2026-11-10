"""Deletion cannot erase frozen credential references or recovery evidence."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.exceptions import EventSubscriptionControlConflictError, EventSubscriptionInUseError
from syntara.eventstreams.services import subscription_service as module
from syntara.eventstreams.services.retirement_service import EventRetirementService
from syntara.eventstreams.services.subscription_service import EventSubscriptionService
from tests.unit.eventstreams.test_deduplication_store import NOW
from tests.unit.eventstreams.test_subscription_snapshot import _source, _subscription


async def test_old_frozen_runtime_credentials_remain_protected_after_republication(monkeypatch):
    session = MagicMock(spec=AsyncSession)
    source_id = uuid4()
    result = MagicMock()
    result.all.return_value = [source_id]
    session.exec.return_value = result
    service = EventSubscriptionService(session, SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(service, "_count_subscriptions", AsyncMock(return_value=0))
    lock = AsyncMock()
    monkeypatch.setattr(module, "lock_source_lifecycle", lock)
    with pytest.raises(EventSubscriptionInUseError):
        await service.assert_credential_not_bound(uuid4(), "old-runtime")
    lock.assert_awaited_once_with(session, source_id)
    statement = str(session.exec.call_args.args[0])
    assert "frozen_binding" in statement
    # Terminal deliveries retain the same credential reference after republish.
    assert "event_deliveries.state" not in statement


@pytest.mark.parametrize("gap_partition", [0, 1, None])
async def test_resource_detachment_requires_no_partition_recovery_gap(monkeypatch, gap_partition):
    session = MagicMock(spec=AsyncSession)
    source = _source(_subscription())
    source.retired_at = NOW
    service = EventRetirementService(session)
    monkeypatch.setattr(service, "stopped", AsyncMock(return_value=True))
    monkeypatch.setattr(service, "has_retained_deliveries", AsyncMock(return_value=False))
    result = MagicMock()
    result.first.return_value = gap_partition
    session.exec.return_value = result
    assert await service.can_detach(source) is (gap_partition is None)
    session.exec.assert_awaited_once()
    statement = str(session.exec.call_args.args[0])
    assert "kafka_partition_initial_positions.gap_detected_at IS NOT NULL" in statement
    assert "event_delivery_recovery_holds" not in statement
    assert "event_subscription_recoveries" not in statement
    session.delete.assert_not_awaited()


async def test_active_sources_cannot_be_retired_even_with_disposition_authority():
    source = _source(_subscription())
    session = MagicMock(spec=AsyncSession)
    with pytest.raises(EventSubscriptionControlConflictError, match="remove_or_replace"):
        await EventRetirementService(session).retire(source, resolve_unscheduled=True)
    session.exec.assert_not_awaited()
