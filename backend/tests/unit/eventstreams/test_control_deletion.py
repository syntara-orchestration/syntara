"""Protect current credential bindings and live source consumers on deletion."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.eventstreams.exceptions import EventSubscriptionControlConflictError, EventSubscriptionInUseError
from syntara.eventstreams.services.retirement_service import EventRetirementService
from syntara.eventstreams.services.subscription_service import EventSubscriptionService
from tests.unit.eventstreams.test_subscription_snapshot import _source, _subscription


@pytest.mark.parametrize("bound", [False, True])
async def test_only_current_subscription_references_bind_runtime_credentials(monkeypatch, bound) -> None:
    session = MagicMock(spec=AsyncSession)
    service = EventSubscriptionService(session, User(id=uuid4(), username="test-user", first_name="Test"))
    count = AsyncMock(return_value=int(bound))
    monkeypatch.setattr(service, "_count_subscriptions", count)
    if bound:
        with pytest.raises(EventSubscriptionInUseError):
            await service.assert_credential_not_bound(uuid4(), "runtime")
    else:
        await service.assert_credential_not_bound(uuid4(), "runtime")
    count.assert_awaited_once()
    session.exec.assert_not_awaited()


async def test_active_source_cannot_be_deleted() -> None:
    source = _source(_subscription())
    session = MagicMock(spec=AsyncSession)
    with pytest.raises(EventSubscriptionControlConflictError, match="drain_pending"):
        await EventRetirementService(session).release_empty_source(source)
    session.delete.assert_not_awaited()
