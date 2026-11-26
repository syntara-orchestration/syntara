"""Standalone control-plane worker: python -m syntara.eventstreams.consumer_entrypoint."""

import argparse
import asyncio
import signal

import structlog
from temporalio.service import RetryConfig

from syntara.audit.outbox.worker import AuditOutboxWorker, get_outbox_worker
from syntara.audit.registration import discover_and_register_all_handlers
from syntara.core.config.base import get_encryption_key, get_settings, validate_encryption_key_at_startup
from syntara.core.constants import EventWorkerDefaults
from syntara.core.database.session import AsyncSessionLocal, engine
from syntara.core.lib.encryption import SecretEncryptor, key_from_string
from syntara.core.logging.lifecycle import start_loggers, stop_loggers
from syntara.eventstreams.adapters.runner_factory import ManagedRunnerFactory
from syntara.eventstreams.consumer_health import EventWorkerHealth
from syntara.eventstreams.consumer_lifecycle import run_event_worker, settle_worker_tasks
from syntara.eventstreams.consumer_service import EventWorkerManager
from syntara.eventstreams.handlers.workflow_launcher import TemporalWorkflowLauncher
from syntara.eventstreams.services.admission_service import EventAdmissionService
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.eventstreams.services.placement_service import SubscriptionPlacementService
from syntara.eventstreams.services.subscription_hints import SubscriptionHintListener
from syntara.eventstreams.services.subscription_reader import EventSubscriptionReader
from syntara.eventstreams.services.worker_gate import EventWorkerGate
from syntara.eventstreams.services.worker_redis import EventWorkerRedisClient
from syntara.eventstreams.services.worker_resources import EventWorkerResources
from syntara.workflows.workflow_engine.services.temporal_execution_service import (
    TemporalExecutionService,
    create_temporal_execution_service,
)

logger = structlog.stdlib.get_logger(__name__)


async def _run_connected(
    temporal: TemporalExecutionService,
    encryptor: SecretEncryptor,
    resources: EventWorkerResources,
    shutdown: asyncio.Event,
    health: EventWorkerHealth,
) -> None:
    """Compose completed services without owning or sharing an AsyncSession."""
    async with asyncio.timeout(EventWorkerDefaults.PLACEMENT_TIMEOUT_SECONDS):
        placement = await SubscriptionPlacementService.create(AsyncSessionLocal)
    owner = str(placement.worker.worker_id)
    gate = EventWorkerGate(placement)
    resources.gate = gate
    redis = EventWorkerRedisClient()
    launcher = TemporalWorkflowLauncher(temporal)
    preparation = EventExecutionPreparationService(AsyncSessionLocal, resources=resources)
    admission = EventAdmissionService(AsyncSessionLocal, launcher, resources=resources)
    factory = ManagedRunnerFactory(
        AsyncSessionLocal, preparation, admission, resources, encryptor, owner_worker_id=owner
    )
    manager = EventWorkerManager(
        EventSubscriptionReader(AsyncSessionLocal, deployment_id=placement.worker.deployment_id),
        factory,
        placement,
        resources,
        connection_revision=factory.connection_revision,
    )
    hints = SubscriptionHintListener(manager.request_reconcile, redis)
    health.set_readiness(lambda: manager.ready)
    try:
        await run_event_worker(manager, resources, hints, shutdown_event=shutdown, on_shutdown=health.close_readiness)
    finally:
        health.close_readiness()
        try:
            async with asyncio.timeout(EventWorkerDefaults.HINT_TIMEOUT_SECONDS):
                await redis.disconnect()
        except Exception:  # noqa: BLE001 - optional Redis cleanup cannot skip Temporal/database cleanup
            logger.warning("event_worker_redis_close_incomplete")


async def _connect_temporal(shutdown: asyncio.Event) -> TemporalExecutionService | None:
    """Bound connection startup and release task-held client references on return."""
    # A rejection must describe the only start request. Application recovery
    # owns retries so a later rejection cannot hide an earlier acceptance.
    connecting = asyncio.create_task(create_temporal_execution_service(retry_config=RetryConfig(max_retries=1)))
    stopping = asyncio.create_task(shutdown.wait())
    try:
        async with asyncio.timeout(EventWorkerDefaults.STARTUP_TIMEOUT_SECONDS):
            done, _ = await asyncio.wait({connecting, stopping}, return_when=asyncio.FIRST_COMPLETED)
        return None if stopping in done else await connecting
    finally:
        for task in (connecting, stopping):
            if not task.done():
                task.cancel()
        await settle_worker_tasks({connecting, stopping}, EventWorkerDefaults.HINT_TIMEOUT_SECONDS)


async def _drain_audit_writes(audit_writer: AuditOutboxWorker | None) -> None:
    # This process only enqueues audit rows. The platform publisher owns shared
    # outbox SELECT/DELETE and OTLP delivery.
    if audit_writer is not None:
        try:
            await audit_writer.drain_writes(timeout_seconds=EventWorkerDefaults.HINT_TIMEOUT_SECONDS)
        except Exception:  # noqa: BLE001 - optional audit cleanup cannot skip database disposal
            logger.warning("event_worker_audit_close_incomplete")


def _validate_termination_grace(grace_seconds: int | None, drain_seconds: float) -> None:
    """Leave shutdown headroom when a deployment supplies its pod grace period."""
    cleanup_seconds = EventWorkerDefaults.SHUTDOWN_CLEANUP_ALLOWANCE_SECONDS
    if grace_seconds is not None and grace_seconds <= drain_seconds + cleanup_seconds:
        msg = (
            f"Termination grace ({grace_seconds}s) must exceed the event drain deadline "
            f"({drain_seconds:g}s) plus cleanup allowance ({cleanup_seconds}s)"
        )
        raise ValueError(msg)


def _arguments() -> argparse.Namespace:
    """Accept pod lifecycle bounds without exposing worker tuning controls."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--termination-grace-period-seconds", type=int)
    return parser.parse_args()


async def main(*, termination_grace_seconds: int | None = None) -> None:
    """Validate secrets, connect once, and release shared resources after bounded drain."""
    start_loggers()
    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    temporal: TemporalExecutionService | None = None
    audit_writer: AuditOutboxWorker | None = None
    health = EventWorkerHealth()
    try:
        settings = get_settings()
        if not settings.eventstream_enabled:
            logger.info("event_worker_disabled")
            return
        _validate_termination_grace(termination_grace_seconds, settings.event_drain_timeout_seconds)
        try:
            audit_writer = get_outbox_worker()
            discover_and_register_all_handlers()
        except Exception:
            logger.exception("event_worker_audit_start_unavailable")
        validate_encryption_key_at_startup()
        encryptor = SecretEncryptor(key_from_string(get_encryption_key().get_secret_value()))
        resources = EventWorkerResources()
        shutdown = asyncio.Event()

        def request_shutdown() -> None:
            health.close_readiness()
            resources.close_admission()
            shutdown.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, request_shutdown)
            installed.append(sig)
        await health.start()
        temporal = await _connect_temporal(shutdown)
        if temporal is not None and not shutdown.is_set():
            await _run_connected(temporal, encryptor, resources, shutdown, health)
    finally:
        health.close_readiness()
        # As in TemporalWorkerService.stop(), the SDK owns client cleanup.
        # Release the composition only after consumers have drained.
        temporal = None
        try:
            try:
                await _drain_audit_writes(audit_writer)
            finally:
                await engine.dispose()
        finally:
            try:
                await health.stop()
            finally:
                for sig in installed:
                    loop.remove_signal_handler(sig)
                stop_loggers()


if __name__ == "__main__":
    asyncio.run(main(termination_grace_seconds=_arguments().termination_grace_period_seconds))
