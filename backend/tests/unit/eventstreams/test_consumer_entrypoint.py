"""Process composition, signals, and shared-client teardown."""

import asyncio
import signal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from syntara.audit import lifecycle as audit_module
from syntara.audit.outbox.worker import AuditOutboxWorker
from syntara.core.config.base import get_settings
from syntara.core.constants import EventWorkerDefaults
from syntara.core.lib.encryption import SecretEncryptor
from syntara.eventstreams import consumer_entrypoint as entrypoint
from syntara.eventstreams import consumer_lifecycle as lifecycle
from syntara.eventstreams.consumer_service import EventWorkerManager
from syntara.eventstreams.services.subscription_reader import EventSubscriptionReader
from syntara.eventstreams.services.worker_resources import EventWorkerResources
from syntara.workflows.workflow_engine.services import temporal_execution_service as temporal_module
from tests.helpers.eventstream_runtime import IsolatedSubscriptionRunner
from tests.helpers.eventstream_worker import IsolatedPlacementPool, IsolatedPlacementService
from tests.unit.eventstreams import test_consumer_service as consumer_tests
from tests.unit.eventstreams.test_connection_provider import connection_context
from tests.unit.eventstreams.test_consumer_service import eventually

manager_context = consumer_tests.manager_context


@pytest.fixture(autouse=True)
def audit_lifecycle(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Isolate process-owned audit startup and draining from external services."""
    audit = SimpleNamespace(register=MagicMock(), start=MagicMock(), stop=AsyncMock())
    monkeypatch.setattr(entrypoint, "discover_and_register_all_handlers", audit.register)
    monkeypatch.setattr(entrypoint, "start_audit_outbox_worker", audit.start)
    monkeypatch.setattr(entrypoint, "stop_audit_outbox_worker", audit.stop)
    return audit


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

    async def run(manager, shared, hints, **kwargs: object) -> None:
        captured.append(True)
        assert shared is resources
        assert kwargs["shutdown_event"] is shutdown
        assert manager._reader._session_factory is sessions
        assert manager._factory._session_factory is sessions
        assert manager._factory._resources is shared
        assert manager._factory._admission._launcher._client is client
        assert manager._factory._preparation._resources is shared
        assert manager._connection_revision == manager._factory.connection_revision
        assert hints._request == manager.request_reconcile
        assert hints._client is redis
        assert manager._placement is placement
        assert manager._factory._owner == str(placement.worker.worker_id)
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


async def test_main_uses_existing_signed_tls_client_and_disposes_database_after_drain(monkeypatch, audit_lifecycle):
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

    async def stop_audit(*, timeout_seconds: float) -> None:
        assert timeout_seconds == EventWorkerDefaults.HINT_TIMEOUT_SECONDS
        trace.append("audit_closed")

    audit_lifecycle.stop.side_effect = stop_audit
    monkeypatch.setattr(entrypoint, "_run_connected", run)
    monkeypatch.setattr(entrypoint, "engine", SimpleNamespace(dispose=AsyncMock(side_effect=dispose)))
    await entrypoint.main()
    connect.assert_awaited_once()
    assert connect.call_args.kwargs["tls"] is tls
    assert len(connect.call_args.kwargs["interceptors"]) == 1
    assert type(connect.call_args.kwargs["interceptors"][0]).__name__ == "WorkflowAuthClientInterceptor"
    assert trace == ["drained", "audit_closed", "database_closed"]
    audit_lifecycle.register.assert_called_once()
    audit_lifecycle.start.assert_called_once()
    audit_lifecycle.stop.assert_awaited_once_with(timeout_seconds=EventWorkerDefaults.HINT_TIMEOUT_SECONDS)
    stop_logs.assert_called_once()


async def test_audit_start_failure_does_not_prevent_consumption(monkeypatch, audit_lifecycle):
    settings = get_settings().model_copy(update={"eventstream_enabled": True})
    monkeypatch.setattr(entrypoint, "get_settings", lambda: settings)
    monkeypatch.setattr(entrypoint, "validate_encryption_key_at_startup", MagicMock())
    monkeypatch.setattr(entrypoint, "start_loggers", MagicMock())
    monkeypatch.setattr(entrypoint, "stop_loggers", MagicMock())
    monkeypatch.setattr(entrypoint, "_connect_temporal", AsyncMock(return_value=MagicMock()))
    run = AsyncMock()
    monkeypatch.setattr(entrypoint, "_run_connected", run)
    dispose = AsyncMock()
    monkeypatch.setattr(entrypoint, "engine", SimpleNamespace(dispose=dispose))
    audit_lifecycle.start.side_effect = RuntimeError("audit unavailable")

    await entrypoint.main()

    run.assert_awaited_once()
    audit_lifecycle.stop.assert_awaited_once()
    dispose.assert_awaited_once()


@pytest.mark.parametrize("audit_failure", ["stalled_drain", "shutdown_error"])
async def test_audit_shutdown_cannot_prevent_database_and_logger_cleanup(monkeypatch, audit_failure):
    settings = get_settings().model_copy(update={"eventstream_enabled": True})
    monkeypatch.setattr(entrypoint, "get_settings", lambda: settings)
    monkeypatch.setattr(entrypoint, "validate_encryption_key_at_startup", MagicMock())
    monkeypatch.setattr(entrypoint, "start_loggers", MagicMock())
    stop_logs = MagicMock()
    monkeypatch.setattr(entrypoint, "stop_loggers", stop_logs)
    monkeypatch.setattr(entrypoint, "_connect_temporal", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr(entrypoint, "_run_connected", AsyncMock())
    dispose = AsyncMock()
    monkeypatch.setattr(entrypoint, "engine", SimpleNamespace(dispose=dispose))
    monkeypatch.setattr(EventWorkerDefaults, "HINT_TIMEOUT_SECONDS", 0.02)
    cancelled = asyncio.Event()

    async def stalled_drain() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    worker = AuditOutboxWorker(name="consumer-audit-shutdown", interval_seconds=1, coordinate=False)
    stop = AsyncMock()
    monkeypatch.setattr(worker, "drain", stalled_drain)
    monkeypatch.setattr(worker, "stop", stop)
    monkeypatch.setattr(audit_module, "get_outbox_worker", lambda: worker)
    monkeypatch.setattr(audit_module, "_state", audit_module.AuditLifecycleState.RUNNING)
    monkeypatch.setattr(entrypoint, "stop_audit_outbox_worker", audit_module.stop_audit_outbox_worker)
    if audit_failure == "shutdown_error":
        monkeypatch.setattr(worker, "shutdown", AsyncMock(side_effect=OSError("audit unavailable")))

    async with asyncio.timeout(1):
        await entrypoint.main()

    dispose.assert_awaited_once()
    stop_logs.assert_called_once()
    assert audit_module._state == audit_module.AuditLifecycleState.STOPPED
    if audit_failure == "stalled_drain":
        assert cancelled.is_set()
        stop.assert_awaited_once()


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
async def test_signal_stops_new_placements_and_drains_consumers(monkeypatch, sig):
    snapshot = connection_context().snapshot
    reader = AsyncMock(spec=EventSubscriptionReader)
    reader.read.return_value = [snapshot]
    release = asyncio.Event()
    runner = IsolatedSubscriptionRunner(snapshot, [])
    runner.start_release = release
    resources = EventWorkerResources()
    placement = IsolatedPlacementService(IsolatedPlacementPool(snapshot.deployment_id, [snapshot.subscription_id]))
    manager = EventWorkerManager(reader, AsyncMock(return_value=runner), placement, resources)
    hints = SimpleNamespace(start=MagicMock(), stop=AsyncMock())
    handlers = {}
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        loop, "add_signal_handler", lambda signal_number, callback: handlers.update({signal_number: callback})
    )
    remove = MagicMock()
    monkeypatch.setattr(loop, "remove_signal_handler", remove)
    task = asyncio.create_task(lifecycle.run_event_worker(manager, resources, hints))
    try:
        await runner.start_entered.wait()
        assert manager.ready
        assert not runner.started
        handlers[sig]()
        assert not resources.accepting
        assert not manager.ready
        manager.request_reconcile()
        async with asyncio.timeout(2):
            await task
        assert runner.stopped
        hints.stop.assert_awaited_once()
        assert remove.call_count == 2
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_membership_failure_is_monitored_and_closes_process_admission(manager_context, monkeypatch):
    context = manager_context
    context.manager._membership._settings = context.manager._membership._settings.model_copy(
        update={"event_worker_liveness_seconds": 0.02, "event_worker_heartbeat_interval_seconds": 10}
    )
    hints = SimpleNamespace(start=MagicMock(), stop=AsyncMock())
    async with asyncio.timeout(2):
        with pytest.raises(RuntimeError, match="membership deadline"):
            await lifecycle.run_event_worker(context.manager, context.resources, hints)
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
    hints = SimpleNamespace(start=MagicMock(), stop=AsyncMock(side_effect=close_hints))
    shutdown = asyncio.Event()
    process = asyncio.create_task(
        lifecycle.run_event_worker(context.manager, context.resources, hints, shutdown_event=shutdown)
    )
    try:
        await eventually(lambda: hints.start.called)
        shutdown.set()
        await entered.wait()
        await cancelled.wait()
        await process
        assert trace == ["drain_cancelled", "hints_closed"]
        assert context.pool.leases[key].owner == context.placement.worker
        assert not context.resources.accepting
    finally:
        shutdown.set()
        await process
        await stop()
