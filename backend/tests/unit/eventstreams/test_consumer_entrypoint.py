"""Process composition, independent recovery, signals, and shared-client teardown."""

import asyncio
import signal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from syntara.core.config.base import get_settings
from syntara.core.constants import EventWorkerDefaults
from syntara.core.lib.encryption import SecretEncryptor
from syntara.eventstreams import consumer_entrypoint as entrypoint
from syntara.eventstreams import consumer_lifecycle as lifecycle
from syntara.eventstreams.consumer_service import EventWorkerManager
from syntara.eventstreams.services.recovery_worker import EventDeliveryRecoveryWorker
from syntara.eventstreams.services.subscription_hints import SubscriptionHintListener
from syntara.eventstreams.services.subscription_reader import EventSubscriptionReader
from syntara.eventstreams.services.worker_resources import EventWorkerResources
from syntara.workflows.workflow_engine.services import temporal_execution_service as temporal_module
from tests.helpers.eventstream_runtime import IsolatedSubscriptionRunner
from tests.helpers.eventstream_worker import IsolatedPlacementPool, IsolatedPlacementService
from tests.unit.eventstreams import test_consumer_service as consumer_tests
from tests.unit.eventstreams.test_connection_provider import connection_context
from tests.unit.eventstreams.test_consumer_service import eventually
from tests.unit.eventstreams.test_worker_resources import TrackingSessionFactory

manager_context = consumer_tests.manager_context


async def test_composition_shares_one_client_factory_and_resource_limits(monkeypatch):
    sessions, client = MagicMock(), MagicMock()
    service = temporal_module.TemporalExecutionService(client, "user", background_task_queue="builtin")
    resources = EventWorkerResources()
    shutdown = asyncio.Event()
    captured = []
    snapshot = connection_context().snapshot
    placement = IsolatedPlacementService(IsolatedPlacementPool(snapshot.deployment_id))
    create_placement = AsyncMock(return_value=placement)
    redis = MagicMock()
    redis.disconnect = AsyncMock()

    async def run(manager, recovery, shared, hints, **kwargs: object) -> None:
        captured.append(True)
        assert shared is resources
        assert kwargs["shutdown_event"] is shutdown
        assert manager._reader._session_factory is sessions
        assert manager._factory._session_factory is sessions
        assert manager._factory._resources is shared
        assert recovery._resources is shared
        assert manager._factory._admission is recovery._admission
        assert recovery._admission._launcher._client is client
        assert recovery._admission._preparation._resources is shared
        assert manager._factory._preparation._resources is shared
        assert hints._request == manager.request_reconcile
        assert manager._placement is placement
        assert manager._factory._lookup is recovery._admission._cache
        assert manager._factory._lookup.cache is redis
        assert hints._client is redis
        assert manager._gate is shared.gate

    monkeypatch.setattr(entrypoint, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(entrypoint, "run_event_worker", run)
    monkeypatch.setattr(entrypoint.SubscriptionPlacementService, "create", create_placement)
    monkeypatch.setattr(entrypoint, "EventWorkerRedisClient", lambda: redis)
    await entrypoint._run_connected(service, SecretEncryptor(b"a" * 32), resources, shutdown)
    assert captured == [True]
    sessions.assert_not_called()
    create_placement.assert_awaited_once_with(sessions)
    redis.disconnect.assert_awaited_once()


async def test_disabled_process_opens_no_temporal_client(monkeypatch):
    connect = AsyncMock()
    dispose = AsyncMock()
    monkeypatch.setattr(entrypoint, "get_settings", lambda: SimpleNamespace(eventstream_enabled=False))
    monkeypatch.setattr(entrypoint, "create_temporal_execution_service", connect)
    monkeypatch.setattr(entrypoint, "engine", SimpleNamespace(dispose=dispose))
    monkeypatch.setattr(entrypoint, "start_loggers", MagicMock())
    monkeypatch.setattr(entrypoint, "stop_loggers", MagicMock())
    await entrypoint.main()
    connect.assert_not_awaited()
    dispose.assert_awaited_once()


async def test_shutdown_cancels_pending_shared_client_connection(monkeypatch):
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def connect() -> None:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(entrypoint, "create_temporal_execution_service", connect)
    shutdown = asyncio.Event()
    task = asyncio.create_task(entrypoint._connect_temporal(shutdown))
    await entered.wait()
    shutdown.set()
    assert await task is None
    assert cancelled.is_set()


async def test_main_uses_existing_signed_tls_client_and_disposes_database_after_drain(monkeypatch):
    settings = get_settings().model_copy(update={"eventstream_enabled": True})
    monkeypatch.setattr(entrypoint, "get_settings", lambda: settings)
    monkeypatch.setattr(entrypoint, "validate_encryption_key_at_startup", MagicMock())
    monkeypatch.setattr(entrypoint, "start_loggers", MagicMock())
    stop_logs = MagicMock()
    monkeypatch.setattr(entrypoint, "stop_loggers", stop_logs)
    client = MagicMock()
    connect = AsyncMock(return_value=client)
    tls = object()
    monkeypatch.setattr(temporal_module.Client, "connect", connect)
    monkeypatch.setattr(temporal_module, "build_temporal_tls_config", lambda: tls)
    trace = []

    async def run(service, _encryptor, _resources, _shutdown) -> None:
        assert service.temporal_client is client
        trace.append("drained")

    async def dispose() -> None:
        trace.append("database_closed")

    monkeypatch.setattr(entrypoint, "_run_connected", run)
    monkeypatch.setattr(entrypoint, "engine", SimpleNamespace(dispose=AsyncMock(side_effect=dispose)))
    await entrypoint.main()
    connect.assert_awaited_once()
    assert connect.call_args.kwargs["tls"] is tls
    assert len(connect.call_args.kwargs["interceptors"]) == 1
    assert type(connect.call_args.kwargs["interceptors"][0]).__name__ == "WorkflowAuthClientInterceptor"
    assert trace == ["drained", "database_closed"]
    stop_logs.assert_called_once()


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
async def test_signal_stops_starts_and_claims_while_recovery_is_independent(monkeypatch, sig):
    snapshot = connection_context().snapshot
    reader = AsyncMock(spec=EventSubscriptionReader)
    reader.read.return_value = [snapshot]
    reader.recovery_holds.return_value = set()
    release = asyncio.Event()
    runner = IsolatedSubscriptionRunner(snapshot, [])
    runner.start_release = release
    resources = EventWorkerResources()
    placement = IsolatedPlacementService(IsolatedPlacementPool(snapshot.deployment_id, [snapshot.subscription_id]))
    manager = EventWorkerManager(reader, AsyncMock(return_value=runner), placement, resources)
    sessions = TrackingSessionFactory()
    store = MagicMock()
    store.claim_due = AsyncMock(return_value=[])
    monkeypatch.setattr("syntara.eventstreams.services.recovery_worker.EventDeliveryStore", lambda _session: store)
    recovery = EventDeliveryRecoveryWorker(sessions, MagicMock(), interval_seconds=0.01, resources=resources)
    hints = SimpleNamespace(start=MagicMock(), stop=AsyncMock())
    handlers = {}
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        loop, "add_signal_handler", lambda signal_number, callback: handlers.update({signal_number: callback})
    )
    remove = MagicMock()
    monkeypatch.setattr(loop, "remove_signal_handler", remove)
    task = asyncio.create_task(lifecycle.run_event_worker(manager, recovery, resources, hints))
    try:
        await runner.start_entered.wait()
        await eventually(lambda: store.claim_due.await_count > 0)
        assert manager.ready
        assert not runner.started
        handlers[sig]()
        assert recovery.draining
        assert not resources.accepting
        assert not manager.ready
        claims = store.claim_due.await_count
        manager.request_reconcile()
        async with asyncio.timeout(2):
            await task
        assert store.claim_due.await_count == claims
        assert runner.stopped
        hints.stop.assert_awaited_once()
        assert remove.call_count == 2
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_recovery_scans_with_zero_active_consumers(monkeypatch):
    reader = AsyncMock(spec=EventSubscriptionReader)
    reader.read.return_value = []
    reader.recovery_holds.return_value = set()
    factory = AsyncMock()
    resources = EventWorkerResources()
    placement = IsolatedPlacementService(IsolatedPlacementPool(connection_context().snapshot.deployment_id))
    manager = EventWorkerManager(reader, factory, placement, resources)
    store = MagicMock()
    store.claim_due = AsyncMock(return_value=[])
    monkeypatch.setattr("syntara.eventstreams.services.recovery_worker.EventDeliveryStore", lambda _session: store)
    recovery = EventDeliveryRecoveryWorker(TrackingSessionFactory(), MagicMock(), interval_seconds=0.01)
    redis = MagicMock()
    redis.pubsub_subscribe = AsyncMock(side_effect=OSError("Redis unavailable"))
    redis.disconnect = AsyncMock()
    hints = SubscriptionHintListener(manager.request_reconcile, redis)
    shutdown = asyncio.Event()
    task = asyncio.create_task(lifecycle.run_event_worker(manager, recovery, resources, hints, shutdown_event=shutdown))
    try:
        await eventually(
            lambda: manager.ready and store.claim_due.await_count > 0 and redis.pubsub_subscribe.await_count > 0
        )
        assert not manager.subscription_ids
        factory.assert_not_awaited()
    finally:
        shutdown.set()
        await task
    assert recovery.draining
    assert not resources.accepting
    redis.disconnect.assert_not_awaited()  # Only the entrypoint owns the shared pool.


async def test_membership_failure_is_monitored_and_closes_process_admission(manager_context, monkeypatch):
    context = manager_context
    context.manager._membership._settings = context.manager._membership._settings.model_copy(
        update={"event_worker_liveness_seconds": 0.02, "event_worker_heartbeat_interval_seconds": 10}
    )
    store = MagicMock()
    store.claim_due = AsyncMock(return_value=[])
    monkeypatch.setattr("syntara.eventstreams.services.recovery_worker.EventDeliveryStore", lambda _session: store)
    recovery = EventDeliveryRecoveryWorker(TrackingSessionFactory(), MagicMock(), resources=context.resources)
    hints = SimpleNamespace(start=MagicMock(), stop=AsyncMock())
    async with asyncio.timeout(2):
        with pytest.raises(RuntimeError, match="membership deadline"):
            await lifecycle.run_event_worker(context.manager, recovery, context.resources, hints)
    assert not context.resources.accepting
    assert not context.manager.ready
    assert context.manager.membership_task.done()
    hints.stop.assert_awaited_once()


async def test_lifecycle_deadline_settles_drain_children_before_hints_close(manager_context, monkeypatch):
    context = manager_context
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    key = context.snapshot.subscription_id
    supervisor = context.manager._supervisors[key]
    stop = supervisor.stop
    entered, cancelled = asyncio.Event(), asyncio.Event()
    trace = []

    async def blocked_stop() -> None:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            assert not context.manager.membership_task.done()
            trace.append("drain_cancelled")
            cancelled.set()

    async def close_hints() -> None:
        assert not context.manager._drain_tasks
        assert context.manager.membership_task.done()
        assert ("release", key) not in context.pool.trace
        trace.append("hints_closed")

    monkeypatch.setattr(supervisor, "stop", blocked_stop)
    settings = get_settings().model_copy(update={"event_drain_timeout_seconds": 0.02})
    monkeypatch.setattr(lifecycle, "get_settings", lambda: settings)
    monkeypatch.setattr(EventWorkerDefaults, "HINT_TIMEOUT_SECONDS", 0.02)
    recovery = SimpleNamespace(start=MagicMock(), close_claims=MagicMock(), stop=AsyncMock())
    hints = SimpleNamespace(start=MagicMock(), stop=AsyncMock(side_effect=close_hints))
    shutdown = asyncio.Event()
    process = asyncio.create_task(
        lifecycle.run_event_worker(context.manager, recovery, context.resources, hints, shutdown_event=shutdown)
    )
    try:
        await eventually(lambda: hints.start.called)
        shutdown.set()
        await entered.wait()
        await cancelled.wait()
        await process
        assert trace == ["drain_cancelled", "hints_closed"]
        assert context.pool.leases[key].owner == context.placement.worker
        recovery.close_claims.assert_called()
        assert not context.resources.accepting
    finally:
        shutdown.set()
        await process
        await stop()
