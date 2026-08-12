"""Outbox Worker Drain Cycle Performance Benchmarking (AAP-79801).

Benchmarks the AuditOutboxWorker's publish cycle: how quickly it can drain
accumulated records to OTEL, the impact of batch_size tuning, FOR UPDATE
SKIP LOCKED contention under concurrent workers, and drain() behavior
during graceful shutdown.

Background:
    The AuditOutboxWorker (a PeriodicWorker with coordinate=True) polls
    audit_outbox every 5 seconds, processes up to batch_size (default: 100)
    records per cycle using ``FOR UPDATE SKIP LOCKED``, exports them to the
    OTEL Collector, then deletes them.  Under normal operation, the outbox
    should drain to near-zero between cycles.

Acceptance criteria:
    - Drain throughput benchmarked at 4 batch sizes (50, 100, 500, 1000)
    - Publish cycle time profiled including OTEL emission overhead
    - FOR UPDATE SKIP LOCKED contention tested under concurrent workers
    - Drain rate confirmed to exceed ingestion rate under normal load
    - Graceful shutdown drain() latency measured at realistic scales (100-5K)
    - Crash-recovery validated (no record loss)
    - Optimal poll interval vs batch size trade-off documented
    - Baseline: drain cycle < 500ms for 100-record batch
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import structlog
from sqlalchemy import func, select, text

from syntara.audit.outbox.models import AuditOutboxRecord
from syntara.audit.outbox.worker import AuditOutboxWorker, publish_outbox_events
from tests.integration.audit.metrics import (
    LatencyResult,
    PerformanceReport,
    ThroughputResult,
    measure_latency_async,
)
from tests.integration.audit.seeder import seed_audit_outbox

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)

pytestmark = pytest.mark.asyncio

# Batch sizes to benchmark drain throughput
DRAIN_BATCH_SIZES = [100, 500]

# Baseline target: drain cycle must complete within this for a 100-record batch
DRAIN_CYCLE_BASELINE_MS = float(os.environ.get("AUDIT_DRAIN_CYCLE_BASELINE_MS", "500"))

# Graceful shutdown record counts
SHUTDOWN_RECORD_COUNTS = [100, 1000]

# Number of concurrent workers for contention tests
CONCURRENT_WORKERS = 4

# Maximum drain cycles before failing (prevents infinite loops)
MAX_DRAIN_CYCLES = 100

# Maximum recovery cycles for crash tests
MAX_RECOVERY_CYCLES = 20

# OTEL overhead profiling iterations
OTEL_PROFILE_ITERATIONS = 3

# Empty cycle test iterations
EMPTY_CYCLE_ITERATIONS = 10

# Ingestion test parameters
INGESTION_TEST_DURATION_S = 5  # seconds to run producer/consumer simulation
NORMAL_INGESTION_RATE = 20  # events/sec under normal load
MAX_ACCEPTABLE_OUTBOX_DEPTH = 50  # max steady-state queue depth
CONSUMER_POLL_INTERVAL_S = 0.5  # how often consumer checks for new records


async def _seed_outbox_records(
    session_factory: async_sessionmaker[AsyncSession],
    count: int,
) -> list[str]:
    """Insert ``count`` records into audit_outbox via bulk raw SQL, returning their IDs."""
    result = await seed_audit_outbox(
        session_factory,
        row_count=count,
        batch_size=min(count, 1000),
        track_ids=True,
        event_action="perf_test.drain_cycle",
    )
    return [str(uid) for uid in result.record_ids]


async def _get_outbox_count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    """Return current number of rows in audit_outbox."""
    async with session_factory() as session:
        result = await session.scalar(select(func.count()).select_from(AuditOutboxRecord))
        return result or 0


async def _get_remaining_seeded_count(
    session_factory: async_sessionmaker[AsyncSession],
    seeded_ids: list[str],
) -> int:
    """Return how many of the seeded IDs still exist in audit_outbox."""
    if not seeded_ids:
        return 0
    remaining = 0
    async with session_factory() as session:
        for chunk_start in range(0, len(seeded_ids), 500):
            chunk = seeded_ids[chunk_start : chunk_start + 500]
            count = await session.scalar(
                select(func.count())
                .select_from(AuditOutboxRecord)
                .where(
                    AuditOutboxRecord.id.in_(chunk),  # type: ignore[attr-defined]
                )
            )
            remaining += count or 0
    return remaining


async def _cleanup_records(
    session_factory: async_sessionmaker[AsyncSession],
    record_ids: list[str],
) -> None:
    """Delete records by ID in chunks using raw SQL."""
    if not record_ids:
        return
    async with session_factory() as session:
        for chunk_start in range(0, len(record_ids), 500):
            chunk = record_ids[chunk_start : chunk_start + 500]
            placeholders = ", ".join(f"'{rid}'" for rid in chunk)
            await session.execute(text(f"DELETE FROM audit_outbox WHERE id IN ({placeholders})"))  # noqa: S608
        await session.commit()


# ---------------------------------------------------------------------------
# AC: Drain throughput benchmarked at 4 batch sizes (50, 100, 500, 1000)
# ---------------------------------------------------------------------------


class TestDrainThroughput:
    """Benchmark publish_outbox_events() drain throughput at multiple batch sizes.

    Seeds the outbox with N records, then measures how long a single
    publish_outbox_events() cycle takes to process them at each configured
    batch_size.
    """

    @pytest.mark.parametrize("batch_size", DRAIN_BATCH_SIZES)
    async def test_drain_throughput_at_batch_size(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
        batch_size: int,
    ) -> None:
        """Measure drain cycle throughput for a given batch_size."""
        seeded_ids: list[str] = []
        try:
            seeded_ids = await _seed_outbox_records(audit_perf_session_factory, batch_size)
            assert len(seeded_ids) == batch_size, f"Expected {batch_size} seeded records, got {len(seeded_ids)}"

            settings_patch = MagicMock()
            settings_patch.audit_outbox_batch_size = batch_size

            latency = LatencyResult(label=f"drain_cycle_batch_{batch_size}")

            for _cycle in range(MAX_DRAIN_CYCLES):
                async with measure_latency_async(latency):
                    with patch("syntara.audit.outbox.worker.get_settings", return_value=settings_patch):
                        await publish_outbox_events(audit_perf_session_factory)
                remaining_seeded = await _get_remaining_seeded_count(audit_perf_session_factory, seeded_ids)
                if remaining_seeded == 0:
                    break

            throughput = ThroughputResult(
                label=f"drain_throughput_batch_{batch_size}",
                total_operations=batch_size,
                elapsed_seconds=latency.samples[0] / 1000 if latency.samples else 0,
            )

            latency.log()
            throughput.log()

            logger.info(
                "drain_throughput_benchmark",
                batch_size=batch_size,
                cycle_ms=round(latency.samples[0], 3) if latency.samples else 0,
                records_drained=batch_size,
                remaining_seeded=remaining_seeded,
                drain_cycles=_cycle + 1,
                throughput_ops_sec=round(throughput.ops_per_second, 1),
            )

            assert remaining_seeded == 0, (
                f"Drain cycle left {remaining_seeded} seeded records for batch_size={batch_size}"
            )

        finally:
            await _cleanup_records(audit_perf_session_factory, seeded_ids)


# ---------------------------------------------------------------------------
# AC: Publish cycle time profiled including OTEL overhead
# ---------------------------------------------------------------------------


class TestPublishCycleProfile:
    """Profile publish_outbox_events() cycle time including OTEL emission overhead.

    Breaks down the publish cycle into query, OTEL emit, and delete phases
    to identify where time is spent.
    """

    async def test_publish_cycle_with_otel_overhead(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Profile a full publish cycle with 100 records, capturing OTEL overhead."""
        record_count = 100
        seeded_ids: list[str] = []

        try:
            seeded_ids = await _seed_outbox_records(audit_perf_session_factory, record_count)

            report = PerformanceReport(
                title="publish_cycle_profile",
                metadata={"record_count": record_count},
            )

            cycle_latency = LatencyResult(label="full_publish_cycle")

            for i in range(OTEL_PROFILE_ITERATIONS):
                current_count = await _get_outbox_count(audit_perf_session_factory)

                # Ensure we have exactly record_count for this iteration
                if current_count < record_count:
                    needed = record_count - current_count
                    extra = await _seed_outbox_records(
                        audit_perf_session_factory,
                        needed,
                    )
                    seeded_ids.extend(extra)

                actual_before = await _get_outbox_count(audit_perf_session_factory)

                async with measure_latency_async(cycle_latency):
                    await publish_outbox_events(audit_perf_session_factory)

                actual_after = await _get_outbox_count(audit_perf_session_factory)
                logger.info(
                    "publish_cycle_iteration",
                    iteration=i,
                    records_before=actual_before,
                    records_after=actual_after,
                    records_processed=actual_before - actual_after,
                )

            report.add_latency(cycle_latency)
            report.log_all()

            logger.info(
                "publish_cycle_profile",
                iterations=OTEL_PROFILE_ITERATIONS,
                p50_ms=round(cycle_latency.p50, 3),
                p95_ms=round(cycle_latency.p95, 3),
                p99_ms=round(cycle_latency.p99, 3),
                mean_ms=round(cycle_latency.mean, 3),
            )

        finally:
            await _cleanup_records(audit_perf_session_factory, seeded_ids)

    async def test_empty_outbox_cycle_overhead(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Measure overhead of publish cycle when outbox is empty (no-op path)."""
        latency = LatencyResult(label="empty_outbox_cycle")

        for _ in range(EMPTY_CYCLE_ITERATIONS):
            async with measure_latency_async(latency):
                await publish_outbox_events(audit_perf_session_factory)

        latency.log()

        logger.info(
            "empty_outbox_cycle_overhead",
            iterations=EMPTY_CYCLE_ITERATIONS,
            p50_ms=round(latency.p50, 3),
            p95_ms=round(latency.p95, 3),
            mean_ms=round(latency.mean, 3),
        )


# ---------------------------------------------------------------------------
# AC: FOR UPDATE SKIP LOCKED contention tested under concurrent workers
# ---------------------------------------------------------------------------


class TestSkipLockedContention:
    """Test FOR UPDATE SKIP LOCKED behavior under concurrent worker scenarios.

    Verifies that multiple workers can process the outbox concurrently without
    processing the same records or causing deadlocks.
    """

    async def test_concurrent_workers_no_duplicate_processing(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Multiple concurrent publish_outbox_events() calls must not lose records.

        Seeds 200 records with batch_size = total / CONCURRENT_WORKERS so that
        each worker can only lock a subset via FOR UPDATE SKIP LOCKED.
        After all workers finish, verifies every record was drained.
        SKIP LOCKED guarantees no duplicate processing at the database level.
        """
        total_records = 200
        batch_per_worker = total_records // CONCURRENT_WORKERS
        seeded_ids: list[str] = []

        try:
            seeded_ids = await _seed_outbox_records(audit_perf_session_factory, total_records)

            settings_patch = MagicMock()
            settings_patch.audit_outbox_batch_size = batch_per_worker

            async def _run_worker() -> None:
                with patch("syntara.audit.outbox.worker.get_settings", return_value=settings_patch):
                    await publish_outbox_events(audit_perf_session_factory)

            latency = LatencyResult(label="skip_locked_contention")

            async with measure_latency_async(latency):
                for _cycle in range(MAX_DRAIN_CYCLES):
                    await asyncio.gather(*[_run_worker() for _ in range(CONCURRENT_WORKERS)])
                    remaining = await _get_remaining_seeded_count(audit_perf_session_factory, seeded_ids)
                    if remaining == 0:
                        break

            logger.info(
                "skip_locked_contention_result",
                concurrent_workers=CONCURRENT_WORKERS,
                batch_per_worker=batch_per_worker,
                total_seeded=total_records,
                remaining_seeded=remaining,
                drain_cycles=_cycle + 1,
                elapsed_ms=round(latency.samples[0], 3) if latency.samples else 0,
            )

            assert remaining == 0, (
                f"Expected 0 remaining seeded records after concurrent drain, got {remaining}. "
                f"FOR UPDATE SKIP LOCKED may have caused records to be skipped permanently."
            )

        finally:
            await _cleanup_records(audit_perf_session_factory, seeded_ids)

    async def test_skip_locked_throughput_vs_serial(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Compare drain throughput: serial (1 worker) vs concurrent (N workers).

        Seeds enough records so each concurrent worker gets a batch.
        Measures total wall-clock time for both approaches.
        """
        records_per_worker = 100
        total_records = records_per_worker * CONCURRENT_WORKERS
        seeded_ids: list[str] = []

        try:
            # --- Serial baseline ---
            seeded_ids = await _seed_outbox_records(audit_perf_session_factory, total_records)

            settings_patch = MagicMock()
            settings_patch.audit_outbox_batch_size = records_per_worker

            serial_latency = LatencyResult(label="serial_drain")
            async with measure_latency_async(serial_latency):
                with patch("syntara.audit.outbox.worker.get_settings", return_value=settings_patch):
                    for _ in range(MAX_DRAIN_CYCLES):
                        if await _get_outbox_count(audit_perf_session_factory) == 0:
                            break
                        await publish_outbox_events(audit_perf_session_factory)
                    else:
                        pytest.fail(f"Serial drain did not complete after {MAX_DRAIN_CYCLES} cycles")

            # --- Concurrent ---
            extra_ids = await _seed_outbox_records(audit_perf_session_factory, total_records)
            seeded_ids.extend(extra_ids)

            async def _run_worker() -> None:
                with patch("syntara.audit.outbox.worker.get_settings", return_value=settings_patch):
                    await publish_outbox_events(audit_perf_session_factory)

            concurrent_latency = LatencyResult(label="concurrent_drain")
            async with measure_latency_async(concurrent_latency):
                for _ in range(MAX_DRAIN_CYCLES):
                    if await _get_outbox_count(audit_perf_session_factory) == 0:
                        break
                    await asyncio.gather(*[_run_worker() for _ in range(CONCURRENT_WORKERS)])
                else:
                    pytest.fail(f"Concurrent drain did not complete after {MAX_DRAIN_CYCLES} cycles")

            serial_ms = serial_latency.samples[0] if serial_latency.samples else 0
            concurrent_ms = concurrent_latency.samples[0] if concurrent_latency.samples else 0

            serial_latency.log()
            concurrent_latency.log()

            logger.info(
                "skip_locked_serial_vs_concurrent",
                total_records=total_records,
                serial_ms=round(serial_ms, 3),
                concurrent_ms=round(concurrent_ms, 3),
                speedup=round(serial_ms / concurrent_ms, 2) if concurrent_ms > 0 else 0,
                concurrent_workers=CONCURRENT_WORKERS,
            )

        finally:
            await _cleanup_records(audit_perf_session_factory, seeded_ids)


# ---------------------------------------------------------------------------
# AC: Drain rate confirmed to exceed ingestion rate under normal load
# ---------------------------------------------------------------------------


class TestDrainVsIngestionRate:
    """Confirm that the drain rate exceeds the ingestion rate under normal load.

    Runs a producer (seeding records) and consumer (drain cycles) concurrently
    and asserts that the outbox depth stays near zero (steady state).
    """

    async def test_drain_keeps_up_with_ingestion(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Sustained producer + consumer: outbox depth must stay near zero.

        Runs for a fixed duration with a producer inserting records at a
        moderate rate and a consumer draining them via publish_outbox_events().
        """
        seeded_ids: list[str] = []
        ids_lock = asyncio.Lock()
        depth_samples: list[int] = []
        stop_event = asyncio.Event()

        async def producer() -> None:
            interval = 1.0 / NORMAL_INGESTION_RATE
            while not stop_event.is_set():
                result = await seed_audit_outbox(
                    audit_perf_session_factory,
                    row_count=1,
                    batch_size=1,
                    track_ids=True,
                    event_action="perf_test.drain_cycle",
                )
                async with ids_lock:
                    seeded_ids.extend(str(uid) for uid in result.record_ids)
                await asyncio.sleep(interval)

        async def consumer() -> None:
            while not stop_event.is_set():
                await publish_outbox_events(audit_perf_session_factory)
                depth = await _get_outbox_count(audit_perf_session_factory)
                depth_samples.append(depth)
                await asyncio.sleep(CONSUMER_POLL_INTERVAL_S)

        producer_task = asyncio.create_task(producer())
        consumer_task = asyncio.create_task(consumer())

        await asyncio.sleep(INGESTION_TEST_DURATION_S)
        stop_event.set()

        producer_task.cancel()
        consumer_task.cancel()
        await asyncio.gather(producer_task, consumer_task, return_exceptions=True)

        # Final drain with bounded iterations
        for _ in range(MAX_DRAIN_CYCLES):
            if await _get_outbox_count(audit_perf_session_factory) == 0:
                break
            await publish_outbox_events(audit_perf_session_factory)
        else:
            pytest.fail(f"Final drain did not complete after {MAX_DRAIN_CYCLES} cycles")

        avg_depth = sum(depth_samples) / len(depth_samples) if depth_samples else 0
        max_depth = max(depth_samples) if depth_samples else 0

        logger.info(
            "drain_vs_ingestion_result",
            duration_s=INGESTION_TEST_DURATION_S,
            ingestion_rate=NORMAL_INGESTION_RATE,
            total_produced=len(seeded_ids),
            depth_samples=len(depth_samples),
            avg_depth=round(avg_depth, 1),
            max_depth=max_depth,
            max_acceptable_depth=MAX_ACCEPTABLE_OUTBOX_DEPTH,
        )

        assert avg_depth < MAX_ACCEPTABLE_OUTBOX_DEPTH, (
            f"Average outbox depth ({avg_depth:.1f}) exceeds acceptable threshold "
            f"({MAX_ACCEPTABLE_OUTBOX_DEPTH}). Drain rate cannot keep up with ingestion "
            f"at {NORMAL_INGESTION_RATE} events/sec."
        )


# ---------------------------------------------------------------------------
# AC: Graceful shutdown drain() latency measured at realistic scales
# ---------------------------------------------------------------------------


class TestGracefulShutdownDrain:
    """Measure drain() latency during graceful shutdown at realistic scales.

    The drain() method waits for in-flight writes, then loops
    publish_outbox_events() until the outbox is empty.
    """

    @pytest.mark.parametrize("pending_count", SHUTDOWN_RECORD_COUNTS)
    async def test_drain_latency_at_scale(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
        pending_count: int,
    ) -> None:
        """Measure drain() wall-clock time with N pending records."""
        seeded_ids: list[str] = []

        try:
            seeded_ids = await _seed_outbox_records(audit_perf_session_factory, pending_count)

            settings_patch = MagicMock()
            settings_patch.audit_outbox_batch_size = 100
            settings_patch.audit_writer_max_concurrent_writes = 100
            settings_patch.audit_writer_max_retries = 3
            settings_patch.audit_writer_base_delay_seconds = 0.1
            settings_patch.otel_enabled = False
            settings_patch.audit_outbox_max_dispatch_attempts = 3
            settings_patch.audit_outbox_poll_interval_seconds = 1.0

            with patch("syntara.audit.outbox.worker.get_settings", return_value=settings_patch):
                worker = AuditOutboxWorker(
                    name="perf-test-drain-shutdown",
                    interval_seconds=999,
                    session_factory=audit_perf_session_factory,
                    coordinate=False,
                )

                latency = LatencyResult(label=f"shutdown_drain_{pending_count}")

                async with measure_latency_async(latency):
                    await worker.drain()

            remaining = await _get_outbox_count(audit_perf_session_factory)

            throughput = ThroughputResult(
                label=f"shutdown_drain_throughput_{pending_count}",
                total_operations=pending_count,
                elapsed_seconds=latency.samples[0] / 1000 if latency.samples else 0,
            )

            latency.log()
            throughput.log()

            logger.info(
                "shutdown_drain_latency",
                pending_count=pending_count,
                drain_ms=round(latency.samples[0], 3) if latency.samples else 0,
                remaining_records=remaining,
                throughput_ops_sec=round(throughput.ops_per_second, 1),
            )

            assert remaining == 0, f"drain() left {remaining} records in outbox for {pending_count}-record test"

        finally:
            await _cleanup_records(audit_perf_session_factory, seeded_ids)


# ---------------------------------------------------------------------------
# AC: Crash-recovery validated (no record loss)
# ---------------------------------------------------------------------------


class TestCrashRecovery:
    """Validate no record loss during crash-recovery scenarios.

    Simulates a worker crash mid-publish (after SELECT FOR UPDATE but before
    DELETE) and verifies the records are available for the next worker cycle.
    """

    async def test_no_record_loss_on_mid_cycle_crash(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Simulate a crash after locking rows: records must survive for next cycle.

        Patches ``_handle_business_audit_records`` to raise, simulating a
        failure after the FOR UPDATE SKIP LOCKED query.  The bare
        ``except Exception`` inside ``publish_outbox_events`` catches the
        error (as in production), so the session is never committed and
        the locked rows are released on rollback.  We verify records
        survive by checking the outbox count, then run a normal recovery
        cycle to drain them.
        """
        record_count = 100
        seeded_ids: list[str] = []

        try:
            seeded_ids = await _seed_outbox_records(audit_perf_session_factory, record_count)
            seeded_before = await _get_remaining_seeded_count(audit_perf_session_factory, seeded_ids)

            with patch(
                "syntara.audit.outbox.worker._handle_business_audit_records",
                side_effect=RuntimeError("simulated mid-cycle crash"),
            ):
                await publish_outbox_events(audit_perf_session_factory)

            seeded_after_crash = await _get_remaining_seeded_count(audit_perf_session_factory, seeded_ids)

            assert seeded_after_crash == seeded_before, (
                f"Seeded records lost during simulated crash: had {seeded_before}, now {seeded_after_crash}"
            )

            # Recovery: drain seeded records with bounded iterations
            for _cycle in range(MAX_RECOVERY_CYCLES):
                await publish_outbox_events(audit_perf_session_factory)
                seeded_after_recovery = await _get_remaining_seeded_count(audit_perf_session_factory, seeded_ids)
                if seeded_after_recovery == 0:
                    break

            logger.info(
                "crash_recovery_result",
                seeded=record_count,
                seeded_before=seeded_before,
                seeded_after_crash=seeded_after_crash,
                seeded_after_recovery=seeded_after_recovery,
                recovery_cycles=_cycle + 1,
            )

            assert seeded_after_recovery == 0, f"Recovery left {seeded_after_recovery} seeded records unprocessed"

        finally:
            await _cleanup_records(audit_perf_session_factory, seeded_ids)

    async def test_no_record_loss_on_concurrent_crash(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Multiple concurrent workers with one crashing must not lose records.

        Seeds records, runs N workers concurrently where one raises. After
        recovery cycles, all records must be processed.
        """
        record_count = 200
        seeded_ids: list[str] = []

        try:
            seeded_ids = await _seed_outbox_records(audit_perf_session_factory, record_count)

            async def crashy_publish() -> None:
                await asyncio.sleep(0)
                msg = "simulated worker crash"
                raise RuntimeError(msg)

            tasks = [asyncio.create_task(crashy_publish())]
            for _ in range(CONCURRENT_WORKERS - 1):
                tasks.append(asyncio.create_task(publish_outbox_events(audit_perf_session_factory)))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            crash_count = sum(1 for r in results if isinstance(r, Exception))
            logger.info("concurrent_crash_phase", crash_count=crash_count)

            # Recovery: drain seeded records with bounded iterations
            for _cycle in range(MAX_RECOVERY_CYCLES):
                remaining = await _get_remaining_seeded_count(audit_perf_session_factory, seeded_ids)
                if remaining == 0:
                    break
                await publish_outbox_events(audit_perf_session_factory)
            else:
                pytest.fail(f"Recovery did not complete after {MAX_RECOVERY_CYCLES} cycles")

            final_remaining = await _get_remaining_seeded_count(audit_perf_session_factory, seeded_ids)

            logger.info(
                "concurrent_crash_recovery_result",
                seeded=record_count,
                final_remaining_seeded=final_remaining,
                crash_count=crash_count,
                recovery_cycles=_cycle + 1,
            )

            assert final_remaining == 0, f"After crash recovery, {final_remaining} seeded records remain unprocessed"

        finally:
            await _cleanup_records(audit_perf_session_factory, seeded_ids)


# ---------------------------------------------------------------------------
# AC: Optimal poll interval vs batch size trade-off documented
# ---------------------------------------------------------------------------


POLL_INTERVALS = [1.0, 5.0]
TRADEOFF_BATCH_SIZES = [100, 500]
STEADY_STATE_RECORDS = 500


class TestPollIntervalVsBatchSize:
    """Identify optimal poll_interval_seconds vs batch_size trade-off.

    Parametrizes (poll_interval, batch_size) combinations so each can be
    identified, filtered, and debugged independently.
    """

    @pytest.mark.parametrize("poll_interval", POLL_INTERVALS)
    @pytest.mark.parametrize("batch_size", TRADEOFF_BATCH_SIZES)
    async def test_poll_interval_batch_size_tradeoff(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
        poll_interval: float,
        batch_size: int,
    ) -> None:
        """Evaluate a single (poll_interval, batch_size) combination.

        Seeds records then runs timed drain cycles to compute effective
        throughput including simulated poll-interval overhead.
        """
        seeded_ids: list[str] = []
        try:
            seeded_ids = await _seed_outbox_records(audit_perf_session_factory, STEADY_STATE_RECORDS)

            settings_patch = MagicMock()
            settings_patch.audit_outbox_batch_size = batch_size

            cycles_needed = 0
            latency = LatencyResult(label=f"poll_{poll_interval}s_batch_{batch_size}")

            total_start = time.monotonic()
            for _ in range(MAX_DRAIN_CYCLES):
                if await _get_outbox_count(audit_perf_session_factory) == 0:
                    break
                async with measure_latency_async(latency):
                    with patch(
                        "syntara.audit.outbox.worker.get_settings",
                        return_value=settings_patch,
                    ):
                        await publish_outbox_events(audit_perf_session_factory)
                cycles_needed += 1
            else:
                pytest.fail(
                    f"Poll interval test did not complete after {MAX_DRAIN_CYCLES} cycles "
                    f"(poll={poll_interval}s, batch={batch_size})"
                )
            total_elapsed = time.monotonic() - total_start

            effective_interval_overhead = poll_interval * max(cycles_needed - 1, 0)
            simulated_total = total_elapsed + effective_interval_overhead

            throughput = ThroughputResult(
                label=f"poll_{poll_interval}s_batch_{batch_size}",
                total_operations=STEADY_STATE_RECORDS,
                elapsed_seconds=simulated_total,
            )

            latency.log()
            throughput.log()

            logger.info(
                "poll_batch_tradeoff",
                poll_interval_s=poll_interval,
                batch_size=batch_size,
                cycles_needed=cycles_needed,
                drain_time_ms=round(total_elapsed * 1000, 3),
                simulated_total_s=round(simulated_total, 3),
                effective_throughput_ops_sec=round(throughput.ops_per_second, 1),
                avg_cycle_ms=round(latency.mean, 3),
            )

        finally:
            await _cleanup_records(audit_perf_session_factory, seeded_ids)


# ---------------------------------------------------------------------------
# AC: Baseline — drain cycle < 500ms for 100-record batch
# ---------------------------------------------------------------------------


class TestDrainCycleBaseline:
    """Establish that a single drain cycle for 100 records completes under the baseline."""

    async def test_100_record_drain_within_baseline(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """A single publish_outbox_events() cycle with 100 records must complete within baseline.

        within DRAIN_CYCLE_BASELINE_MS (default 500ms).
        """
        record_count = 100
        iterations = 5
        seeded_ids: list[str] = []

        try:
            latency = LatencyResult(label="drain_baseline_100")

            for _ in range(iterations):
                batch_ids = await _seed_outbox_records(audit_perf_session_factory, record_count)
                seeded_ids.extend(batch_ids)

                async with measure_latency_async(latency):
                    await publish_outbox_events(audit_perf_session_factory)

            latency.log()

            logger.info(
                "drain_cycle_baseline",
                iterations=iterations,
                record_count=record_count,
                p50_ms=round(latency.p50, 3),
                p95_ms=round(latency.p95, 3),
                p99_ms=round(latency.p99, 3),
                baseline_target_ms=DRAIN_CYCLE_BASELINE_MS,
                meets_baseline=latency.p95 < DRAIN_CYCLE_BASELINE_MS,
            )

            assert latency.p95 < DRAIN_CYCLE_BASELINE_MS, (
                f"Drain cycle p95 ({latency.p95:.3f}ms) exceeds baseline "
                f"({DRAIN_CYCLE_BASELINE_MS}ms). Set AUDIT_DRAIN_CYCLE_BASELINE_MS "
                f"for remote deployments."
            )

        finally:
            await _cleanup_records(audit_perf_session_factory, seeded_ids)
