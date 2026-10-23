"""Scheduling control paths and uncertain-write ordering with isolated adapters."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.core.deduplication import (
    ClaimLost,
    DeliveryClaim,
    DeliveryState,
    TemporalAcceptance,
    TerminalDelivery,
)
from syntara.eventstreams.core.handler import BlockedDelivery, EventLaunchError, ResolvedDelivery, SchedulingFailureCode
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.core.scheduling_metadata import EVENT_DELIVERY_METADATA_KEY
from syntara.eventstreams.services import admission_service as module
from syntara.eventstreams.services.admission_service import EventAdmissionService
from tests.unit.eventstreams.test_execution_preparation_service import preparation_context


@pytest_asyncio.fixture
async def prepared(monkeypatch: pytest.MonkeyPatch) -> PreparedExecution:
    result = await preparation_context(monkeypatch).prepare()
    assert isinstance(result, PreparedExecution)
    return result


def acceptance(prepared: PreparedExecution) -> TemporalAcceptance:
    assert prepared.claim.binding is not None
    return TemporalAcceptance(
        execution_id=prepared.execution_id,
        temporal_workflow_id=prepared.temporal_workflow_id,
        temporal_run_id="accepted-run",
        input_fingerprint=prepared.claim.binding.input_fingerprint,
    )


def harness(prepared: PreparedExecution, monkeypatch: pytest.MonkeyPatch):
    now = datetime.now(UTC)
    attempted = prepared.claim.model_copy(
        update={
            "attempt_count": prepared.claim.attempt_count + 1,
            "first_start_attempt_at": prepared.claim.first_start_attempt_at or now,
            "start_retry_deadline": prepared.claim.start_retry_deadline or now + timedelta(hours=23),
        }
    )
    launcher = SimpleNamespace(
        history_retention_seconds=AsyncMock(return_value=259200),
        start=AsyncMock(return_value=acceptance(prepared)),
        describe=AsyncMock(side_effect=EventLaunchError(SchedulingFailureCode.TEMPORAL_NOT_FOUND)),
    )
    service = EventAdmissionService(MagicMock(), launcher)
    monkeypatch.setattr(service, "_reload", AsyncMock(return_value=prepared))
    monkeypatch.setattr(service, "_record_attempt", AsyncMock(return_value=attempted))
    resolved = ResolvedDelivery(
        terminal=TerminalDelivery(
            identity=prepared.claim.identity,
            state=DeliveryState.SCHEDULED,
            resolved_at=now,
            execution_id=prepared.execution_id,
            temporal_run_id="accepted-run",
            execution_confirmed_at=now,
        )
    )
    monkeypatch.setattr(service, "_confirm", AsyncMock(return_value=resolved))
    monkeypatch.setattr(
        service,
        "_failure",
        AsyncMock(return_value=BlockedDelivery(error_code=SchedulingFailureCode.TEMPORAL_UNAVAILABLE)),
    )
    return service, launcher, attempted


async def test_start_follows_attempt_commit_and_uses_reloaded_arguments(prepared, monkeypatch) -> None:
    service, launcher, attempted = harness(prepared, monkeypatch)
    assert isinstance(attempted, DeliveryClaim)
    events = []

    async def record(_prepared: PreparedExecution, _retention: int) -> DeliveryClaim:
        events.append("attempt_committed")
        return attempted

    async def start(value: PreparedExecution) -> TemporalAcceptance:
        assert events == ["attempt_committed"]
        assert value.workflow_arguments() == prepared.workflow_arguments()
        assert value.claim.attempt_count == 1
        events.append("start")
        return acceptance(value)

    service._record_attempt.side_effect = record
    launcher.start.side_effect = start
    caller = prepared.model_copy(update={"input_data": {"tampered": True}})
    assert isinstance(await service.schedule(caller), ResolvedDelivery)
    assert events == ["attempt_committed", "start"]


async def test_lost_token_prevents_rpc(prepared, monkeypatch) -> None:
    service, launcher, _ = harness(prepared, monkeypatch)
    service._record_attempt.return_value = ClaimLost()
    assert isinstance(await service.schedule(prepared), ClaimLost)
    launcher.start.assert_not_awaited()
    service._confirm.assert_not_awaited()


@pytest.mark.parametrize(
    "failure", [SchedulingFailureCode.TEMPORAL_NOT_FOUND, SchedulingFailureCode.TEMPORAL_UNAVAILABLE]
)
async def test_expired_ambiguity_blocks_even_on_timeout(prepared, monkeypatch, failure) -> None:
    now = datetime.now(UTC)
    prepared = prepared.model_copy(
        update={
            "claim": prepared.claim.model_copy(
                update={
                    "attempt_count": 1,
                    "first_start_attempt_at": now - timedelta(days=5),
                    "start_retry_deadline": now - timedelta(days=4),
                }
            )
        }
    )
    service, launcher, _ = harness(prepared, monkeypatch)
    launcher.describe.side_effect = EventLaunchError(failure)
    await service.schedule(prepared)
    captured = service._failure.call_args.args[1]
    assert captured.code == SchedulingFailureCode.HISTORY_EXPIRED
    assert not captured.transient
    launcher.start.assert_not_awaited()
    service._record_attempt.assert_not_awaited()


async def test_mismatch_blocks_without_start(prepared, monkeypatch) -> None:
    prepared = prepared.model_copy(update={"claim": prepared.claim.model_copy(update={"attempt_count": 1})})
    service, launcher, _ = harness(prepared, monkeypatch)
    launcher.describe.side_effect = EventLaunchError(SchedulingFailureCode.EVIDENCE_MISMATCH, transient=False)
    await service.schedule(prepared)
    assert service._failure.call_args.args[1].code == SchedulingFailureCode.EVIDENCE_MISMATCH
    launcher.start.assert_not_awaited()


@pytest.mark.parametrize("phase", ["reload", "attempt"])
async def test_value_error_uses_nontransient_failure_path(prepared, monkeypatch, phase) -> None:
    service, launcher, _ = harness(prepared, monkeypatch)
    failure = ValueError("PRIVATE")
    if phase == "reload":
        service._reload.side_effect = failure
    else:
        service._record_attempt.side_effect = failure
    blocked = BlockedDelivery(error_code=SchedulingFailureCode.EVIDENCE_MISMATCH)
    service._failure.return_value = blocked
    assert await service.schedule(prepared) is blocked
    claim, recorded = service._failure.call_args.args
    assert claim == prepared.claim
    assert recorded.code == SchedulingFailureCode.EVIDENCE_MISMATCH
    assert not recorded.transient
    launcher.start.assert_not_awaited()
    service._confirm.assert_not_awaited()


async def test_value_error_cannot_park_a_lost_token(prepared, monkeypatch) -> None:
    service, launcher, _ = harness(prepared, monkeypatch)
    service._reload.side_effect = ValueError("PRIVATE")
    service._failure.return_value = ClaimLost()
    assert isinstance(await service.schedule(prepared), ClaimLost)
    launcher.start.assert_not_awaited()


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (OperationalError("park", {}, RuntimeError("PRIVATE")), SchedulingFailureCode.STORAGE_UNAVAILABLE),
        (ValueError("PRIVATE"), SchedulingFailureCode.EVIDENCE_MISMATCH),
    ],
)
async def test_value_error_stays_blocked_when_parking_fails(prepared, monkeypatch, failure, code) -> None:
    service, launcher, _ = harness(prepared, monkeypatch)
    service._reload.side_effect = ValueError("PRIVATE")
    service._failure.side_effect = failure
    result = await service.schedule(prepared)
    assert isinstance(result, BlockedDelivery)
    assert result.error_code == code
    launcher.start.assert_not_awaited()
    service._confirm.assert_not_awaited()


@pytest.mark.parametrize("transient", [False, True])
async def test_failed_start_is_described_before_confirmation(prepared, monkeypatch, *, transient) -> None:
    service, launcher, _ = harness(prepared, monkeypatch)
    launcher.start.side_effect = EventLaunchError(SchedulingFailureCode.TEMPORAL_UNAVAILABLE, transient=transient)
    launcher.describe.side_effect = None
    launcher.describe.return_value = acceptance(prepared)
    assert isinstance(await service.schedule(prepared), ResolvedDelivery)
    launcher.start.assert_awaited_once()
    launcher.describe.assert_awaited_once()
    service._failure.assert_not_awaited()


@pytest.mark.parametrize(
    "recovery_code",
    [
        SchedulingFailureCode.TEMPORAL_UNAVAILABLE,
        SchedulingFailureCode.TEMPORAL_NOT_FOUND,
        SchedulingFailureCode.EVIDENCE_MISMATCH,
    ],
)
async def test_permanent_start_failure_survives_inconclusive_recovery(prepared, monkeypatch, recovery_code) -> None:
    service, launcher, _ = harness(prepared, monkeypatch)
    failure = EventLaunchError(SchedulingFailureCode.TEMPORAL_UNAVAILABLE, transient=False)
    recovery = EventLaunchError(recovery_code, transient=recovery_code != SchedulingFailureCode.EVIDENCE_MISMATCH)
    launcher.start.side_effect = failure
    launcher.describe.side_effect = recovery
    await service.schedule(prepared)
    recorded = service._failure.call_args.args[1]
    assert recorded is (recovery if recovery_code == SchedulingFailureCode.EVIDENCE_MISMATCH else failure)
    assert not recorded.transient
    launcher.start.assert_awaited_once()
    launcher.describe.assert_awaited_once()
    service._confirm.assert_not_awaited()


async def test_shorter_namespace_retention_prevents_start(prepared, monkeypatch) -> None:
    service, launcher, _ = harness(prepared, monkeypatch)
    launcher.history_retention_seconds.return_value = 3600
    await service.schedule(prepared)
    assert service._failure.call_args.args[1].code == SchedulingFailureCode.HISTORY_UNAVAILABLE
    service._record_attempt.assert_not_awaited()
    launcher.start.assert_not_awaited()


@pytest.mark.parametrize(
    ("committed", "other_attempt", "failed_before_write"),
    [(False, False, False), (True, False, False), (False, True, False), (False, True, True)],
)
async def test_uncertain_attempt_commit_is_reconciled_before_start(
    prepared, monkeypatch, *, committed, other_attempt, failed_before_write
) -> None:
    service, launcher, attempted = harness(prepared, monkeypatch)
    assert isinstance(attempted, DeliveryClaim)
    # Exercise the real transaction/reconciliation implementation, isolating only
    # the database adapter and its commit response.
    monkeypatch.setattr(service, "_record_attempt", EventAdmissionService._record_attempt.__get__(service))
    session = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    transaction = MagicMock()
    session.begin.return_value = transaction
    failure = OperationalError("commit", {}, RuntimeError("PRIVATE"))
    transaction.__aexit__.side_effect = [None if failed_before_write else failure, None]
    execution = SimpleNamespace(
        project_id=UUID(int=9),
        execution_metadata={EVENT_DELIVERY_METADATA_KEY: {"start_attempt_id": str(uuid4()) if other_attempt else None}},
    )
    session.get = AsyncMock(return_value=execution)
    session.exec = AsyncMock(return_value=MagicMock(one=MagicMock(return_value=datetime.now(UTC))))
    service._session_factory = lambda: session
    store = SimpleNamespace(
        renew=AsyncMock(
            side_effect=[
                failure if failed_before_write else prepared.claim,
                attempted if committed or other_attempt else prepared.claim,
            ]
        ),
        record_start_attempt=AsyncMock(),
        lookup_terminal=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(module, "EventDeliveryStore", lambda _value: store)

    async def record(_claim: DeliveryClaim, *, retry_deadline: datetime, attempt_id: UUID) -> DeliveryClaim:
        if committed:
            execution.execution_metadata[EVENT_DELIVERY_METADATA_KEY]["start_attempt_id"] = str(attempt_id)
        return attempted

    store.record_start_attempt.side_effect = record
    provider = SimpleNamespace(resolve_frozen=AsyncMock())
    monkeypatch.setattr(module, "EventConnectionProvider", lambda _value: provider)

    async def start(value: PreparedExecution) -> TemporalAcceptance:
        assert store.renew.await_count == 2
        assert store.record_start_attempt.await_count == 1
        assert transaction.__aexit__.await_count == 2
        return acceptance(value)

    launcher.start.side_effect = start
    await service.schedule(prepared)
    if committed:
        launcher.start.assert_awaited_once()
        service._confirm.assert_awaited_once()
    else:
        launcher.start.assert_not_awaited()
        assert service._failure.call_args.args[1].code == SchedulingFailureCode.ATTEMPT_UNCERTAIN
    assert store.record_start_attempt.await_count == (0 if failed_before_write else 1)
