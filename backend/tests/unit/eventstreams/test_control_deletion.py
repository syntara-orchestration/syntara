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
    assert "state" in statement


@pytest.mark.parametrize("protected", ["hold", "gap", "request"])
async def test_resource_detachment_requires_no_recovery_dependency(monkeypatch, protected):
    session = MagicMock(spec=AsyncSession)
    source = _source(_subscription())
    source.retired_at = NOW
    service = EventRetirementService(session)
    monkeypatch.setattr(service, "stopped", AsyncMock(return_value=True))
    monkeypatch.setattr(service, "deliveries", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "has_retained_deliveries", AsyncMock(return_value=False))
    values = ["held" if protected == name else None for name in ("hold", "gap", "request")]
    results = []
    for value in values:
        result = MagicMock()
        result.first.return_value = value
        results.append(result)
    session.exec.side_effect = results
    assert not await service.can_detach(source)
    session.delete.assert_not_awaited()


async def test_active_sources_cannot_be_retired_even_with_disposition_authority():
    source = _source(_subscription())
    session = MagicMock(spec=AsyncSession)
    with pytest.raises(EventSubscriptionControlConflictError, match="remove_or_replace"):
        await EventRetirementService(session).retire(source, resolve_unscheduled=True)
    session.exec.assert_not_awaited()
