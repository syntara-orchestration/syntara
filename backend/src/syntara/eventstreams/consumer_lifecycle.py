"""Shared lifecycle for the event-stream consumer process.

Mirrors :func:`syntara.workflows.worker_lifecycle.run_worker`: install SIGINT/
SIGTERM handlers for a graceful drain, expose Prometheus metrics on the shared
worker port, run the consumer until a shutdown is requested, then stop it cleanly.

The difference from the Temporal worker is that a consumer's ``run()`` blocks on
its receive loop, so it runs as a task while we await the shutdown event.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from collections.abc import Callable, Coroutine
from typing import Any

import prometheus_client
import structlog

from syntara.core.config.base import get_settings
from syntara.eventstreams.consumer_service import EventStreamConsumerService

logger = structlog.stdlib.get_logger(__name__)

StartFn = Callable[[], Coroutine[Any, Any, EventStreamConsumerService]]


async def run_consumer(start_fn: StartFn, *, worker_name: str) -> None:
    """Bootstrap an event-stream consumer with graceful shutdown.

    Args:
        start_fn: Async callable that builds and returns a started/ready
            :class:`EventStreamConsumerService` (typically ``start_consumer``).
        worker_name: Human-readable label used in log messages.

    """
    service: EventStreamConsumerService | None = None
    run_task: asyncio.Task[None] | None = None

    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler(sig: int) -> None:
        logger.info("Received signal, initiating graceful shutdown...", signal=sig, worker=worker_name)
        shutdown_event.set()

    loop.add_signal_handler(signal.SIGINT, lambda: _signal_handler(signal.SIGINT))
    loop.add_signal_handler(signal.SIGTERM, lambda: _signal_handler(signal.SIGTERM))

    # Expose Prometheus metrics on the shared worker port. A bind failure (port in
    # use) is logged and ignored — it must never prevent the consumer from starting.
    _metrics_port = get_settings().metrics_worker_port
    try:
        prometheus_client.start_http_server(_metrics_port)
        logger.info("Consumer metrics server started", port=_metrics_port, worker=worker_name)
    except OSError as exc:
        logger.warning(
            "Consumer metrics server could not bind — skipping",
            port=_metrics_port,
            worker=worker_name,
            error=str(exc),
        )

    try:
        logger.info("Starting event-stream consumer", worker=worker_name)
        service = await start_fn()
        run_task = asyncio.create_task(service.run(), name=f"{worker_name}-run")

        # Wake on either an external shutdown signal or the run loop exiting on its own.
        stop_wait = asyncio.create_task(shutdown_event.wait(), name=f"{worker_name}-wait")
        await asyncio.wait({run_task, stop_wait}, return_when=asyncio.FIRST_COMPLETED)
        stop_wait.cancel()

        # Surface a crash in the run loop rather than swallowing it: result()
        # re-raises the task's original exception (if any) with its traceback.
        if run_task.done():
            run_task.result()

    except Exception:
        logger.exception("Event-stream consumer failed", worker=worker_name)
        sys.exit(1)

    finally:
        if service is not None:
            logger.info("Stopping event-stream consumer", worker=worker_name)
            await service.stop()
        if run_task is not None:
            try:
                await run_task
            except Exception:
                logger.exception("Event-stream consumer stopped with error", worker=worker_name)
        logger.info("Event-stream consumer stopped", worker=worker_name)
