"""Source removal follows placement drain rather than delivery-row retention."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.exceptions import EventSubscriptionControlConflictError
from syntara.eventstreams.services.retirement_service import EventRetirementService
from tests.unit.eventstreams.test_kafka_position_store import lifecycle


@pytest.mark.parametrize("live", [False, True])
async def test_source_release_requires_no_live_consumer(live) -> None:
    subscription, source = lifecycle()
    now = datetime.now(UTC)
    source.retired_at = now
    subscription.assigned_worker_id = subscription.id
    subscription.assignment_lease_until = now + timedelta(seconds=60 if live else -1)
    session = MagicMock(spec=AsyncSession)
    session.get.return_value = subscription
    session.exec = AsyncMock(return_value=MagicMock())
    session.exec.return_value.one.return_value = now
    session.exec.return_value.all.return_value = []
    session.exec.return_value.first.return_value = None
    if live:
        with pytest.raises(EventSubscriptionControlConflictError, match="drain_pending"):
            await EventRetirementService(session).release_empty_source(source)
        session.delete.assert_not_awaited()
    else:
        await EventRetirementService(session).release_empty_source(source)
        session.delete.assert_awaited_once_with(source)


@pytest.mark.parametrize("history", ["position", "initialized", "execution"])
async def test_expired_lease_cannot_release_resources_for_an_unrecorded_accepted_run(history) -> None:
    subscription, source = lifecycle()
    now = datetime.now(UTC)
    source.retired_at = now
    subscription.assigned_worker_id = subscription.id
    subscription.assignment_lease_until = now - timedelta(seconds=1)
    session = MagicMock(spec=AsyncSession)
    session.get.return_value = subscription
    session.exec = AsyncMock(return_value=MagicMock())
    session.exec.return_value.one.return_value = now
    session.exec.return_value.all.return_value = [MagicMock()] if history == "position" else []
    session.exec.return_value.first.return_value = subscription.id if history == "execution" else None
    if history == "initialized":
        source.initialized_at = now
    with pytest.raises(EventSubscriptionControlConflictError, match="handoff_safety_unproven"):
        await EventRetirementService(session).release_empty_source(source)
    session.delete.assert_not_awaited()
