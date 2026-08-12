"""Reusable periodic background worker with cross-instance coordination.

Provides asyncio lifecycle management (start/stop/cancel/error-resilience) and
optional database-backed coordination via PostgreSQL advisory locks so that only
one application process executes the work callback per cycle.

Usage::

    worker = PeriodicWorker(
        name="telemetry-collector",
        interval_seconds=300,
        session_factory=AsyncSessionLocal,
        callback=collect_and_send,
        cleanup_callback=flush_segment,
    )
    worker.start()
    # ... app runs ...
    await worker.stop()
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)


async def _try_advisory_xact_lock(session: AsyncSession, lock_key: int) -> bool:
    """Attempt to acquire a PostgreSQL transaction-level advisory lock.

    Transaction-level locks auto-release when the transaction ends (COMMIT or
    ROLLBACK), which happens when the session context manager exits.  This
    avoids the leak risk of session-level locks in a connection-pooled setup
    where ``session.close()`` returns the connection to the pool without
    closing it.

    Args:
        session: Active async database session.
        lock_key: 64-bit integer identifying the lock.

    Returns:
        True if the lock was acquired, False otherwise.

    """
    conn = await session.connection()
    result = await conn.execute(
        text("SELECT pg_try_advisory_xact_lock(:key)"),
        {"key": lock_key},
    )
    return bool(result.scalar())


def derive_lock_key(name: str) -> int:
    """Derive a deterministic 64-bit integer lock key from a worker name.

    Args:
        name: Human-readable worker name.

    Returns:
        64-bit integer suitable for PostgreSQL advisory lock functions.

    """
    digest = hashlib.sha256(name.encode()).digest()
    # Use first 8 bytes as a signed 64-bit int (PostgreSQL bigint is signed)
    return int.from_bytes(digest[:8], "big", signed=True)


class PeriodicWorker:
    """Periodic background worker with optional cross-instance coordination.

    Manages a single asyncio background task that repeatedly sleeps for a
    configured interval and then invokes a user-provided async callback.
    When coordination is enabled (the default), a PostgreSQL advisory lock
    ensures that at most one worker instance across all application processes
    executes the callback per cycle.

    Args:
        name: Human-readable worker identifier used for logging and as the
            seed for the advisory lock key.
        interval_seconds: Seconds to sleep between the end of one callback
            and the start of the next.
        session_factory: Injectable async session maker for database access.
            Required when ``coordinate=True`` (the default).  May be omitted
            (``None``) for uncoordinated workers that do not need database
            access.
        callback: Async work function called each cycle. Receives the
            session_factory (which may be ``None``) so it can open its own
            database sessions when needed.
        cleanup_callback: Optional async function called during stop() for
            resource cleanup (e.g., flushing buffers).
        coordinate: Whether to acquire an advisory lock before running the
            callback. Set to False for tasks that must run in every worker
            (e.g., per-process connection cleanup). Defaults to True.

    Raises:
        ValueError: If ``coordinate=True`` and ``session_factory`` is None.

    """

    def __init__(
        self,
        *,
        name: str,
        interval_seconds: float,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        callback: Callable[[Any], Awaitable[None]],
        cleanup_callback: Callable[[], Awaitable[None]] | None = None,
        coordinate: bool = True,
    ) -> None:
        """Initialize the periodic worker with the given configuration."""
        if coordinate and session_factory is None:
            msg = f"PeriodicWorker {name!r}: session_factory is required when coordinate=True"
            raise ValueError(msg)
        self._name = name
        self._interval_seconds = interval_seconds
        self._session_factory = session_factory
        self._callback = callback
        self._cleanup_callback = cleanup_callback
        self._coordinate = coordinate
        self._task: asyncio.Task[None] | None = None
        self._lock_key = derive_lock_key(name)

    def start(self) -> None:
        """Start the background periodic task.

        Idempotent — calling start() multiple times has no effect if the
        task is already running.
        """
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "periodic_worker_started",
            worker_name=self._name,
            interval_seconds=self._interval_seconds,
            coordinate=self._coordinate,
        )

    async def stop(self) -> None:
        """Stop the background task and run optional cleanup.

        Cancels the background task, awaits its completion, then calls the
        cleanup callback if one was provided. Cleanup errors are logged but
        do not prevent shutdown.
        """
        if self._task is None or self._task.done():
            self._task = None
            return

        self._task.cancel()
        with contextlib.suppress(BaseException):
            await self._task
        self._task = None

        if self._cleanup_callback is not None:
            try:
                await self._cleanup_callback()
            except Exception:  # noqa: BLE001
                logger.warning(
                    "periodic_worker_cleanup_error",
                    worker_name=self._name,
                    exc_info=True,
                )

        logger.info("periodic_worker_stopped", worker_name=self._name)

    async def _run_loop(self) -> None:
        """Run the sleep-then-work loop until cancelled."""
        while True:
            try:
                await asyncio.sleep(self._interval_seconds)
                await self._execute_cycle()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.warning(
                    "periodic_worker_cycle_error",
                    worker_name=self._name,
                    exc_info=True,
                )

    async def _execute_cycle(self) -> None:
        """Execute a single cycle, optionally coordinated by advisory lock.

        When coordination is enabled, a transaction-level advisory lock
        (``pg_try_advisory_xact_lock``) is acquired before running the
        callback.  The lock auto-releases when the session's transaction
        ends — i.e. when the ``async with`` block exits and the session
        performs an implicit ROLLBACK.  This is safe with connection pooling
        because the lock is tied to the *transaction*, not the underlying
        connection.
        """
        if not self._coordinate:
            await self._callback(self._session_factory)
            return

        # Coordinated mode: acquire transaction-level advisory lock.
        # The lock auto-releases when the session context manager exits
        # (transaction ROLLBACK), so no explicit unlock is needed.
        if self._session_factory is None:
            return
        async with self._session_factory() as session:
            try:
                acquired = await _try_advisory_xact_lock(session, self._lock_key)
            except SQLAlchemyError:
                logger.warning(
                    "periodic_worker_lock_error",
                    worker_name=self._name,
                    exc_info=True,
                )
                return

            if not acquired:
                logger.debug(
                    "periodic_worker_lock_skipped",
                    worker_name=self._name,
                )
                return

            await self._callback(self._session_factory)
