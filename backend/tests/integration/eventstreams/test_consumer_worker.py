"""PostgreSQL worker reconciliation and independent recovery with isolated transports."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import get_settings
from syntara.eventstreams import consumer_lifecycle as lifecycle
from syntara.eventstreams.consumer_service import EventWorkerManager
from syntara.eventstreams.core.deduplication import DeliveryState
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.services.admission_service import EventAdmissionService
from syntara.eventstreams.services.recovery_worker import EventDeliveryRecoveryWorker
from syntara.eventstreams.services.subscription_reader import EventSubscriptionReader
from syntara.eventstreams.services.worker_resources import EventWorkerResources
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow import Workflow
from tests.helpers.eventstream_runtime import IsolatedSubscriptionRunner
from tests.integration.eventstreams import test_execution_scheduling

pytestmark = pytest.mark.integration
scheduling_context = test_execution_scheduling.scheduling_context


async def eventually(predicate) -> None:
    async with asyncio.timeout(5):
        while not predicate():  # noqa: ASYNC110 - bounded polling across database and runtime observations
            await asyncio.sleep(0)


async def disable(context, state):
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

    reader = EventSubscriptionReader(factory)
    snapshots = await asyncio.gather(*(reader.read() for _ in range(3)))
    assert all(rows == [context.snapshot] for rows in snapshots)
    assert len({id(session) for session in sessions}) == 3
    assert all(not session.in_transaction() for session in sessions)
    await disable(context, state)
    assert await reader.read() == []


async def test_each_process_reconciles_one_local_client_and_stops_on_hint(delivery_context):
    context = delivery_context
    runners = []

    def construct(snapshot) -> IsolatedSubscriptionRunner:
        runner = IsolatedSubscriptionRunner(snapshot, [])
        runners.append(runner)
        return runner

    factories = [AsyncMock(side_effect=construct), AsyncMock(side_effect=construct)]
    managers = [EventWorkerManager(EventSubscriptionReader(context.session_factory), factory) for factory in factories]
    try:
        await asyncio.gather(*(manager.start() for manager in managers))
        await eventually(lambda: len(runners) == 2 and all(runner.started for runner in runners))
        await asyncio.gather(*(manager.reconcile() for manager in managers))
        assert all(factory.await_count == 1 for factory in factories)
        assert all(manager.ready for manager in managers)
        assert runners[0].snapshot.configuration == runners[1].snapshot.configuration
        await disable(context, "paused")
        for manager in managers:
            manager.request_reconcile()
        await eventually(lambda: all(not manager.subscription_ids for manager in managers))
        assert all(runner.stopped for runner in runners)
        assert all(manager.ready for manager in managers)
    finally:
        await asyncio.gather(*(manager.stop() for manager in managers))


@pytest.mark.parametrize("state", ["paused", "unpublished", "retired", "blocked_startup"])
async def test_scanner_recovers_independently_of_consumers(scheduling_context, state):
    context = scheduling_context
    if state != "blocked_startup":
        await disable(context.delivery, state)
    await context.delivery.expire(context.prepared.claim)
    release = asyncio.Event()
    runners = []

    def construct(snapshot) -> IsolatedSubscriptionRunner:
        runner = IsolatedSubscriptionRunner(snapshot, [])
        runner.start_release = release
        runners.append(runner)
        return runner

    factory = AsyncMock(side_effect=construct)
    manager = EventWorkerManager(EventSubscriptionReader(context.delivery.session_factory), factory)
    resources = EventWorkerResources()
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
        async with asyncio.timeout(5):
            while True:
                async with context.delivery.session_factory() as session:
                    row = await session.get(EventDelivery, context.prepared.claim.identity.digest)
                    assert row is not None
                    if row.state == DeliveryState.SCHEDULED:
                        break
                await asyncio.sleep(0)
        assert manager.ready
        assert len(context.temporal.starts) == 1
        assert context.temporal.starts[0].workflow_arguments() == context.prepared.workflow_arguments()
        if state == "blocked_startup":
            assert len(runners) == 1
            assert not runners[0].started
        else:
            factory.assert_not_awaited()
        async with context.delivery.session_factory() as session:
            execution = await session.get(Execution, context.prepared.execution_id)
            assert execution is not None
            assert execution.execution_metadata["event_delivery"]["scheduling_state"] == "confirmed"
    finally:
        shutdown.set()
        await process
        release.set()


async def test_shutdown_stops_claims_and_preserves_waiting_preparation(scheduling_context, monkeypatch):
    context = scheduling_context
    await disable(context.delivery, "paused")
    await context.delivery.expire(context.prepared.claim)
    second = await context.delivery.claim(42, prepare=True)
    await context.delivery.expire(second)
    entered, release = asyncio.Event(), asyncio.Event()

    async def block() -> None:
        entered.set()
        await release.wait()

    context.temporal.before_first_start = block
    resources = EventWorkerResources()
    resources.processing = asyncio.Semaphore(1)
    manager = EventWorkerManager(EventSubscriptionReader(context.delivery.session_factory), AsyncMock())
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
            row = await session.get(EventDelivery, second.identity.digest)
            assert row is not None
            assert row.state == DeliveryState.IN_PROGRESS
            assert row.frozen_binding == second.binding
            assert row.claim_token == second.token
    finally:
        release.set()
        shutdown.set()
        await asyncio.gather(process, return_exceptions=True)
