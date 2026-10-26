"""Shared preparation/finalization bounds, session ownership, and admission fencing."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.core.handler import BlockedDelivery, SchedulingFailureCode
from syntara.eventstreams.core.preparation import PreparationBlocked, PreparedExecution
from syntara.eventstreams.services.admission_service import EventAdmissionService
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.eventstreams.services.recovery_worker import EventDeliveryRecoveryWorker
from syntara.eventstreams.services.worker_gate import EventWorkerGate
from syntara.eventstreams.services.worker_resources import EventWorkerResources
from tests.unit.eventstreams.test_consumer_service import eventually
from tests.unit.eventstreams.test_execution_preparation_service import preparation_context


class TrackingSessionFactory:
    """Observe independent session/transaction scopes without a database."""

    def __init__(self) -> None:
        """Keep strong references and observe active transaction scopes."""
        self.sessions: list[MagicMock] = []
        self.active: set[int] = set()
        self.transactions: set[int] = set()

    def __call__(self) -> MagicMock:
        session = MagicMock(spec=AsyncSession)
        key = len(self.sessions)
        self.sessions.append(session)

        async def enter() -> MagicMock:
            self.active.add(key)
            return session

        async def leave(*_args: object) -> None:
            self.active.remove(key)

        async def begin() -> None:
            self.transactions.add(key)

        async def end(*_args: object) -> None:
            self.transactions.remove(key)

        session.__aenter__.side_effect = enter
        session.__aexit__.side_effect = leave
        session.begin.return_value.__aenter__.side_effect = begin
        session.begin.return_value.__aexit__.side_effect = end
        return session


@pytest.fixture
def healthy_gate() -> MagicMock:
    gate = MagicMock(spec=EventWorkerGate)
    gate.scheduling_open = True
    return gate


def test_missing_gate_preserves_failures_and_closed_admission_until_composed():
    resources = EventWorkerResources()
    assert not resources.scheduling_open
    resources.database_failed()
    resources.close_admission()
    gate = MagicMock(spec=EventWorkerGate)
    gate.scheduling_open = False
    resources.gate = gate
    gate.database_failed.assert_called_once()
    gate.close_admission.assert_called_once()
    assert not resources.scheduling_open
    assert not resources.accepting


@pytest.mark.parametrize("remove_gate", [False, True])
def test_installed_gate_cannot_be_replaced_to_clear_database_failure(remove_gate):
    gate = EventWorkerGate(MagicMock(), clock=lambda: 100.0)
    gate.membership_confirmed(160.0, generation=gate.generation)
    assert gate.reconciled([], set(), generation=gate.generation, started=100.0)
    resources = EventWorkerResources(gate)
    assert resources.scheduling_open
    resources.database_failed()
    assert not resources.scheduling_open
    replacement = None if remove_gate else MagicMock(spec=EventWorkerGate)
    if replacement is not None:
        replacement.scheduling_open = True
    with pytest.raises(ValueError, match="already installed"):
        resources.gate = replacement
    assert resources.gate is gate
    assert not resources.scheduling_open
    resources.gate = gate
    assert not resources.scheduling_open


async def test_missing_gate_blocks_preparation_scheduling_and_recovery_claims(monkeypatch):
    context = preparation_context(monkeypatch)
    resources = EventWorkerResources()
    sessions, launcher = MagicMock(), MagicMock()
    preparation = EventExecutionPreparationService(sessions, resources=resources)
    result = await preparation.prepare_delivery(context.snapshot, context.identity, context.envelope, "worker")
    assert isinstance(result, PreparationBlocked)
    admission = EventAdmissionService(sessions, launcher, resources=resources)
    assert isinstance(await admission.recover_claim(context.claim), BlockedDelivery)
    recovery = EventDeliveryRecoveryWorker(sessions, launcher, admission=admission, resources=resources)
    assert await recovery._claim_and_recover_one() is None
    sessions.assert_not_called()
    launcher.start.assert_not_called()
    launcher.describe.assert_not_called()


async def test_shared_preparation_bounds_sessions_and_rechecks_closed_admission(monkeypatch, healthy_gate):
    context = preparation_context(monkeypatch)
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    resources = EventWorkerResources(healthy_gate)
    resources.preparation = asyncio.Semaphore(2)
    sessions = TrackingSessionFactory()
    service = EventExecutionPreparationService(sessions, resources=resources)
    entered = []
    release = asyncio.Event()

    async def prepare(session, *_args: object) -> PreparedExecution:
        entered.append(session)
        assert len(sessions.active) <= 2
        await release.wait()
        return prepared

    monkeypatch.setattr(service, "_prepare", prepare)
    tasks = [
        asyncio.create_task(service.prepare_delivery(context.snapshot, context.identity, context.envelope, "worker"))
        for _ in range(4)
    ]
    await eventually(lambda: len(entered) == 2)
    assert entered[0] is not entered[1]
    resources.close_admission()
    release.set()
    results = await asyncio.gather(*tasks)
    assert sum(isinstance(result, PreparedExecution) for result in results) == 2
    assert sum(isinstance(result, PreparationBlocked) for result in results) == 2
    assert len(sessions.sessions) == 2
    assert not sessions.active
    assert not sessions.transactions
    recovered = await service.prepare_delivery(context.snapshot, context.identity, None, "worker", claim=prepared.claim)
    assert isinstance(recovered, PreparedExecution)


async def test_finalization_limit_is_shared_across_services(monkeypatch, healthy_gate):
    resources = EventWorkerResources(healthy_gate)
    resources.finalization = asyncio.Semaphore(1)
    services = [EventAdmissionService(MagicMock(), MagicMock(), resources=resources) for _ in range(2)]
    entered = []
    release = asyncio.Event()

    async def finalize(*_args: object) -> BlockedDelivery:
        entered.append(True)
        await release.wait()
        return BlockedDelivery(error_code=SchedulingFailureCode.STORAGE_UNAVAILABLE)

    for service in services:
        monkeypatch.setattr(service, "_finalize", finalize)
    tasks = [asyncio.create_task(service._confirm(MagicMock(), MagicMock())) for service in services]
    await eventually(lambda: bool(entered))
    assert len(entered) == 1
    release.set()
    await asyncio.gather(*tasks)
    assert len(entered) == 2


@pytest.mark.parametrize("close_during", ["session", "transaction"])
@pytest.mark.parametrize("existing_claim", [False, True])
async def test_preparation_rechecks_admission_after_session_entry(
    monkeypatch, close_during, existing_claim, healthy_gate
):
    context = preparation_context(monkeypatch)
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    resources = EventWorkerResources(healthy_gate)
    session: MagicMock = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    entry = session if close_during == "session" else session.begin.return_value

    async def enter() -> MagicMock:
        resources.close_admission()
        return session

    entry.__aenter__.side_effect = enter
    service = EventExecutionPreparationService(MagicMock(return_value=session), resources=resources)
    prepare = AsyncMock(return_value=prepared)
    monkeypatch.setattr(service, "_prepare", prepare)
    claim = prepared.claim if existing_claim else None
    result = await service.prepare_delivery(context.snapshot, context.identity, context.envelope, "worker", claim=claim)
    assert not resources.accepting
    if existing_claim:
        assert result is prepared
        prepare.assert_awaited_once_with(session, context.snapshot, context.identity, context.envelope, "worker", claim)
    else:
        assert isinstance(result, PreparationBlocked)
        prepare.assert_not_awaited()
    session.__aexit__.assert_awaited_once()
    session.begin.return_value.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("close_during", ["session", "transaction"])
async def test_recovery_rechecks_claim_fence_after_session_entry(monkeypatch, close_during):
    session: MagicMock = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    admission = MagicMock(spec=EventAdmissionService)
    worker = EventDeliveryRecoveryWorker(MagicMock(return_value=session), MagicMock(), admission=admission)
    entry = session if close_during == "session" else session.begin.return_value

    async def enter() -> MagicMock:
        worker.close_claims()
        return session

    entry.__aenter__.side_effect = enter
    store = MagicMock()
    store.claim_due = AsyncMock(return_value=[MagicMock()])
    construct = MagicMock(return_value=store)
    monkeypatch.setattr("syntara.eventstreams.services.recovery_worker.EventDeliveryStore", construct)
    assert await worker._claim_and_recover_one() is None
    assert worker.draining
    construct.assert_not_called()
    store.claim_due.assert_not_awaited()
    admission.recover_claim.assert_not_awaited()
    session.__aexit__.assert_awaited_once()
    session.begin.return_value.__aexit__.assert_awaited_once()


async def test_recovery_waiting_for_shared_work_does_not_claim_after_close(healthy_gate):
    resources = EventWorkerResources(healthy_gate)
    resources.processing = asyncio.Semaphore(0)
    sessions = MagicMock()
    worker = EventDeliveryRecoveryWorker(sessions, MagicMock(), resources=resources)
    task = asyncio.create_task(worker._claim_and_recover_one())
    await asyncio.sleep(0)
    sessions.assert_not_called()
    worker.close_claims()
    resources.processing.release()
    assert await task is None
    sessions.assert_not_called()


async def test_recovery_closes_claim_session_before_admission(monkeypatch, healthy_gate):
    sessions = TrackingSessionFactory()
    claim = MagicMock()
    store = MagicMock()
    store.claim_due = AsyncMock(return_value=[claim])
    monkeypatch.setattr("syntara.eventstreams.services.recovery_worker.EventDeliveryStore", lambda _session: store)

    async def recover(current) -> BlockedDelivery:
        assert current is claim
        assert not sessions.active
        assert not sessions.transactions
        return BlockedDelivery(error_code=SchedulingFailureCode.TEMPORAL_UNAVAILABLE)

    admission = MagicMock()
    admission.recover_claim = AsyncMock(side_effect=recover)
    worker = EventDeliveryRecoveryWorker(
        sessions, MagicMock(), admission=admission, resources=EventWorkerResources(healthy_gate)
    )
    await worker._claim_and_recover_one()
    store.claim_due.assert_awaited_once_with("recovery-scanner", limit=1, prepared_only=True)
