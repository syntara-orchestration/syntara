"""Signals and bounded lifecycle for the standalone control-plane worker."""

import asyncio
import signal
from typing import Any

import structlog

from syntara.core.config.base import get_settings
from syntara.core.constants import EventWorkerDefaults
from syntara.eventstreams.consumer_service import EventWorkerManager
from syntara.eventstreams.services.recovery_worker import EventDeliveryRecoveryWorker
from syntara.eventstreams.services.subscription_hints import SubscriptionHintListener
from syntara.eventstreams.services.worker_resources import EventWorkerResources

logger = structlog.stdlib.get_logger(__name__)


async def settle_worker_tasks(tasks: set[asyncio.Task[Any]], drain_seconds: float) -> None:
    """Wait within a shared deadline, cancel local tasks, and consume their results."""
    if not tasks:
        return
    _, pending = await asyncio.wait(tasks, timeout=drain_seconds)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.wait(pending, timeout=EventWorkerDefaults.HINT_TIMEOUT_SECONDS)
    for task in tasks:
        if task.done():
            _consume_result(task)
        else:
            task.add_done_callback(_consume_result)
    if pending:
        logger.warning("event_worker_shutdown_deadline_reached", task_count=len(pending))


def _consume_result(task: asyncio.Task[Any]) -> None:
    if not task.cancelled():
        task.exception()


async def _monitor(
    manager: EventWorkerManager,
    shutdown: asyncio.Event,
    startup: asyncio.Task[None],
    stopping: asyncio.Task[bool],
) -> None:
    done, _ = await asyncio.wait({startup, stopping}, return_when=asyncio.FIRST_COMPLETED)
    if startup in done:
        await startup
    if shutdown.is_set():
        return
    reconciliation = manager.reconciliation_task
    membership = manager.membership_task
    if reconciliation is None or membership is None:
        msg = "Event worker infrastructure did not start"
        raise RuntimeError(msg)
    infrastructure = {reconciliation, membership}
    done, _ = await asyncio.wait({*infrastructure, stopping}, return_when=asyncio.FIRST_COMPLETED)
    if not shutdown.is_set():
        for task in done & infrastructure:
            await task
        msg = "Event worker infrastructure exited unexpectedly"
        raise RuntimeError(msg)


async def _drain_worker(
    manager: EventWorkerManager,
    recovery: EventDeliveryRecoveryWorker,
    resources: EventWorkerResources,
    lifecycle_tasks: tuple[asyncio.Task[None] | None, asyncio.Task[bool] | None],
) -> None:
    """Share one deadline and finish manager cleanup before stopping maintenance."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + get_settings().event_drain_timeout_seconds
    try:
        async with asyncio.timeout_at(min(deadline, loop.time() + EventWorkerDefaults.PLACEMENT_TIMEOUT_SECONDS)):
            await manager.begin_shutdown()
    except Exception:  # noqa: BLE001 - failed membership marking must not skip bounded cleanup
        resources.database_failed()
        logger.warning("event_worker_draining_membership_unavailable")
    tasks: set[asyncio.Task[Any]] = {asyncio.create_task(recovery.stop())}
    for task in lifecycle_tasks:
        if task is not None:
            if not task.done():
                task.cancel()
            tasks.add(task)
    try:
        await manager.stop(deadline=deadline)
    finally:
        try:
            await settle_worker_tasks(tasks, max(0.0, deadline - loop.time()))
        finally:
            await manager.stop_membership()


async def run_event_worker(
    manager: EventWorkerManager,
    recovery: EventDeliveryRecoveryWorker,
    resources: EventWorkerResources,
    hints: SubscriptionHintListener,
    *,
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """Run independent reconciliation/recovery and delegate transport-owned drain.

    The optional event supports embedding and isolated tests. Readiness is exposed
    by manager.ready; no operational HTTP routes or packaging are installed here.
    """
    shutdown = shutdown_event if shutdown_event is not None else asyncio.Event()
    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    startup: asyncio.Task[None] | None = None
    stopping: asyncio.Task[bool] | None = None

    def close_admission() -> None:
        manager.close_reconciliation()
        recovery.close_claims()
        resources.close_admission()

    def request_shutdown() -> None:
        close_admission()
        shutdown.set()

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, request_shutdown)
            installed.append(sig)
        if shutdown.is_set():
            return
        recovery.start()
        hints.start()
        startup = asyncio.create_task(manager.start(), name="event-worker-startup")
        stopping = asyncio.create_task(shutdown.wait(), name="event-worker-shutdown")
        await _monitor(manager, shutdown, startup, stopping)
    finally:
        close_admission()
        try:
            await _drain_worker(manager, recovery, resources, (startup, stopping))
        finally:
            try:
                await hints.stop()
            finally:
                for sig in installed:
                    loop.remove_signal_handler(sig)
