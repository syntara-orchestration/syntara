"""Durable requests preserve authority, revisions and assignment-local dispatch."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.adapters.kafka_initial_position import PositionResult, PositionStatus
from syntara.eventstreams.models.control import EventSubscriptionRecovery
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services import recovery_request_service as module
from syntara.eventstreams.services.recovery_request_service import EventRecoveryRequestService
from tests.unit.eventstreams.test_subscription_snapshot import _source, _subscription


@pytest.fixture
def context(monkeypatch):
    subscription = _subscription()
    source = _source(subscription)
    snapshot = SubscriptionSnapshot.from_models(subscription, source)
    row = EventSubscriptionRecovery(
        source_id=source.id,
        partition=0,
        configuration_revision=1,
        expected_recovery_revision=2,
        policy="current_end",
        reason="offset_expired",
        requested_by=uuid4(),
        resolve_unscheduled=True,
    )
    session = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    session.get.return_value = row
    monkeypatch.setattr(module, "lock_source_lifecycle", AsyncMock(return_value=(subscription, source)))
    return SimpleNamespace(
        row=row,
        subscription=subscription,
        snapshot=snapshot,
        session=session,
        service=EventRecoveryRequestService(MagicMock(return_value=session)),
    )


async def test_request_uses_current_owner_epoch_and_preserves_authorized_policy(context):
    request = await context.service.read(context.snapshot, 0, 17)
    assert request.assignment_epoch == 17
    assert request.expected_recovery_revision == 2
    assert request.allow_unscheduled_disposition
    assert request.policy.value == "current_end"
    assert "offset" not in type(request).model_fields


@pytest.mark.parametrize("stale", ["configuration", "completed"])
async def test_completed_or_superseded_requests_are_not_dispatched(context, stale):
    if stale == "configuration":
        context.row.configuration_revision = 0
    else:
        context.row.completed = True
    assert await context.service.read(context.snapshot, 0, 17) is None


@pytest.mark.parametrize("status", [PositionStatus.BLOCKED, PositionStatus.READY, PositionStatus.OWNERSHIP_LOST])
async def test_only_ready_completes_a_request(context, status):
    request = await context.service.read(context.snapshot, 0, 17)
    await context.service.record(request, PositionResult(status=status, assignment_epoch=17, reason=None))
    assert context.row.completed is (status == PositionStatus.READY)


async def test_stale_result_cannot_complete_an_amended_request(context):
    request = await context.service.read(context.snapshot, 0, 17)
    context.row.resolve_unscheduled = False
    await context.service.record(request, PositionResult(status=PositionStatus.READY, assignment_epoch=17))
    assert not context.row.completed
