"""PostgreSQL worker reconciliation and independent recovery with isolated transports."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import get_settings
from syntara.eventstreams import consumer_lifecycle as lifecycle
from syntara.eventstreams.consumer_service import EventWorkerManager
from syntara.eventstreams.core.deduplication import DeliveryState, RecoveryReservation
from syntara.eventstreams.core.placement import WorkerIdentity
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.recovery_hold import EventDeliveryRecoveryHold
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.services.admission_service import EventAdmissionService
from syntara.eventstreams.services.delivery_retention_service import EventDeliveryRetentionService
from syntara.eventstreams.services.placement_service import SubscriptionPlacementService
from syntara.eventstreams.services.recovery_worker import EventDeliveryRecoveryWorker
from syntara.eventstreams.services.subscription_reader import EventSubscriptionReader
from syntara.eventstreams.services.worker_resources import EventWorkerResources
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow import Workflow
from tests.helpers.eventstream_runtime import IsolatedSubscriptionRunner
from tests.integration.eventstreams import test_execution_scheduling
from tests.integration.eventstreams.conftest import DeliveryContext
from tests.integration.eventstreams.test_execution_preparation import envelope
from tests.integration.eventstreams.test_execution_preparation import service as preparation_service

pytestmark = pytest.mark.integration
scheduling_context = test_execution_scheduling.scheduling_context


async def eventually(predicate) -> None:
    async with asyncio.timeout(5):
        while not predicate():  # noqa: ASYNC110 - bounded polling across database and runtime observations
            await asyncio.sleep(0)


async def disable(context: DeliveryContext, state: str) -> None:
    async with context.session_factory() as session, session.begin():
        subscription = await session.get(EventSubscription, context.snapshot.subscription_id)
        assert subscription is not None
        if state == "paused":
            subscription.paused = True
        elif state == "unpublished":
            workflow = await session.get(Workflow, context.snapshot.workflow_id)
            assert workflow is not None
            workflow.published_version_id = None
            workflow.is_enabled = False
            subscription.desired_enabled = False
        else:
            assert state == "retired"
            subscription.retired = True
            subscription.desired_enabled = False
            source = await session.get(EventSubscriptionSource, context.snapshot.source_id)
            assert source is not None
            source.retired_at = datetime.now(UTC)


@pytest.mark.parametrize("state", ["paused", "unpublished", "retired"])
async def test_reader_tracks_persisted_active_state(delivery_context, state):
    context = delivery_context
    sessions = []

    def factory() -> AsyncSession:
        session: AsyncSession = context.session_factory()
        sessions.append(session)
        return session

    reader = EventSubscriptionReader(factory, deployment_id=context.snapshot.deployment_id)
    snapshots = await asyncio.gather(*(reader.read() for _ in range(3)))
    assert all(rows == [context.snapshot] for rows in snapshots)
    assert len({id(session) for session in sessions}) == 3
    assert all(not session.in_transaction() for session in sessions)
    foreign = EventSubscriptionReader(factory, deployment_id=uuid4())
    assert await foreign.read() == []
    await disable(context, state)
    assert await reader.read() == []


async def test_recovery_hold_reader_is_scoped_to_the_process_deployment(delivery_context):
    context = delivery_context
    retention = EventDeliveryRetentionService(context.session_factory)
    reservation = await retention.reserve_recovery(context.snapshot.source_id)
    assert reservation is not None
    reader = EventSubscriptionReader(context.session_factory, deployment_id=context.snapshot.deployment_id)
    foreign = EventSubscriptionReader(context.session_factory, deployment_id=uuid4())
    try:
        assert await reader.recovery_holds() == {context.snapshot.source_id}
        assert await foreign.recovery_holds() == set()
    finally:
        assert await retention.release_recovery(reservation)


async def test_processes_share_one_committed_placement_and_stop_on_hint(delivery_context):
    context = delivery_context
    runners = []

    async def construct(snapshot) -> IsolatedSubscriptionRunner:
        async with context.session_factory() as session:
            subscription = await session.get(EventSubscription, snapshot.subscription_id)
            assert subscription is not None
            assert subscription.assigned_worker_id == providers[0].worker.worker_id
            assert subscription.assignment_lease_until is not None
        runner = IsolatedSubscriptionRunner(snapshot, [])
        runners.append(runner)
        return runner

    factories = [AsyncMock(side_effect=construct), AsyncMock(side_effect=construct)]
    providers = [await SubscriptionPlacementService.create(context.session_factory) for _ in range(2)]
    providers.sort(key=lambda provider: provider.worker.worker_id)
    managers = [
        EventWorkerManager(
            EventSubscriptionReader(context.session_factory, deployment_id=provider.worker.deployment_id),
            factory,
            provider,
            EventWorkerResources(),
        )
        for factory, provider in zip(factories, providers, strict=True)
    ]
    try:
        for manager in managers:
            await manager.start()
        await eventually(lambda: len(runners) == 1 and runners[0].started)
        await asyncio.gather(*(manager.reconcile() for manager in managers))
        assert factories[0].await_count == 1
        factories[1].assert_not_awaited()
        assert all(manager.ready for manager in managers)
        assert managers[0].owned_subscription_ids == {context.snapshot.subscription_id}
        assert not managers[1].owned_subscription_ids
        await disable(context, "paused")
        for manager in managers:
            manager.request_reconcile()
        await eventually(lambda: all(not manager.subscription_ids for manager in managers))
        assert all(runner.stopped for runner in runners)
        assert all(manager.ready for manager in managers)
    finally:
        await asyncio.gather(*(manager.stop() for manager in managers))


async def _prepare_recovery_state(
    context: test_execution_scheduling.SchedulingContext, state: str
) -> tuple[EventDeliveryRetentionService, RecoveryReservation | None]:
    if state in {"paused", "unpublished", "retired"}:
        await disable(context.delivery, state)
    retention = EventDeliveryRetentionService(context.delivery.session_factory)
    reservation = None
    if state == "recovery_hold":
        await disable(context.delivery, "paused")
        reservation = await retention.reserve_recovery(context.delivery.snapshot.source_id)
        assert reservation is not None
    await context.delivery.expire(context.prepared.claim)
    return retention, reservation


async def _wait_for_scheduled(context: test_execution_scheduling.SchedulingContext) -> None:
    async with asyncio.timeout(5):
        while True:
            async with context.delivery.session_factory() as session:
                row = await session.get(EventDelivery, context.prepared.claim.identity.digest)
                assert row is not None
                if row.state == DeliveryState.SCHEDULED:
                    break
            await asyncio.sleep(0)


@pytest.mark.parametrize(
    "state", ["paused", "unpublished", "retired", "blocked_startup", "zero_target", "recovery_hold"]
)
async def test_scanner_recovers_independently_of_consumers(scheduling_context, state):
    context = scheduling_context
    retention, reservation = await _prepare_recovery_state(context, state)
    release = asyncio.Event()
    runners = []

    def construct(snapshot) -> IsolatedSubscriptionRunner:
        runner = IsolatedSubscriptionRunner(snapshot, [])
        runner.start_release = release
        runners.append(runner)
        return runner

    factory = AsyncMock(side_effect=construct)
    resources = EventWorkerResources()
    placement = await SubscriptionPlacementService.create(context.delivery.session_factory)
    other = None
    if state == "zero_target":
        other = SubscriptionPlacementService(
            context.delivery.session_factory,
            WorkerIdentity(deployment_id=placement.worker.deployment_id, worker_id=UUID(int=0)),
        )
        await other.heartbeat_worker(other.worker, draining=False)
    manager = EventWorkerManager(
        EventSubscriptionReader(context.delivery.session_factory, deployment_id=placement.worker.deployment_id),
        factory,
        placement,
        resources,
    )
    admission = EventAdmissionService(context.delivery.session_factory, context.temporal, resources=resources)
    recovery = EventDeliveryRecoveryWorker(
        context.delivery.session_factory,
        context.temporal,
        admission=admission,
        resources=resources,
        interval_seconds=0.01,
    )
    hints = SimpleNamespace(start=MagicMock(), stop=AsyncMock())
    shutdown = asyncio.Event()
    process = asyncio.create_task(
        lifecycle.run_event_worker(manager, recovery, resources, hints, shutdown_event=shutdown)
    )
    try:
        await _wait_for_scheduled(context)
        assert manager.ready
        assert len(context.temporal.starts) == 1
        assert context.temporal.starts[0].workflow_arguments() == context.prepared.workflow_arguments()
        if state == "blocked_startup":
            assert len(runners) == 1
            assert not runners[0].started
        else:
            factory.assert_not_awaited()
            assert not manager.owned_subscription_ids
        async with context.delivery.session_factory() as session:
            execution = await session.get(Execution, context.prepared.execution_id)
            assert execution is not None
            assert execution.execution_metadata["event_delivery"]["scheduling_state"] == "confirmed"
            if reservation is not None:
                hold = await session.get(EventDeliveryRecoveryHold, reservation.token)
                assert hold is not None
                assert hold.released_at is None
    finally:
        shutdown.set()
        await process
        release.set()
        if other is not None:
            await other.heartbeat_worker(other.worker, draining=True)
        if reservation is not None:
            assert await retention.release_recovery(reservation)


async def test_shutdown_stops_claims_and_preserves_waiting_preparation(scheduling_context, monkeypatch):
    context = scheduling_context
    await context.delivery.expire(context.prepared.claim)
    second = await preparation_service(context.delivery).prepare_delivery(
        context.delivery.snapshot, context.delivery.identity(42), await envelope(context.delivery, offset=42), "first"
    )
    assert isinstance(second, PreparedExecution)
    await context.delivery.expire(second.claim)
    await disable(context.delivery, "paused")
    entered, release = asyncio.Event(), asyncio.Event()

    async def block() -> None:
        entered.set()
        await release.wait()

    context.temporal.before_first_start = block
    resources = EventWorkerResources()
    resources.processing = asyncio.Semaphore(1)
    placement = await SubscriptionPlacementService.create(context.delivery.session_factory)
    manager = EventWorkerManager(
        EventSubscriptionReader(context.delivery.session_factory, deployment_id=placement.worker.deployment_id),
        AsyncMock(),
        placement,
        resources,
    )
    admission = EventAdmissionService(context.delivery.session_factory, context.temporal, resources=resources)
    recovery = EventDeliveryRecoveryWorker(
        context.delivery.session_factory,
        context.temporal,
        admission=admission,
        resources=resources,
        interval_seconds=0.01,
    )
    hints = SimpleNamespace(start=MagicMock(), stop=AsyncMock())
    shutdown = asyncio.Event()
    settings = get_settings().model_copy(update={"event_drain_timeout_seconds": 0.2})
    monkeypatch.setattr(lifecycle, "get_settings", lambda: settings)
    process = asyncio.create_task(
        lifecycle.run_event_worker(manager, recovery, resources, hints, shutdown_event=shutdown)
    )
    try:
        async with asyncio.timeout(5):
            await entered.wait()
        shutdown.set()
        await eventually(lambda: recovery.draining)
        assert not resources.accepting
        release.set()
        await process
        assert len(context.temporal.starts) == 1
        async with context.delivery.session_factory() as session:
            row = await session.get(EventDelivery, second.claim.identity.digest)
            assert row is not None
            assert row.state == DeliveryState.IN_PROGRESS
            assert row.frozen_binding == second.claim.binding
            assert row.claim_token == second.claim.token
    finally:
        release.set()
        shutdown.set()
        await asyncio.gather(process, return_exceptions=True)
