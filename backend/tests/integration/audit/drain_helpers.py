"""Helpers for audit outbox drain/recovery integration tests.

Provides utilities to block the production drain worker, measure outbox depth,
run controlled drain cycles, and collect PostgreSQL table bloat statistics.

Drain-rate calculations use ``get_drain_settings()``, which reads
``AUDIT_PERF_DRAIN_BATCH_SIZE`` / ``AUDIT_PERF_DRAIN_POLL_INTERVAL`` when set.
These should mirror the running AO deployment's ``audit_outbox_*`` settings.

Depth polling in ``wait_for_outbox_drain()`` uses ``AUDIT_PERF_WAIT_POLL_INTERVAL``
(default 0.5s), separate from the production worker poll interval.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import text

from syntara.audit.outbox.worker import publish_outbox_events
from syntara.core.config.base import get_settings
from syntara.core.workers.periodic import derive_lock_key

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)

PRODUCTION_WORKER_NAME = "audit-outbox-worker"

# Prefix for event_action values that identify perf-test outbox rows
PERF_DRAIN_MARKER_PREFIX = "perf_test.outbox_drain"

DEFAULT_DRAIN_TIMEOUT_SECONDS = float(os.environ.get("AUDIT_PERF_DRAIN_TIMEOUT_SECONDS", "120"))
DEFAULT_BURST_BASELINE_SECONDS = float(os.environ.get("AUDIT_PERF_BURST_BASELINE_SECONDS", "30"))
DEFAULT_WAIT_POLL_INTERVAL_SECONDS = float(os.environ.get("AUDIT_PERF_WAIT_POLL_INTERVAL", "0.5"))
DEFAULT_BLOAT_MAX_RATIO = float(os.environ.get("AUDIT_PERF_BLOAT_MAX_RATIO", "0.5"))
DEFAULT_SETTLING_SECONDS = float(os.environ.get("AUDIT_PERF_SETTLING_SECONDS", "8"))
DEFAULT_QUIESCENT_MAX_DEPTH = int(os.environ.get("AUDIT_PERF_QUIESCENT_MAX_DEPTH", "0"))
DEFAULT_QUIESCENT_TIMEOUT_SECONDS = float(
    os.environ.get("AUDIT_PERF_QUIESCENT_TIMEOUT", str(DEFAULT_DRAIN_TIMEOUT_SECONDS))
)
DRAIN_TIMEOUT_HEADROOM_FACTOR = float(os.environ.get("AUDIT_PERF_DRAIN_TIMEOUT_HEADROOM", "2.0"))


PRODUCTION_DRAIN_LOCK_KEY = derive_lock_key(PRODUCTION_WORKER_NAME)


@dataclass(frozen=True)
class DrainSettings:
    """Effective drain worker settings for perf test calculations."""

    batch_size: int
    poll_interval_seconds: float


def get_drain_settings() -> DrainSettings:
    """Return drain batch size and poll interval for perf test calculations.

    Prefers ``AUDIT_PERF_DRAIN_BATCH_SIZE`` and ``AUDIT_PERF_DRAIN_POLL_INTERVAL``
    when set so the test runner can mirror the live AO deployment config.
    """
    settings = get_settings()
    batch_size = int(os.environ.get("AUDIT_PERF_DRAIN_BATCH_SIZE", str(settings.audit_outbox_batch_size)))
    poll_interval = float(
        os.environ.get(
            "AUDIT_PERF_DRAIN_POLL_INTERVAL",
            str(settings.audit_outbox_poll_interval_seconds),
        )
    )
    return DrainSettings(batch_size=batch_size, poll_interval_seconds=poll_interval)


def log_drain_settings_for_deployment() -> None:
    """Log effective drain settings and warn when AO mirroring env vars are unset."""
    drain = get_drain_settings()
    from_env = "AUDIT_PERF_DRAIN_BATCH_SIZE" in os.environ and "AUDIT_PERF_DRAIN_POLL_INTERVAL" in os.environ
    logger.info(
        "audit_perf_drain_settings",
        batch_size=drain.batch_size,
        poll_interval_seconds=drain.poll_interval_seconds,
        drain_rate_eps=drain.batch_size / drain.poll_interval_seconds,
        from_env=from_env,
    )
    if not from_env:
        logger.warning(
            "audit_perf_drain_settings_not_mirrored — "
            "set AUDIT_PERF_DRAIN_BATCH_SIZE and AUDIT_PERF_DRAIN_POLL_INTERVAL "
            "to match the AO deployment",
        )


def parse_rate_levels(env_value: str) -> list[int]:
    """Parse a comma-separated list of ingestion rates (events/sec)."""
    rates = [int(x) for x in env_value.split(",") if x.strip()]
    if not rates:
        msg = "AUDIT_PERF_SUSTAINED_RATES must contain at least one integer rate"
        raise ValueError(msg)
    return rates


@dataclass
class DrainWaitResult:
    """Result of waiting for the outbox to drain."""

    elapsed_seconds: float
    initial_depth: int
    peak_depth: int
    final_depth: int
    timed_out: bool = False

    def log(self, *, label: str) -> None:
        logger.info(
            "outbox_drain_wait_result",
            label=label,
            elapsed_s=round(self.elapsed_seconds, 3),
            initial_depth=self.initial_depth,
            peak_depth=self.peak_depth,
            final_depth=self.final_depth,
            timed_out=self.timed_out,
        )


@dataclass
class SustainedLoadResult:
    """Result of a sustained load window at a target ingestion rate."""

    target_rate_eps: float
    duration_seconds: float
    initial_depth: int
    post_ingest_depth: int
    final_depth: int
    peak_depth: int
    settling_seconds: float
    achieved_ingestion_rate: float = 0.0

    @property
    def depth_delta(self) -> int:
        return self.final_depth - self.initial_depth

    @property
    def settling_depth_delta(self) -> int:
        return self.final_depth - self.post_ingest_depth

    @property
    def is_stable(self) -> bool:
        """True when depth returned near zero after the post-ingest settling phase.

        Requires both a low absolute final depth and no continued growth during
        settling (settling_depth_delta near zero or negative).

        Stability threshold: max(5, target_rate * 0.1)
        - Allows 10% of the target ingestion rate as acceptable residual depth
        - Minimum threshold of 5 events handles low-rate edge cases
        - Both final_depth and settling_depth_delta must be below threshold
        """
        threshold = max(5, int(self.target_rate_eps * 0.1))
        return self.final_depth <= threshold and self.settling_depth_delta <= threshold


@dataclass
class TableBloatStats:
    """PostgreSQL table statistics for audit_outbox bloat measurement."""

    live_tuples: int
    dead_tuples: int
    bloat_ratio: float
    last_autovacuum: str | None
    last_autoanalyze: str | None
    table_size_bytes: int

    def log(self) -> None:
        logger.info(
            "audit_outbox_bloat_stats",
            live_tuples=self.live_tuples,
            dead_tuples=self.dead_tuples,
            bloat_ratio=round(self.bloat_ratio, 4),
            last_autovacuum=self.last_autovacuum,
            last_autoanalyze=self.last_autoanalyze,
            table_size_bytes=self.table_size_bytes,
        )


def make_drain_marker(test_name: str) -> str:
    """Build a unique event_action marker for filtering perf-test rows."""
    return f"{PERF_DRAIN_MARKER_PREFIX}.{test_name}.{time.time_ns()}"


async def get_outbox_depth(session: AsyncSession) -> int:
    """Return the current number of rows in audit_outbox."""
    result = await session.execute(text("SELECT COUNT(*) FROM audit_outbox"))
    return result.scalar() or 0


async def get_tagged_outbox_depth(session: AsyncSession, marker: str) -> int:
    """Return outbox rows whose event_action starts with *marker*."""
    result = await session.execute(
        text("SELECT COUNT(*) FROM audit_outbox WHERE event_payload->>'event_action' LIKE :marker_prefix"),
        {"marker_prefix": f"{marker}%"},
    )
    return result.scalar() or 0


async def get_table_bloat_stats(session: AsyncSession) -> TableBloatStats:
    """Collect live/dead tuple counts and autovacuum metadata for audit_outbox."""
    stats_result = await session.execute(
        text(
            """
            SELECT
                n_live_tup,
                n_dead_tup,
                last_autovacuum,
                last_autoanalyze
            FROM pg_stat_user_tables
            WHERE schemaname = current_schema()
              AND relname = 'audit_outbox'
            """
        )
    )
    row = stats_result.one_or_none()
    live = int(row[0] or 0) if row else 0
    dead = int(row[1] or 0) if row else 0
    last_autovacuum = str(row[2]) if row and row[2] else None
    last_autoanalyze = str(row[3]) if row and row[3] else None

    size_result = await session.execute(text("SELECT pg_total_relation_size('audit_outbox')"))
    table_size = int(size_result.scalar() or 0)

    total = live + dead
    bloat_ratio = dead / total if total > 0 else 0.0

    return TableBloatStats(
        live_tuples=live,
        dead_tuples=dead,
        bloat_ratio=bloat_ratio,
        last_autovacuum=last_autovacuum,
        last_autoanalyze=last_autoanalyze,
        table_size_bytes=table_size,
    )


async def wait_for_outbox_drain(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    timeout_seconds: float = DEFAULT_DRAIN_TIMEOUT_SECONDS,
    poll_interval: float = DEFAULT_WAIT_POLL_INTERVAL_SECONDS,
    marker: str | None = None,
    max_depth: int = 0,
) -> DrainWaitResult:
    """Poll outbox depth until at or below *max_depth* or *timeout_seconds* elapses."""
    start = time.monotonic()
    deadline = start + timeout_seconds

    async with session_factory() as session:
        if marker:
            initial_depth = await get_tagged_outbox_depth(session, marker)
        else:
            initial_depth = await get_outbox_depth(session)

    peak_depth = initial_depth
    final_depth = initial_depth

    while time.monotonic() < deadline:
        async with session_factory() as session:
            if marker:
                final_depth = await get_tagged_outbox_depth(session, marker)
            else:
                final_depth = await get_outbox_depth(session)

        peak_depth = max(peak_depth, final_depth)
        if final_depth <= max_depth:
            break

        await asyncio.sleep(poll_interval)

    elapsed = time.monotonic() - start
    return DrainWaitResult(
        elapsed_seconds=elapsed,
        initial_depth=initial_depth,
        peak_depth=peak_depth,
        final_depth=final_depth,
        timed_out=final_depth > max_depth,
    )


async def run_drain_cycles(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    timeout_seconds: float = DEFAULT_DRAIN_TIMEOUT_SECONDS,
    poll_interval: float | None = None,
    marker: str | None = None,
) -> DrainWaitResult:
    """Actively drain the outbox by calling ``publish_outbox_events`` in a loop.

    Mimics the production worker's publish cycle.  Uses ``poll_interval=0`` for
    fast cleanup between sustained-load iterations.
    """
    drain_settings = get_drain_settings()
    interval = poll_interval if poll_interval is not None else drain_settings.poll_interval_seconds

    start = time.monotonic()
    deadline = start + timeout_seconds

    async with session_factory() as session:
        if marker:
            initial_depth = await get_tagged_outbox_depth(session, marker)
        else:
            initial_depth = await get_outbox_depth(session)

    peak_depth = initial_depth
    final_depth = initial_depth

    while time.monotonic() < deadline:
        await publish_outbox_events(session_factory)

        async with session_factory() as session:
            if marker:
                final_depth = await get_tagged_outbox_depth(session, marker)
            else:
                final_depth = await get_outbox_depth(session)

        peak_depth = max(peak_depth, final_depth)
        if final_depth == 0:
            break

        if interval > 0:
            await asyncio.sleep(min(interval, max(0.0, deadline - time.monotonic())))

    elapsed = time.monotonic() - start
    return DrainWaitResult(
        elapsed_seconds=elapsed,
        initial_depth=initial_depth,
        peak_depth=peak_depth,
        final_depth=final_depth,
        timed_out=final_depth > 0,
    )


async def drain_marker_to_zero(
    session_factory: async_sessionmaker[AsyncSession],
    marker: str,
    *,
    timeout_seconds: float = DEFAULT_DRAIN_TIMEOUT_SECONDS,
) -> DrainWaitResult:
    """Drain all rows matching *marker* as fast as possible (test cleanup)."""
    return await run_drain_cycles(
        session_factory,
        timeout_seconds=timeout_seconds,
        poll_interval=0.0,
        marker=marker,
    )


async def wait_for_quiescent_outbox(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    timeout_seconds: float = DEFAULT_QUIESCENT_TIMEOUT_SECONDS,
    max_depth: int | None = None,
) -> int:
    """Wait until total outbox depth is at or below *max_depth*.

    Returns the observed depth at quiescence.  On shared deployments, set
    ``AUDIT_PERF_QUIESCENT_MAX_DEPTH`` to tolerate background audit traffic
    instead of requiring a globally empty outbox.
    """
    allowed_depth = DEFAULT_QUIESCENT_MAX_DEPTH if max_depth is None else max_depth
    result = await wait_for_outbox_drain(
        session_factory,
        timeout_seconds=timeout_seconds,
        marker=None,
        max_depth=allowed_depth,
    )
    if result.timed_out:
        msg = (
            f"Outbox did not reach quiescent state (depth={result.final_depth}, "
            f"max_allowed={allowed_depth}) within {timeout_seconds}s. "
            "Raise AUDIT_PERF_QUIESCENT_MAX_DEPTH on shared deployments."
        )
        raise TimeoutError(msg)
    return result.final_depth


@asynccontextmanager
async def block_production_drain(
    engine: AsyncEngine,
    *,
    acquire_timeout: float = 30.0,
) -> AsyncGenerator[None, None]:
    """Hold the production audit-outbox-worker advisory lock for the block duration.

    Acquires a transaction-level PostgreSQL advisory lock (``pg_try_advisory_xact_lock``)
    using the same key and lock type as the production ``PeriodicWorker``.  While the
    transaction remains open, the production drain worker cannot acquire its lock and
    will skip drain cycles — simulating OTEL collector unavailability.

    Retries for up to *acquire_timeout* seconds since the production worker may
    briefly hold the lock during an active drain cycle.
    """
    lock_key = PRODUCTION_DRAIN_LOCK_KEY
    async with engine.connect() as conn:
        trans = await conn.begin()
        deadline = time.monotonic() + acquire_timeout
        acquired = False

        while time.monotonic() < deadline:
            result = await conn.execute(
                text("SELECT pg_try_advisory_xact_lock(:key)"),
                {"key": lock_key},
            )
            if result.scalar():
                acquired = True
                break
            await asyncio.sleep(0.5)

        if not acquired:
            await trans.rollback()
            msg = (
                f"Could not acquire production drain advisory lock within {acquire_timeout}s — "
                "the production worker may be mid-cycle or another test is holding it"
            )
            raise RuntimeError(msg)

        logger.info("production_drain_blocked", lock_key=lock_key)
        try:
            yield
        finally:
            await trans.rollback()
            logger.info("production_drain_unblocked", lock_key=lock_key)


async def ingest_at_rate(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    rate_eps: float,
    duration_seconds: float,
    marker: str,
    batch_size: int = 100,
) -> tuple[int, float]:
    """Insert outbox rows at a steady *rate_eps* for *duration_seconds*.

    Returns (rows_inserted, actual_elapsed_seconds).
    """
    from tests.integration.audit.seeder import seed_audit_outbox

    target_rows = max(1, int(rate_eps * duration_seconds))
    start = time.monotonic()

    remaining = target_rows
    inserted = 0
    while remaining > 0:
        current_batch = min(batch_size, remaining)

        await seed_audit_outbox(
            session_factory,
            row_count=current_batch,
            batch_size=current_batch,
            track_ids=False,
            event_action=f"{marker}.{inserted}",
        )
        inserted += current_batch
        remaining -= current_batch

        expected_elapsed = inserted / rate_eps
        actual_elapsed = time.monotonic() - start
        sleep_for = expected_elapsed - actual_elapsed
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)

    elapsed = time.monotonic() - start
    return inserted, elapsed


async def run_sustained_load_window(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    target_rate_eps: float,
    duration_seconds: float,
    marker: str,
    drain_enabled: bool,
    settling_seconds: float | None = None,
) -> SustainedLoadResult:
    """Run ingestion (and optional drain) for a fixed window and sample depth.

    After ingestion completes, continues draining and sampling for a settling
    phase so stable rates can reach equilibrium before measuring final depth.
    """
    drain_settings = get_drain_settings()
    poll_interval = drain_settings.poll_interval_seconds
    settling = settling_seconds if settling_seconds is not None else DEFAULT_SETTLING_SECONDS

    async with session_factory() as session:
        initial_depth = await get_tagged_outbox_depth(session, marker)

    stop_event = asyncio.Event()
    peak_depth = initial_depth
    background_tasks: list[asyncio.Task[None]] = []

    async def _drain_loop() -> None:
        while not stop_event.is_set():
            await publish_outbox_events(session_factory)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
            except TimeoutError:
                continue

    if drain_enabled:
        background_tasks.append(asyncio.create_task(_drain_loop()))

    inserted, ingest_elapsed = await ingest_at_rate(
        session_factory,
        rate_eps=target_rate_eps,
        duration_seconds=duration_seconds,
        marker=marker,
    )

    async with session_factory() as session:
        post_ingest_depth = await get_tagged_outbox_depth(session, marker)
    peak_depth = max(peak_depth, post_ingest_depth)

    if drain_enabled and settling > 0:
        await asyncio.sleep(settling)

    stop_event.set()
    for task in background_tasks:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async with session_factory() as session:
        final_depth = await get_tagged_outbox_depth(session, marker)
    peak_depth = max(peak_depth, final_depth)

    achieved_rate = inserted / ingest_elapsed if ingest_elapsed > 0 else 0.0

    return SustainedLoadResult(
        target_rate_eps=target_rate_eps,
        duration_seconds=duration_seconds,
        initial_depth=initial_depth,
        post_ingest_depth=post_ingest_depth,
        final_depth=final_depth,
        peak_depth=peak_depth,
        settling_seconds=settling if drain_enabled else 0.0,
        achieved_ingestion_rate=achieved_rate,
    )


def estimate_max_drain_rate_eps() -> float:
    """Estimate upper-bound drain rate from batch size and poll interval.

    Assumes a full batch every poll cycle with zero OTEL publish latency.
    Real throughput is typically lower.
    """
    drain_settings = get_drain_settings()
    return drain_settings.batch_size / drain_settings.poll_interval_seconds


def estimate_drain_timeout_seconds(row_count: int) -> float:
    """Estimate how long drain needs to clear *row_count* events.

    Scales with backlog size and effective drain rate.  Always at least
    ``DEFAULT_DRAIN_TIMEOUT_SECONDS``.
    """
    if row_count <= 0:
        return DEFAULT_DRAIN_TIMEOUT_SECONDS

    drain_rate = estimate_max_drain_rate_eps()
    if drain_rate <= 0:
        return DEFAULT_DRAIN_TIMEOUT_SECONDS

    theoretical_seconds = row_count / drain_rate
    return max(DEFAULT_DRAIN_TIMEOUT_SECONDS, theoretical_seconds * DRAIN_TIMEOUT_HEADROOM_FACTOR)
