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
from syntara.authz.evaluator import RegoEvaluator
from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.logging.logging import apply_runtime_log_level
from syntara.settings.cache.settings_cache import SettingsCache, get_runtime_settings, set_runtime_settings
from syntara.workflows.node_launch_checks import set_node_authz_evaluator
from syntara.workflows.workflow_engine.services.temporal_worker import (
    TemporalWorkerService,
    stop_worker,
)

logger = structlog.stdlib.get_logger(__name__)

StartFn = Callable[[], Coroutine[Any, Any, TemporalWorkerService]]


async def _start_authz_evaluator(worker_name: str) -> RegoEvaluator | None:
    """Start the Rego evaluator this process uses for node-kind checks.

    Worker activities evaluate ``workflow_node:execute`` (scheduled launches and
    the resume re-check) but have no request to read the API's evaluator from.
    The evaluator loads a native Rego runtime, so it is created once here at
    process startup — never inside workflow code, where the Temporal sandbox
    blocks the lazy imports and environment access it needs.

    Returns the started evaluator, or ``None`` when startup failed: a worker must
    still come up, and a missing evaluator is logged loudly and fails open rather
    than denying every node.
    """
    evaluator = RegoEvaluator()
    try:
        evaluator.start()
        if not await evaluator.health():
            msg = "Authorization evaluator failed startup healthcheck"
            raise RuntimeError(msg)  # noqa: TRY301
    except Exception:
        logger.exception(
            "Authorization evaluator unavailable — node-kind execute checks will be skipped",
            worker=worker_name,
        )
        return None
    set_node_authz_evaluator(evaluator)
    logger.info("Authorization evaluator ready", worker=worker_name)
    return evaluator


async def run_worker(start_fn: StartFn, *, worker_name: str) -> None:
    """Bootstrap a Temporal worker with graceful shutdown and shared lifecycle.

    Args:
        start_fn: Async callable that calls ``start_worker()`` with the
            appropriate parameters and returns the started service.
        worker_name: Human-readable label used in log messages.

    """
    worker_service: TemporalWorkerService | None = None
    authz_evaluator: RegoEvaluator | None = None

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

    get_runtime_settings().start_watching()
    discover_and_register_all_handlers()
    authz_evaluator = await _start_authz_evaluator(worker_name)

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

        if authz_evaluator is not None:
            set_node_authz_evaluator(None)
            await authz_evaluator.stop()

        if worker_service:
            logger.info("Stopping Temporal worker", worker=worker_name)
            await stop_worker()
            logger.info("Temporal worker stopped", worker=worker_name)
