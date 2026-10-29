"""Lifecycle cancellation, retained evidence and uncertain acceptance safeguards."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.core.deduplication import DeliveryState
from syntara.eventstreams.core.processing import CONTENT_INSPECTION_PENDING
from syntara.eventstreams.exceptions import EventSubscriptionControlConflictError
from syntara.eventstreams.models.control import EventSubscriptionRuntime
from syntara.eventstreams.services.retirement_service import EventRetirementService, cancel_unstarted
from syntara.workflows.models.execution import Execution, ExecutionStatus
from tests.unit.eventstreams.test_deduplication_store import NOW, binding, delivery
from tests.unit.eventstreams.test_subscription_snapshot import _source, _subscription


def pending_execution(row):
    row.frozen_binding = binding()
    row.execution_id = row.execution_identity
    return Execution(
        id=row.execution_identity,
        workflow_id=row.workflow_id,
        project_id=_subscription().project_id,
        workflow_version_id=row.frozen_binding.workflow_version_id,
        created_at=NOW - timedelta(seconds=1),
        input_data={"frozen": "input"},
        execution_metadata={"event_delivery": {"attempt_count": 0, "scheduling_state": "prepared"}},
    )


async def test_cancel_unstarted_updates_delivery_and_pending_execution_in_same_transaction():
    row = delivery()
    execution = pending_execution(row)
    session = MagicMock(spec=AsyncSession)
    session.get.return_value = execution
    frozen, inputs = row.frozen_binding, execution.input_data.copy()
    await cancel_unstarted(session, row, NOW)
    assert row.state == DeliveryState.CANCELLED
    assert row.last_error_code == "cancelled_by_lifecycle"
    assert row.claim_token is row.lease_until is row.owner_worker_id is None
    assert execution.status == ExecutionStatus.CANCELLED
    assert execution.completed_at == NOW
    assert row.frozen_binding == frozen
    assert execution.input_data == inputs
    assert execution.execution_metadata["event_delivery"]["scheduling_state"] == "cancelled"
    assert session.get.call_args.kwargs["with_for_update"]
    session.commit.assert_not_awaited()  # The caller commits both rows, never one independently.


@pytest.mark.parametrize(
    "uncertainty", ["attempt", "expired_attempt", "accepted_run", "confirmed", "execution_attempt", "running"]
)
async def test_cancel_rejects_every_uncertain_or_accepted_prior_start(uncertainty):
    row = delivery()
    execution = pending_execution(row)
    row.lease_until = NOW - timedelta(days=1)
    if uncertainty in {"attempt", "expired_attempt"}:
        row.attempt_count, row.first_start_attempt_at = 1, NOW - timedelta(days=10)
        row.last_error_code = "temporal_not_found" if uncertainty == "expired_attempt" else "temporal_unavailable"
    elif uncertainty == "accepted_run":
        row.temporal_run_id = "accepted-run"
    elif uncertainty == "confirmed":
        row.execution_confirmed_at = NOW
    elif uncertainty == "execution_attempt":
        execution.execution_metadata = {"event_delivery": {"start_attempt_id": "prior-attempt"}}
    else:
        execution.status = ExecutionStatus.RUNNING
    session = MagicMock(spec=AsyncSession)
    session.get.return_value = execution
    original = row.model_dump()
    with pytest.raises(EventSubscriptionControlConflictError):
        await cancel_unstarted(session, row, NOW)
    assert row.model_dump() == original
    session.commit.assert_not_awaited()


@pytest.mark.parametrize("code", [CONTENT_INSPECTION_PENDING, "invalid_json", "activity_log_unavailable"])
async def test_known_content_errors_cannot_be_discarded(code):
    row = delivery()
    row.last_error_code = code
    if code == "activity_log_unavailable":
        row.state = DeliveryState.REJECTED
    session = MagicMock(spec=AsyncSession)
    with pytest.raises(EventSubscriptionControlConflictError, match="activity_log"):
        await cancel_unstarted(session, row, NOW)
    session.get.assert_not_awaited()


async def test_one_local_stop_is_insufficient_when_another_consumer_is_unacknowledged():
    session = MagicMock(spec=AsyncSession)
    gate, running = MagicMock(), MagicMock()
    gate.first.return_value = None
    running.first.return_value = "lost-worker-without-stop-ack"
    session.exec.side_effect = [gate, running]
    source = _source(_subscription())
    source.retired_at = NOW
    service = EventRetirementService(session)
    with pytest.raises(EventSubscriptionControlConflictError, match="acknowledgements"):
        await service.retire(source, resolve_unscheduled=True)
    session.delete.assert_not_awaited()


async def test_retirement_retains_terminal_identity_and_resource_references(monkeypatch):
    session = MagicMock(spec=AsyncSession)
    session.exec.return_value = MagicMock()
    session.exec.return_value.one.return_value = NOW
    source = _source(_subscription())
    source.retired_at = NOW
    row = delivery()
    row.state, row.resolved_at = DeliveryState.FILTERED, NOW
    service = EventRetirementService(session)
    monkeypatch.setattr(service, "stopped", AsyncMock(return_value=True))
    monkeypatch.setattr(service, "deliveries", AsyncMock(return_value=[row]))
    monkeypatch.setattr(service, "has_retained_deliveries", AsyncMock(return_value=True))
    integration = source.integration_id
    await service.retire(source, resolve_unscheduled=False)
    assert source.integration_id == integration
    assert row.state == DeliveryState.FILTERED
    assert not await service.can_detach(source)
    with pytest.raises(EventSubscriptionControlConflictError, match="retained_delivery"):
        await service.release_empty_source(source)
    session.delete.assert_not_awaited()


@pytest.mark.parametrize("resolve", [False, True])
async def test_safe_versus_exceptional_retirement_disposition(monkeypatch, resolve):
    session = MagicMock(spec=AsyncSession)
    session.exec.return_value = MagicMock()
    session.exec.return_value.one.return_value = NOW
    session.get.return_value = None
    source = _source(_subscription())
    source.retired_at = NOW
    row = delivery()
    service = EventRetirementService(session)
    monkeypatch.setattr(service, "stopped", AsyncMock(return_value=True))
    monkeypatch.setattr(service, "deliveries", AsyncMock(return_value=[row]))
    if resolve:
        await service.retire(source, resolve_unscheduled=True)
        assert row.state == DeliveryState.CANCELLED
    else:
        with pytest.raises(EventSubscriptionControlConflictError, match="disposition"):
            await service.retire(source, resolve_unscheduled=False)
        assert row.state == DeliveryState.IN_PROGRESS


def test_runtime_fences_have_no_timeout_that_could_imply_shutdown():
    columns = set(EventSubscriptionRuntime.__table__.columns.keys())
    assert {"stopped", "permanent_content_error", "applied_revision"} <= columns
    assert not {"expires_at", "lease_until", "heartbeat_at", "payload", "credentials"} & columns
