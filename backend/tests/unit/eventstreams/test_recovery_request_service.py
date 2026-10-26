"""Durable requests preserve authority, revisions and assignment-local dispatch."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.adapters import kafka_position_store
from syntara.eventstreams.adapters.kafka_initial_position import PositionResult, PositionStatus
from syntara.eventstreams.adapters.kafka_position_control import DrainEvidence
from syntara.eventstreams.adapters.kafka_position_store import KafkaInitialPositionStore
from syntara.eventstreams.core.deduplication import RecoveryReservation
from syntara.eventstreams.models.control import EventSubscriptionRecovery
from syntara.eventstreams.models.recovery_hold import EventDeliveryRecoveryHold
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services import recovery_request_service as module
from syntara.eventstreams.services.recovery_request_service import EventRecoveryRequestService
from tests.unit.eventstreams.test_deduplication_store import NOW
from tests.unit.eventstreams.test_kafka_initial_positions import Harness, row
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
        source=source,
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


@pytest.fixture
def recovery_harness(context, monkeypatch) -> Harness:
    """Use real hold/confirmation transactions with isolated SQL and broker ports."""
    context.row.expected_recovery_revision = 0
    context.row.resolve_unscheduled = False
    h = Harness(position=row(gap=True))
    repository = KafkaInitialPositionStore(MagicMock(return_value=context.session))
    monkeypatch.setattr(
        repository, "_locked", AsyncMock(return_value=(context.subscription, context.source, h.position))
    )
    monkeypatch.setattr(repository, "_deliveries", AsyncMock(return_value=[]))
    clock = MagicMock()
    clock.one.return_value = NOW
    context.session.exec.return_value = clock

    def get(model, *_args: object, **_kwargs: object) -> object:
        if model is EventSubscriptionRecovery:
            return context.row
        assert model is EventDeliveryRecoveryHold
        return SimpleNamespace(source_id=context.source.id, released_at=None)

    context.session.get.side_effect = get

    async def reserve(*_args: object) -> RecoveryReservation:
        h.held = True
        return RecoveryReservation(source_id=context.source.id, token=uuid4())

    async def release(*_args: object) -> bool:
        h.held = False
        return True

    monkeypatch.setattr(kafka_position_store, "reserve_recovery_locked", reserve)
    monkeypatch.setattr(kafka_position_store, "release_recovery_locked", release)
    h.store.begin_recovery.side_effect = repository.begin_recovery
    h.store.confirm_recovery.side_effect = repository.confirm_recovery
    return h


@pytest.mark.parametrize("phase", ["before_hold", "after_hold", "after_commit"])
@pytest.mark.parametrize("authority", ["acknowledge_duplicate_risk", "resolve_unscheduled"])
async def test_detached_worker_yields_to_replacement_without_stranding_recovery(
    context, recovery_harness, phase, authority
):
    h = recovery_harness
    old_request = await context.service.read(context.snapshot, 0, 7)

    def replace_authority() -> None:
        context.row = context.row.model_copy(
            update={"expected_recovery_revision": h.position.recovery_revision, authority: True}
        )

    async def replace_after_drain(*_args: object, **_kwargs: object) -> DrainEvidence:
        replace_authority()
        return DrainEvidence(quiescent=True, retained_evidence_complete=True, permanent_content_error=False)

    async def replace_after_commit(offsets: dict[int, int], **kwargs: object) -> None:
        await h.commit(offsets, **kwargs)
        replace_authority()

    if phase == "before_hold":
        replace_authority()
    elif phase == "after_hold":
        h.control.close_and_drain.side_effect = replace_after_drain
    else:
        h.client.commit.side_effect = replace_after_commit
    result = await h.service.recover(old_request, owner_worker_id="worker")
    assert result.status == PositionStatus.REVISION_CHANGED
    assert result.reason == "recovery_request_changed"
    assert h.position.gap_detected_at is not None
    assert h.position.recovery_confirmed_at is None
    assert h.held is (phase != "before_hold")
    await context.service.record(old_request, result)
    assert not context.row.completed

    # The next poll adopts the replacement and retains any selected boundary,
    # even if the broker's current end advanced while the old attempt finished.
    h.control.close_and_drain.side_effect = None
    h.client.commit.side_effect = h.commit
    if phase != "before_hold":
        h.end = 150
    replacement = await context.service.read(context.snapshot, 0, 7)
    result = await h.service.recover(replacement, owner_worker_id="worker")
    assert result.status == PositionStatus.READY
    assert result.next_offset == 100
    assert h.position.gap_detected_at is None
    assert h.position.recovery_boundary == 100
    assert h.position.duplicate_risk_acknowledged is (authority == "acknowledge_duplicate_risk")
    assert not h.held
    await context.service.record(replacement, result)
    assert context.row.completed
