"""Shared lifecycle management for Temporal worker processes.

Extracted so the main workflow worker (worker.py) and the background queue
worker (background_worker.py) share the same startup / shutdown / signal-handling
logic without copy-paste.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from collections.abc import Callable, Coroutine
from typing import Any

import prometheus_client
import structlog

from syntara.audit.registration import discover_and_register_all_handlers
from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.logging.logging import apply_runtime_log_level
from syntara.settings.cache.settings_cache import SettingsCache, get_runtime_settings, set_runtime_settings
from syntara.workflows.workflow_engine.services.temporal_worker import (
    TemporalWorkerService,
    stop_worker,
)

logger = structlog.stdlib.get_logger(__name__)

StartFn = Callable[[], Coroutine[Any, Any, TemporalWorkerService]]


async def run_worker(start_fn: StartFn, *, worker_name: str) -> None:
    """Bootstrap a Temporal worker with graceful shutdown and shared lifecycle.

    Args:
        start_fn: Async callable that calls ``start_worker()`` with the
            appropriate parameters and returns the started service.
        worker_name: Human-readable label used in log messages.

    """
    worker_service: TemporalWorkerService | None = None

    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler(sig: int) -> None:
        logger.info("Received signal, initiating graceful shutdown...", signal=sig, worker=worker_name)
        shutdown_event.set()

    loop.add_signal_handler(signal.SIGINT, lambda: _signal_handler(signal.SIGINT))
    loop.add_signal_handler(signal.SIGTERM, lambda: _signal_handler(signal.SIGTERM))

    set_runtime_settings(SettingsCache(session_factory=AsyncSessionLocal))
    await apply_runtime_log_level()

    # Expose a Prometheus HTTP endpoint so ServiceMonitors can scrape worker-side metrics.
    # Uses a daemon thread — does not block the event loop. Port conflicts (two workers on
    # the same host, or Prometheus already bound to the port) are logged and ignored —
    # a missing metrics endpoint must never prevent the worker from starting.
    _metrics_port = get_settings().metrics_worker_port
    try:
        prometheus_client.start_http_server(_metrics_port)
        logger.info("Worker metrics server started", port=_metrics_port, worker=worker_name)
    except OSError as exc:
        logger.warning(
            "Worker metrics server could not bind — skipping",
            port=_metrics_port,
            worker=worker_name,
            error=str(exc),
        )

    # Ensure @watch_setting("telemetry.segment_write_key") is registered before
    # start_watching() applies pending watchers.
    import syntara.telemetry.client  # noqa: F401, PLC0415

    get_runtime_settings().start_watching()
    discover_and_register_all_handlers()

    try:
        logger.info("Starting Temporal worker", worker=worker_name)
        worker_service = await start_fn()
        logger.info("Temporal worker started successfully", worker=worker_name)

        await shutdown_event.wait()

    except Exception:
        logger.exception("Failed to start Temporal worker", worker=worker_name)
        sys.exit(1)

    finally:
        await get_runtime_settings().stop_watching()

        if worker_service:
            logger.info("Stopping Temporal worker", worker=worker_name)
            await stop_worker()
            logger.info("Temporal worker stopped", worker=worker_name)
