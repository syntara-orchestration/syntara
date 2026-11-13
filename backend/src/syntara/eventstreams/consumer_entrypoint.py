"""Standalone control-plane worker: python -m syntara.eventstreams.consumer_entrypoint."""

import argparse
import asyncio
import signal

import structlog

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
        await run_event_worker(manager, resources, hints, shutdown_event=shutdown)
    finally:
        health.close_readiness()
        try:
            async with asyncio.timeout(EventWorkerDefaults.HINT_TIMEOUT_SECONDS):
                await redis.disconnect()
        except Exception:  # noqa: BLE001 - optional Redis cleanup cannot skip Temporal/database cleanup
            logger.warning("event_worker_redis_close_incomplete")


async def _connect_temporal(shutdown: asyncio.Event) -> TemporalExecutionService | None:
    """Bound connection startup and release task-held client references on return."""
    connecting = asyncio.create_task(create_temporal_execution_service())
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


def _validate_termination_grace(grace_seconds: int | None, drain_seconds: float) -> None:
    """Leave shutdown headroom when a deployment supplies its pod grace period."""
    if grace_seconds is not None and grace_seconds <= (
        drain_seconds + EventWorkerDefaults.SHUTDOWN_CLEANUP_ALLOWANCE_SECONDS
    ):
        msg = "Termination grace must exceed the event drain deadline and cleanup allowance"
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
    health = EventWorkerHealth()
    try:
        if not get_settings().eventstream_enabled:
            logger.info("event_worker_disabled")
            return
        _validate_termination_grace(termination_grace_seconds, get_settings().event_drain_timeout_seconds)
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
