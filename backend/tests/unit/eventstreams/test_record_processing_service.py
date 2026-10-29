"""Record processing composition with real decoding/preparation and isolated I/O."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from syntara.core.exceptions import SafeValueError
from syntara.eventstreams.core.deduplication import (
    ClaimBusy,
    ClaimLost,
    DeliveryClaim,
    DeliveryIdentity,
    DeliveryState,
    TerminalDelivery,
)
from syntara.eventstreams.core.envelope import RawEvent
from syntara.eventstreams.core.handler import ResolvedDelivery, RetryDelivery, SchedulingFailureCode
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.core.processing import (
    CONTENT_INSPECTION_PENDING,
    CONTENT_VALIDATED,
    HeldRecord,
    InspectedRecord,
)
from syntara.eventstreams.core.results import EventDecodeFailure, EventFailureCode
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.services import record_processing_service as module
from syntara.eventstreams.services.admission_service import EventAdmissionService
from syntara.eventstreams.services.record_processing_service import EventRecordProcessingService
from tests.unit.eventstreams.test_execution_preparation_service import preparation_context

if TYPE_CHECKING:
    from syntara.eventstreams.core.serialization import EventDecodeSuccess, JsonEventDecoder


def terminal(identity: DeliveryIdentity, state: DeliveryState = DeliveryState.SCHEDULED) -> ResolvedDelivery:
    now = datetime.now(UTC)
    return ResolvedDelivery(
        terminal=TerminalDelivery(
            identity=identity,
            state=state,
            resolved_at=now,
            execution_id=identity.execution_id if state == DeliveryState.SCHEDULED else None,
            temporal_run_id="run" if state == DeliveryState.SCHEDULED else None,
            execution_confirmed_at=now if state == DeliveryState.SCHEDULED else None,
        )
    )


def retained(identity: DeliveryIdentity, **values: object) -> EventDelivery:
    return EventDelivery(
        **identity.model_dump(exclude={"record"}),
        identity_digest=identity.digest,
        transport="kafka",
        record_identity=identity.record,
        execution_identity=identity.execution_id,
        temporal_workflow_id=identity.temporal_workflow_id,
        **values,
    )


def processing_context(monkeypatch: pytest.MonkeyPatch):
    context = preparation_context(monkeypatch)
    context.store.lookup_terminal.return_value = None
    context.store.defer.return_value = None

    async def acquire_inspection(identity, _expected, _owner) -> DeliveryClaim:
        context.events.append("inspection_marker")
        context.rows[EventDelivery] = retained(identity, last_error_code=CONTENT_INSPECTION_PENDING)
        return context.claim

    async def finish_inspection(claim, failure, *, keep_pending=False) -> ClaimLost | None:
        code = (
            failure.code.value
            if failure is not None
            else CONTENT_INSPECTION_PENDING
            if keep_pending
            else CONTENT_VALIDATED
        )
        result = await context.store.defer(
            claim, error_code=code, next_attempt_at=datetime.max.replace(tzinfo=UTC) if failure else datetime.now(UTC)
        )
        if result is None:
            context.rows[EventDelivery] = retained(claim.identity, last_error_code=code)
            return None
        assert isinstance(result, ClaimLost)
        return result

    context.store.acquire_inspection.side_effect = acquire_inspection
    context.store.finish_inspection.side_effect = finish_inspection
    monkeypatch.setattr(module, "EventDeliveryStore", lambda _session: context.store)
    snapshot = context.snapshot
    source = EventSubscriptionSource(
        id=snapshot.source_id,
        subscription_id=snapshot.subscription_id,
        deployment_id=snapshot.deployment_id,
        generation=snapshot.source_generation,
        integration_id=snapshot.integration_id,
        integration_identity=snapshot.integration_identity,
        transport=snapshot.transport,
        configuration=snapshot.configuration,
    )
    monkeypatch.setattr(module, "lock_source_lifecycle", AsyncMock(return_value=(context.subscription, source)))
    monkeypatch.setattr(
        module, "EventConnectionProvider", lambda _session: SimpleNamespace(resolve_revision=context.provider)
    )
    admission = MagicMock(spec=EventAdmissionService)
    admission.schedule.return_value = terminal(context.identity)
    service = EventRecordProcessingService(lambda: context.session, context.service, admission)
    event = RawEvent(value=b'{"count":2}', source_metadata=context.envelope.source_metadata)
    return context, service, admission, event


async def test_evidence_then_decode_prepare_commit_and_schedule(monkeypatch) -> None:
    context, service, admission, event = processing_context(monkeypatch)

    async def lookup(_identity) -> None:
        context.events.append("lookup")

    async def schedule(prepared) -> ResolvedDelivery:
        assert isinstance(prepared, PreparedExecution)
        assert context.events[-1] == "commit"
        context.events.append("schedule")
        return terminal(context.identity)

    context.store.lookup_terminal.side_effect = lookup
    admission.schedule.side_effect = schedule
    assert isinstance(await service.process(context.snapshot, context.identity, event, "worker"), ResolvedDelivery)
    assert context.events.index("lookup") < context.events.index("acquire") < context.events.index("freeze")
    assert context.events[-2:] == ["commit", "schedule"]


@pytest.mark.parametrize("stage", ["lookup", "eligibility", "inspection"])
async def test_placement_loss_during_slow_processing_never_opens_new_admission(monkeypatch, stage):
    context, service, admission, event = processing_context(monkeypatch)
    permitted = [True]

    if stage == "lookup":

        async def lookup(_identity) -> None:
            permitted[0] = False

        context.store.lookup_terminal.side_effect = lookup
    elif stage == "eligibility":

        async def eligibility(_snapshot) -> bool:
            permitted[0] = False
            return True

        monkeypatch.setattr(service, "admission_eligible", eligibility)
    else:

        async def inspect(*_args: object, **_kwargs: object) -> "EventDecodeSuccess | EventDecodeFailure":
            permitted[0] = False
            decoder: JsonEventDecoder = service._decoder
            return decoder.decode(event)

        monkeypatch.setattr(service, "_inspect_content", inspect)

    result = await service.process(
        context.snapshot, context.identity, event, "worker", admission_guard=lambda: permitted[0]
    )
    assert isinstance(result, HeldRecord)
    assert result.reason == "admission_closed"
    context.store.acquire.assert_not_awaited()
    context.store.freeze.assert_not_awaited()
    admission.schedule.assert_not_awaited()
    if stage != "inspection":
        context.store.acquire_inspection.assert_not_awaited()


async def test_placement_guard_never_revokes_a_frozen_delivery_recovery(monkeypatch):
    context, service, admission, _ = processing_context(monkeypatch)
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    context.rows[EventDelivery] = retained(context.identity, frozen_binding=prepared.claim.binding)
    context.store.acquire.side_effect = None
    context.store.acquire.return_value = prepared.claim
    result = await service.process(context.snapshot, context.identity, None, "worker", admission_guard=lambda: False)
    assert isinstance(result, ResolvedDelivery)
    admission.schedule.assert_awaited_once()
    assert context.events.count("freeze") == 1


async def test_placement_loss_blocks_new_inspection_in_the_session_that_would_acquire_it(monkeypatch):
    context, service, admission, event = processing_context(monkeypatch)
    result = await service.inspect_only(
        context.snapshot, context.identity, event, "worker", admission_guard=lambda: False
    )
    assert isinstance(result, HeldRecord)
    assert result.reason == "admission_closed"
    context.store.acquire_inspection.assert_not_awaited()
    admission.schedule.assert_not_awaited()


@pytest.mark.parametrize("state", [DeliveryState.SCHEDULED, DeliveryState.FILTERED, DeliveryState.CANCELLED])
async def test_terminal_decision_is_preserved_before_eligibility_or_invalid_redelivery(monkeypatch, state) -> None:
    context, service, admission, event = processing_context(monkeypatch)
    original = terminal(context.identity, state).terminal
    context.store.lookup_terminal.return_value = original
    monkeypatch.setattr(service, "admission_eligible", AsyncMock(side_effect=AssertionError("new admission")))
    result = await service.process(
        context.snapshot, context.identity, event.model_copy(update={"value": b"invalid"}), "worker"
    )
    assert isinstance(result, ResolvedDelivery)
    assert result.terminal == original
    context.store.acquire.assert_not_awaited()
    admission.schedule.assert_not_awaited()


@pytest.mark.parametrize("flag", ["paused", "retired", "desired_enabled"])
async def test_frozen_recovery_ignores_new_admission_eligibility(monkeypatch, flag) -> None:
    context, service, admission, _ = processing_context(monkeypatch)
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    context.rows[EventDelivery] = retained(context.identity, frozen_binding=prepared.claim.binding)
    context.store.acquire.side_effect = None
    context.store.acquire.return_value = prepared.claim
    snapshot = context.snapshot.model_copy(update={flag: flag != "desired_enabled"})
    monkeypatch.setattr(service, "admission_eligible", AsyncMock(side_effect=AssertionError("new admission")))
    result = await service.process(snapshot, context.identity, None, "worker")
    assert isinstance(result, ResolvedDelivery)
    admission.schedule.assert_awaited_once()
    assert context.events.count("freeze") == 1


@pytest.mark.parametrize("value", [b"not-json", None, b"\x00\x00\x00\x00\x01"])
async def test_content_failure_is_committed_as_unresolved_evidence(monkeypatch, value) -> None:
    context, service, admission, event = processing_context(monkeypatch)
    result = await service.process(
        context.snapshot, context.identity, event.model_copy(update={"value": value}), "worker"
    )
    assert isinstance(result, HeldRecord)
    assert result.permanent_content_error
    assert result.retry_at is None
    assert context.events[-1] == "commit"
    claim = context.store.defer.call_args.args[0]
    assert claim.binding is None
    assert context.store.defer.call_args.kwargs["error_code"] in {code.value for code in EventFailureCode}
    context.store.finalize_without_execution.assert_not_awaited()
    context.store.freeze.assert_not_awaited()
    admission.schedule.assert_not_awaited()


@pytest.mark.parametrize("code", list(EventFailureCode))
async def test_persisted_content_gate_survives_retry_restart_and_changed_content(monkeypatch, code) -> None:
    context, service, admission, event = processing_context(monkeypatch)
    context.rows[EventDelivery] = retained(context.identity, last_error_code=code.value)
    for instance in [service, EventRecordProcessingService(lambda: context.session, context.service, admission)]:
        result = await instance.process(context.snapshot, context.identity, event, "new-owner")
        assert isinstance(result, HeldRecord)
        assert result.permanent_content_error
        assert result.retry_at is None
    context.store.acquire.assert_not_awaited()
    admission.schedule.assert_not_awaited()


async def test_internal_rejected_marker_does_not_bypass_activity_log_gate(monkeypatch) -> None:
    context, service, admission, event = processing_context(monkeypatch)
    context.store.lookup_terminal.return_value = terminal(context.identity, DeliveryState.REJECTED).terminal
    result = await service.process(context.snapshot, context.identity, event, "worker")
    assert isinstance(result, HeldRecord)
    assert result.permanent_content_error
    admission.schedule.assert_not_awaited()


@pytest.mark.parametrize("failure", [SQLAlchemyError("PRIVATE"), OSError("PRIVATE"), SafeValueError("PRIVATE")])
async def test_dependency_failures_hold_without_content_rejection(monkeypatch, failure) -> None:
    context, service, admission, event = processing_context(monkeypatch)
    context.provider.side_effect = failure
    result = await service.process(context.snapshot, context.identity, event, "worker")
    assert isinstance(result, HeldRecord)
    assert not result.permanent_content_error
    context.store.defer.assert_not_awaited()
    admission.schedule.assert_not_awaited()


async def test_quota_refusal_is_backpressure_not_content(monkeypatch) -> None:
    context, service, admission, event = processing_context(monkeypatch)
    context.capacity.side_effect = None
    context.capacity.return_value = 2
    result = await service.process(context.snapshot, context.identity, event, "worker")
    assert isinstance(result, HeldRecord)
    assert result.reason == "execution_capacity"
    assert not result.permanent_content_error
    assert context.events[-1] == "rollback"
    assert context.store.defer.call_args.kwargs["error_code"] == CONTENT_INSPECTION_PENDING
    admission.schedule.assert_not_awaited()


async def test_busy_claim_and_temporal_retry_preserve_retry_time(monkeypatch) -> None:
    context, service, admission, event = processing_context(monkeypatch)
    retry_at = datetime.now(UTC) + timedelta(seconds=60)
    context.store.acquire.side_effect = None
    context.store.acquire.return_value = ClaimBusy(lease_until=retry_at)
    result = await service.process(context.snapshot, context.identity, event, "worker")
    assert isinstance(result, HeldRecord)
    assert result.reason == "claim_busy"
    assert result.retry_at == retry_at
    context.store.acquire.return_value = context.claim
    admission.schedule.return_value = RetryDelivery(
        error_code=SchedulingFailureCode.TEMPORAL_UNAVAILABLE, next_attempt_at=retry_at, circuit_open=False
    )
    result = await service.process(context.snapshot, context.identity, event, "worker")
    assert isinstance(result, HeldRecord)
    assert result.reason == "temporal_unavailable"
    assert result.retry_at == retry_at
    context.store.finalize_without_execution.assert_not_awaited()


@pytest.mark.parametrize(
    "code", [EventFailureCode.value_too_large, EventFailureCode.envelope_too_large, EventFailureCode.too_many_headers]
)
async def test_unbufferable_content_persists_only_safe_unresolved_evidence(monkeypatch, code) -> None:
    context, service, admission, _ = processing_context(monkeypatch)
    result = await service.hold_content_failure(
        context.snapshot, context.identity, EventDecodeFailure(code=code), "worker"
    )
    assert isinstance(result, HeldRecord)
    assert result.permanent_content_error
    assert result.retry_at is None
    assert context.events[-1] == "commit"
    assert context.store.defer.call_args.kwargs["error_code"] == code.value
    assert context.store.defer.call_args.args[0].binding is None
    context.store.finalize_without_execution.assert_not_awaited()
    context.store.freeze.assert_not_awaited()
    admission.schedule.assert_not_awaited()


async def test_unbufferable_redelivery_preserves_terminal_evidence_before_eligibility(monkeypatch) -> None:
    context, service, admission, _ = processing_context(monkeypatch)
    original = terminal(context.identity, DeliveryState.CANCELLED).terminal
    context.store.lookup_terminal.return_value = original
    monkeypatch.setattr(service, "admission_eligible", AsyncMock(side_effect=AssertionError("new admission")))
    result = await service.hold_content_failure(
        context.snapshot, context.identity, EventDecodeFailure(code=EventFailureCode.value_too_large), "worker"
    )
    assert isinstance(result, ResolvedDelivery)
    assert result.terminal == original
    context.store.defer.assert_not_awaited()
    admission.schedule.assert_not_awaited()


async def test_unbufferable_redelivery_repairs_frozen_work_before_eligibility(monkeypatch) -> None:
    context, service, admission, _ = processing_context(monkeypatch)
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    context.rows[EventDelivery] = retained(context.identity, frozen_binding=prepared.claim.binding)
    context.store.acquire.side_effect = None
    context.store.acquire.return_value = prepared.claim
    monkeypatch.setattr(service, "admission_eligible", AsyncMock(side_effect=AssertionError("new admission")))
    result = await service.hold_content_failure(
        context.snapshot, context.identity, EventDecodeFailure(code=EventFailureCode.value_too_large), "worker"
    )
    assert isinstance(result, ResolvedDelivery)
    admission.schedule.assert_awaited_once()
    context.store.defer.assert_not_awaited()
    assert context.events.count("freeze") == 1


async def test_unbufferable_content_database_failure_stays_retryable(monkeypatch) -> None:
    context, service, admission, _ = processing_context(monkeypatch)
    context.store.defer.side_effect = SQLAlchemyError("PRIVATE")
    result = await service.hold_content_failure(
        context.snapshot, context.identity, EventDecodeFailure(code=EventFailureCode.value_too_large), "worker"
    )
    assert isinstance(result, HeldRecord)
    assert result.retry_at is not None
    assert not result.permanent_content_error
    assert context.events[-1] == "rollback"
    context.store.finalize_without_execution.assert_not_awaited()
    admission.schedule.assert_not_awaited()


async def test_inspection_marker_commits_before_decoder_and_survives_failed_finish(monkeypatch) -> None:
    context, service, admission, event = processing_context(monkeypatch)
    decoder = MagicMock()

    def decode(*_args: object, **_kwargs: object) -> EventDecodeFailure:
        assert context.events[-1] == "commit"
        assert context.rows[EventDelivery].last_error_code == CONTENT_INSPECTION_PENDING
        return EventDecodeFailure(code=EventFailureCode.invalid_json)

    decoder.decode.side_effect = decode
    service._decoder = decoder
    context.store.finish_inspection.side_effect = SQLAlchemyError("unavailable")
    result = await service.inspect_only(context.snapshot, context.identity, event, "worker")
    assert isinstance(result, HeldRecord)
    assert not result.permanent_content_error
    assert context.rows[EventDelivery].last_error_code == CONTENT_INSPECTION_PENDING
    assert context.events[-1] == "rollback"
    context.store.acquire.assert_not_awaited()
    admission.schedule.assert_not_awaited()


async def test_validation_only_inspection_works_while_new_admission_is_closed(monkeypatch) -> None:
    context, service, admission, event = processing_context(monkeypatch)
    monkeypatch.setattr(service, "admission_eligible", AsyncMock(side_effect=AssertionError("new admission")))
    result = await service.inspect_only(context.snapshot, context.identity, event, "worker")
    assert isinstance(result, InspectedRecord)
    assert result.identity == context.identity
    assert context.rows[EventDelivery].last_error_code == CONTENT_VALIDATED
    context.store.acquire.assert_not_awaited()
    context.store.freeze.assert_not_awaited()
    admission.schedule.assert_not_awaited()


async def test_pending_inspection_identity_requests_content_without_new_admission(monkeypatch) -> None:
    context, service, admission, _ = processing_context(monkeypatch)
    context.rows[EventDelivery] = retained(context.identity, last_error_code=CONTENT_INSPECTION_PENDING)
    result = await service.process(context.snapshot, context.identity, None, "worker")
    assert isinstance(result, HeldRecord)
    assert result.reason == CONTENT_INSPECTION_PENDING
    assert not result.permanent_content_error
    context.store.acquire_inspection.assert_not_awaited()
    context.store.acquire.assert_not_awaited()
    admission.schedule.assert_not_awaited()
