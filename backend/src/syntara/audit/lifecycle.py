"""Audit system lifecycle management.

Provides initialization and shutdown handlers for the audit outbox worker subsystem,
plus orchestration helpers that coordinate logging and audit subsystems together.

Low-level functions (for fine-grained control):
    - start_audit_outbox_worker() / stop_audit_outbox_worker()

High-level orchestration (combines logging + audit):
    - start_audit_subsystems() / stop_audit_subsystems()
    - Use these from API server, CLI tools, or any process that emits audit events

Initialization (`start_audit_subsystems`):
    - Starts logging subsystems (stdout + OTLP handlers)
    - Starts asynchronous outbox worker with retry and batching support

Shutdown (`stop_audit_subsystems`):
    - Drains in-flight audit events from the async worker queue
    - Stops the outbox worker
    - Flushes and stops logging subsystems

Call during application startup (lifespan context or CLI entry point)
and shutdown, after all request handlers complete but before database connections close.
"""

import threading
from enum import StrEnum

import structlog

from syntara.audit.outbox.worker import get_outbox_worker

logger = structlog.stdlib.get_logger(__name__)


class AuditLifecycleState(StrEnum):
    """Audit system lifecycle states."""

    STOPPED = "stopped"
    RUNNING = "running"


# Thread lock to ensure thread-safe state transitions
_state_lock = threading.Lock()
_state = AuditLifecycleState.STOPPED


def start_audit_outbox_worker() -> None:
    """Initialize and start audit outbox worker.

    Thread-safe and idempotent - safe to call multiple times.
    Can be called after stop to restart the audit system.
    """
    global _state  # noqa: PLW0603

    with _state_lock:
        if _state == AuditLifecycleState.RUNNING:
            logger.debug("audit.components.already_running", state=_state)
            return

        # Start audit outbox worker (publishes events from main DB to audit DB)
        outbox_worker = get_outbox_worker()
        outbox_worker.start()
        logger.info("AuditOutboxWorker started")

        _state = AuditLifecycleState.RUNNING


async def stop_audit_outbox_worker() -> None:
    """Flush and stop audit outbox worker during shutdown.

    Ensures in-flight audit outbox events are drained and the worker is stopped.

    Thread-safe and idempotent - safe to call multiple times.
    Must be called last during shutdown to avoid dropping events.
    """
    global _state  # noqa: PLW0603

    with _state_lock:
        if _state == AuditLifecycleState.STOPPED:
            logger.debug("audit.components.already_stopped", state=_state)
            return

        # Wait for in-flight audit writes to complete
        outbox_worker = get_outbox_worker()
        if outbox_worker is not None:
            await outbox_worker.drain()
            await outbox_worker.stop()
            logger.info("AuditOutboxWorker shutdown.")

        _state = AuditLifecycleState.STOPPED


# =============================================================================
# High-level orchestration (combines logging + audit)
# =============================================================================


def start_audit_subsystems() -> None:
    """Start all subsystems needed for audit event emission.

    Combines logging and audit worker initialization in the correct order:
    1. Logging (must start first to capture all subsequent events)
    2. Audit outbox worker (depends on logging)

    Use this from API server, CLI tools, or any process that emits audit events.

    Thread-safe and idempotent - safe to call multiple times.
    """
    from syntara.core.logging.lifecycle import start_loggers  # noqa: PLC0415

    start_loggers()
    start_audit_outbox_worker()


async def stop_audit_subsystems() -> None:
    """Stop all audit subsystems in reverse order.

    Order:
    1. Audit outbox worker (flush pending events before logging stops)
    2. Logging (stop last to capture all shutdown events)

    Thread-safe and idempotent - safe to call multiple times.
    """
    from syntara.core.logging.lifecycle import stop_loggers  # noqa: PLC0415

    await stop_audit_outbox_worker()
    stop_loggers()
