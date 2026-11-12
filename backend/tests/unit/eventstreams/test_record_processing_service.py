"""Accepted-run recovery before current decoding and new workflow admission."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from syntara.eventstreams.core.deduplication import DeliveryIdentity, DeliveryState, TerminalDelivery
from syntara.eventstreams.core.envelope import RawEvent
from syntara.eventstreams.core.handler import ResolvedDelivery, RetryDelivery, SchedulingFailureCode
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.core.processing import HeldRecord, InspectedRecord, RecordProcessingGate, SkippedRecord
from syntara.eventstreams.core.results import EventDecodeFailure, EventFailureCode
from syntara.eventstreams.services.admission_service import EventAdmissionService
from syntara.eventstreams.services.record_processing_service import EventRecordProcessingService
from tests.unit.eventstreams.test_execution_preparation_service import PreparationContext, preparation_context


def terminal(identity: DeliveryIdentity) -> ResolvedDelivery:
    """Build normal Execution confirmation without a delivery row."""
    now = datetime.now(UTC)
    return ResolvedDelivery(
        terminal=TerminalDelivery(
            identity=identity,
            state=DeliveryState.SCHEDULED,
            resolved_at=now,
            execution_id=identity.execution_id,
            temporal_run_id="accepted-run",
            execution_confirmed_at=now,
        )
    )


def processing_context(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[PreparationContext, EventRecordProcessingService, MagicMock, RawEvent]:
    """Build typed processing services with isolated preparation and admission ports."""
    context = preparation_context(monkeypatch)
    admission = MagicMock(spec=EventAdmissionService)
    admission.recover_accepted.return_value = None
    admission.schedule.return_value = terminal(context.identity)
    service = EventRecordProcessingService(lambda: context.session, context.service, admission)
    event = RawEvent(value=b'{"count":2}', source_metadata=context.envelope.source_metadata)
    return context, service, admission, event


@pytest.mark.parametrize("entrypoint", ["process", "inspection", "content_failure"])
async def test_accepted_run_wins_before_current_validation(monkeypatch, entrypoint) -> None:
    context, service, admission, event = processing_context(monkeypatch)
    admission.recover_accepted.return_value = terminal(context.identity)
    forbidden = AsyncMock(side_effect=AssertionError("Accepted work must not use current admission"))
    monkeypatch.setattr(service, "admission_eligible", forbidden)
    result: ResolvedDelivery | HeldRecord | InspectedRecord | SkippedRecord
    if entrypoint == "process":
        result = await service.process(context.snapshot, context.identity, event)
    elif entrypoint == "inspection":
        result = await service.inspect_only(context.snapshot, context.identity, event)
    else:
        result = await service.hold_content_failure(
            context.snapshot, context.identity, EventDecodeFailure(code=EventFailureCode.value_too_large)
        )
    assert isinstance(result, ResolvedDelivery)
    forbidden.assert_not_awaited()
    admission.schedule.assert_not_awaited()
    context.session.add.assert_not_called()


async def test_valid_message_prepares_in_memory_then_schedules(monkeypatch) -> None:
    context, service, admission, event = processing_context(monkeypatch)
    monkeypatch.setattr(service, "admission_eligible", AsyncMock(return_value=True))
    result = await service.process(context.snapshot, context.identity, event)
    assert isinstance(result, ResolvedDelivery)
    prepared = admission.schedule.call_args.args[0]
    assert isinstance(prepared, PreparedExecution)
    assert prepared.input_data["payload"] == {"count": 2}
    context.session.add.assert_not_called()


async def test_invalid_message_is_held_without_execution_or_discard(monkeypatch) -> None:
    context, service, admission, event = processing_context(monkeypatch)
    monkeypatch.setattr(service, "admission_eligible", AsyncMock(return_value=True))
    result = await service.process(context.snapshot, context.identity, event.model_copy(update={"value": b"invalid"}))
    assert isinstance(result, HeldRecord)
    assert result.permanent_content_error
    admission.schedule.assert_not_awaited()
    context.session.add.assert_not_called()


async def test_closed_placement_guard_blocks_new_work(monkeypatch) -> None:
    context, service, admission, event = processing_context(monkeypatch)
    result = await service.process(context.snapshot, context.identity, event, admission_guard=lambda: False)
    assert isinstance(result, HeldRecord)
    admission.schedule.assert_not_awaited()


async def test_recovery_inspection_can_validate_delivered_content_behind_its_fence(monkeypatch) -> None:
    context, service, admission, event = processing_context(monkeypatch)
    gate = MagicMock(spec=RecordProcessingGate)
    gate.admission_open.return_value = False
    gate.resolution_open.return_value = False
    service._gate = gate
    result = await service.inspect_only(context.snapshot, context.identity, event)
    assert isinstance(result, InspectedRecord)
    admission.schedule.assert_not_awaited()
    context.session.add.assert_not_called()


async def test_storage_failure_closes_shared_resolution_gate(monkeypatch) -> None:
    context, service, admission, event = processing_context(monkeypatch)
    gate = MagicMock(spec=RecordProcessingGate)
    service._gate = gate
    admission.recover_accepted.return_value = RetryDelivery(
        error_code=SchedulingFailureCode.STORAGE_UNAVAILABLE,
        next_attempt_at=datetime.now(UTC),
        circuit_open=False,
    )
    result = await service.process(context.snapshot, context.identity, event)
    assert isinstance(result, HeldRecord)
    gate.dependency_failed.assert_called_once_with(context.snapshot)
