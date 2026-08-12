"""Mixed Read/Write Workload & Contention Testing (AAP-79806).

Tests realistic mixed workloads: concurrent audit writes, outbox worker
drains, and normal API database queries operating across separate
connection pools.  Measures cross-impact between audit operations and
main application database performance.

Background:
    After AAP-79901 (#212), the audit outbox worker uses a **dedicated
    connection pool** (``audit_worker_pool_size=5``, ``max_overflow=2``,
    max 7 connections) isolated from the main application pool
    (``pool_size=10``, ``max_overflow=20``, max 30 connections).

    The contention model is:
        - **Main pool**: business reads/writes + CRUD trigger audit inserts
          (synchronous, same transaction as the business operation)
        - **Worker pool**: async fire-and-forget audit writes + drain worker
          ``SELECT ... FOR UPDATE SKIP LOCKED`` + DELETE cycles

    Both pools hit the same PostgreSQL instance and the same
    ``audit_outbox`` table, so row-level lock contention still occurs
    even though connection-pool contention is eliminated.

Acceptance criteria:
    - Mixed workload simulated with concurrent audit writes + drain + business queries
    - Business transaction latency impact measured (p95 overhead from audit)
    - Row-level lock contention tested on ``audit_outbox``
    - Audit isolation from normal DB operations validated
    - Graceful degradation tested at 3 traffic multipliers (2x, 5x, 10x)
    - Advisory lock overhead measured
    - Maximum safe concurrent load documented
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID, uuid4

import pytest
import structlog
from sqlalchemy import text

from syntara.audit.outbox.models import AuditEventSource, AuditOutboxRecord
from tests.integration.audit.conftest import (
    DELETE_OUTBOX_BY_IDS_SQL,
    DRAIN_SELECT_IDS_SQL,
    MAX_TEST_DB_CONNECTIONS,
    cleanup_outbox_records,
    make_audit_event,
)
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

# Base workload sizes (1x normal traffic)
BASE_AUDIT_WRITES = int(os.environ.get("AUDIT_PERF_BASE_AUDIT_WRITES", "20"))
BASE_DRAIN_CYCLES = int(os.environ.get("AUDIT_PERF_BASE_DRAIN_CYCLES", "10"))
BASE_BUSINESS_QUERIES = int(os.environ.get("AUDIT_PERF_BASE_BUSINESS_QUERIES", "30"))
DRAIN_BATCH_SIZE = int(os.environ.get("AUDIT_PERF_DRAIN_BATCH_SIZE", "100"))

_DRAIN_SELECT_SQL = DRAIN_SELECT_IDS_SQL
_DELETE_OUTBOX_RECORDS_BY_IDS = DELETE_OUTBOX_BY_IDS_SQL


async def _drain_and_delete(
    session: AsyncSession,
    latency: LatencyResult,
    batch_size: int = DRAIN_BATCH_SIZE,
) -> None:
    """Execute a drain SELECT + DELETE cycle, recording latency."""
    async with measure_latency_async(latency):
        result = await session.execute(
            _DRAIN_SELECT_SQL,
            {"batch": batch_size},
        )
        rows = result.fetchall()
        if rows:
            row_ids = [r[0] for r in rows]
            await session.execute(_DELETE_OUTBOX_RECORDS_BY_IDS, {"ids": row_ids})
        await session.commit()


async def _measure_serial_baseline(
    session_factory: async_sessionmaker[AsyncSession],
    label: str = "business_baseline",
    iterations: int = 30,
) -> LatencyResult:
    """Measure serial business-query latency with no contention."""
    baseline = LatencyResult(label=label)
    for _ in range(iterations):
        async with session_factory() as session, measure_latency_async(baseline):
            await session.execute(text("SELECT 1"))
    return baseline


# ---------------------------------------------------------------------------
# AC: Mixed workload simulated with concurrent audit writes + drain + business queries
# AC: Business transaction latency impact measured (p95 overhead from audit)
# ---------------------------------------------------------------------------


class TestMixedWorkloadSimulation:
    """Simulate concurrent audit writes, drain cycles, and business queries.

    Uses separate session factories for business operations (main pool)
    and audit worker operations (worker pool) to match the production
    architecture after AAP-79901 (#212).
    """

    async def test_mixed_workload_three_roles(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
        audit_worker_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Run concurrent audit writes, drain SELECTs, and business queries.

        Audit writes and drain cycles use the worker pool session factory.
        Business queries use the main pool session factory.
        """
        sem = asyncio.Semaphore(MAX_TEST_DB_CONNECTIONS)
        audit_latency = LatencyResult(label="audit_write")
        drain_latency = LatencyResult(label="drain_cycle")
        business_latency = LatencyResult(label="business_query")
        inserted_ids: list[UUID] = []
        report = PerformanceReport(
            title="mixed_workload_three_roles",
            metadata={
                "audit_writes": BASE_AUDIT_WRITES,
                "drain_cycles": BASE_DRAIN_CYCLES,
                "business_queries": BASE_BUSINESS_QUERIES,
                "pool_model": "separate (main + worker)",
            },
        )

        async def audit_write() -> None:
            event = make_audit_event(benchmark="mixed_workload")
            async with sem, audit_worker_perf_session_factory() as session:
                record = AuditOutboxRecord(
                    event_source=AuditEventSource.BUSINESS_EVENT,
                    event_payload=event.model_dump(mode="json"),
                )
                async with measure_latency_async(audit_latency):
                    session.add(record)
                    await session.commit()
                inserted_ids.append(record.id)

        async def drain_cycle() -> None:
            async with sem, audit_worker_perf_session_factory() as session:
                await _drain_and_delete(session, drain_latency)

        async def business_query() -> None:
            async with sem, audit_perf_session_factory() as session, measure_latency_async(business_latency):
                await session.execute(text("SELECT 1"))

        try:
            seed_result = await seed_audit_outbox(
                audit_worker_perf_session_factory,
                row_count=BASE_DRAIN_CYCLES * DRAIN_BATCH_SIZE,
                track_ids=True,
            )
            inserted_ids.extend(seed_result.record_ids)

            audit_tasks = [asyncio.create_task(audit_write()) for _ in range(BASE_AUDIT_WRITES)]
            drain_tasks = [asyncio.create_task(drain_cycle()) for _ in range(BASE_DRAIN_CYCLES)]
            business_tasks = [asyncio.create_task(business_query()) for _ in range(BASE_BUSINESS_QUERIES)]

            start = time.monotonic()
            await asyncio.gather(*audit_tasks, *drain_tasks, *business_tasks)
            elapsed = time.monotonic() - start

            report.add_latency(audit_latency)
            report.add_latency(drain_latency)
            report.add_latency(business_latency)
            report.metadata["elapsed_s"] = round(elapsed, 3)
            report.log_all()

            logger.info(
                "mixed_workload_results",
                elapsed_s=round(elapsed, 3),
                audit_p95_ms=round(audit_latency.p95, 3),
                drain_p95_ms=round(drain_latency.p95, 3),
                business_p95_ms=round(business_latency.p95, 3),
                audit_count=audit_latency.count,
                drain_count=drain_latency.count,
                business_count=business_latency.count,
            )

            assert audit_latency.count == BASE_AUDIT_WRITES
            assert business_latency.count == BASE_BUSINESS_QUERIES

        finally:
            await cleanup_outbox_records(audit_worker_perf_session_factory, inserted_ids)

    async def test_business_latency_impact_from_audit(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
        audit_worker_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Measure p95 business query overhead caused by concurrent audit operations.

        Runs business queries in isolation (baseline), then with concurrent
        audit writes + drain on the worker pool to quantify the impact on
        the main pool.
        """
        sem = asyncio.Semaphore(MAX_TEST_DB_CONNECTIONS)
        query_count = 50
        inserted_ids: list[UUID] = []

        baseline = await _measure_serial_baseline(audit_perf_session_factory, iterations=query_count)

        under_load = LatencyResult(label="business_under_audit_load")
        audit_latency = LatencyResult(label="concurrent_audit_writes")

        async def audit_write() -> None:
            event = make_audit_event(benchmark="mixed_workload")
            async with sem, audit_worker_perf_session_factory() as session:
                record = AuditOutboxRecord(
                    event_source=AuditEventSource.BUSINESS_EVENT,
                    event_payload=event.model_dump(mode="json"),
                )
                async with measure_latency_async(audit_latency):
                    session.add(record)
                    await session.commit()
                inserted_ids.append(record.id)

        async def business_query() -> None:
            async with sem, audit_perf_session_factory() as session, measure_latency_async(under_load):
                await session.execute(text("SELECT 1"))

        try:
            audit_tasks = [asyncio.create_task(audit_write()) for _ in range(BASE_AUDIT_WRITES)]
            business_tasks = [asyncio.create_task(business_query()) for _ in range(query_count)]
            await asyncio.gather(*audit_tasks, *business_tasks)

            overhead_ms = under_load.p95 - baseline.p95
            overhead_pct = (overhead_ms / baseline.p95 * 100) if baseline.p95 > 0 else 0

            baseline.log()
            under_load.log()

            logger.info(
                "business_latency_impact",
                baseline_p95_ms=round(baseline.p95, 3),
                under_load_p95_ms=round(under_load.p95, 3),
                overhead_ms=round(overhead_ms, 3),
                overhead_pct=round(overhead_pct, 1),
                baseline_p50_ms=round(baseline.p50, 3),
                under_load_p50_ms=round(under_load.p50, 3),
            )

        finally:
            await cleanup_outbox_records(audit_worker_perf_session_factory, inserted_ids)


# ---------------------------------------------------------------------------
# AC: Row-level lock contention tested on audit_outbox
# ---------------------------------------------------------------------------


class TestRowLevelLockContention:
    """Test FOR UPDATE SKIP LOCKED contention between concurrent drain workers.

    All drain operations use the worker pool session factory.
    """

    async def test_concurrent_drain_workers_skip_locked(
        self,
        audit_worker_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Verify multiple drain workers don't process the same rows.

        Seeds rows, then fires N concurrent drain SELECTs with
        FOR UPDATE SKIP LOCKED.  Each drain locks its batch; subsequent
        drains skip those rows.  Total processed rows across all drains
        should not exceed total seeded.
        """
        seed_count = 200
        concurrent_drains = 5
        sem = asyncio.Semaphore(MAX_TEST_DB_CONNECTIONS)
        drain_latency = LatencyResult(label="concurrent_drain_skip_locked")
        rows_per_drain: list[int] = []
        lock = asyncio.Lock()

        seed_result = await seed_audit_outbox(
            audit_worker_perf_session_factory,
            row_count=seed_count,
            track_ids=True,
        )
        all_ids = list(seed_result.record_ids)

        seeded_id_set = set(all_ids)

        async def drain_and_count() -> None:
            async with sem, audit_worker_perf_session_factory() as session:
                async with measure_latency_async(drain_latency):
                    result = await session.execute(
                        _DRAIN_SELECT_SQL,
                        {"batch": DRAIN_BATCH_SIZE},
                    )
                    rows = result.fetchall()
                seeded_rows = [r for r in rows if r[0] in seeded_id_set]
                async with lock:
                    rows_per_drain.append(len(seeded_rows))
                # Hold the row-lock briefly to force contention for other drains
                await asyncio.sleep(0.05)
                await session.rollback()

        try:
            tasks = [asyncio.create_task(drain_and_count()) for _ in range(concurrent_drains)]
            await asyncio.gather(*tasks)

            total_rows_seen = sum(rows_per_drain)
            drain_latency.log()

            logger.info(
                "concurrent_drain_skip_locked",
                seed_count=seed_count,
                concurrent_drains=concurrent_drains,
                rows_per_drain=rows_per_drain,
                total_rows_seen=total_rows_seen,
                drain_p95_ms=round(drain_latency.p95, 3),
            )

            assert total_rows_seen <= seed_count, (
                f"Drains processed {total_rows_seen} seeded rows total, but only {seed_count} were seeded — "
                f"SKIP LOCKED may not be working correctly"
            )

        finally:
            await cleanup_outbox_records(audit_worker_perf_session_factory, all_ids)

    async def test_writer_drain_contention(
        self,
        audit_worker_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Measure contention when writers and drainers operate concurrently.

        Both writers and drainers use the worker pool (matching production
        where async writes and drain cycles share the worker pool).
        The drain's FOR UPDATE SKIP LOCKED should not block writers
        (they insert new rows, not update locked ones).
        """
        sem = asyncio.Semaphore(MAX_TEST_DB_CONNECTIONS)
        write_latency = LatencyResult(label="write_during_drain")
        drain_latency = LatencyResult(label="drain_during_write")
        inserted_ids: list[UUID] = []
        write_count = 30
        drain_count = 10

        seed_result = await seed_audit_outbox(
            audit_worker_perf_session_factory,
            row_count=drain_count * DRAIN_BATCH_SIZE,
            track_ids=True,
        )
        inserted_ids.extend(seed_result.record_ids)

        async def write_record() -> None:
            event = make_audit_event(benchmark="mixed_workload")
            async with sem, audit_worker_perf_session_factory() as session:
                record = AuditOutboxRecord(
                    event_source=AuditEventSource.BUSINESS_EVENT,
                    event_payload=event.model_dump(mode="json"),
                )
                async with measure_latency_async(write_latency):
                    session.add(record)
                    await session.commit()
                inserted_ids.append(record.id)

        async def drain_rows() -> None:
            async with sem, audit_worker_perf_session_factory() as session:
                await _drain_and_delete(session, drain_latency)

        try:
            write_tasks = [asyncio.create_task(write_record()) for _ in range(write_count)]
            drain_tasks = [asyncio.create_task(drain_rows()) for _ in range(drain_count)]
            await asyncio.gather(*write_tasks, *drain_tasks)

            write_latency.log()
            drain_latency.log()

            logger.info(
                "writer_drain_contention",
                write_p95_ms=round(write_latency.p95, 3),
                drain_p95_ms=round(drain_latency.p95, 3),
                write_count=write_latency.count,
                drain_count=drain_latency.count,
            )

            assert write_latency.count == write_count
            assert drain_latency.count == drain_count

        finally:
            await cleanup_outbox_records(audit_worker_perf_session_factory, inserted_ids)


# ---------------------------------------------------------------------------
# AC: Audit isolation from normal DB operations validated
# ---------------------------------------------------------------------------


class TestAuditIsolation:
    """Validate that audit operations don't block normal application DB operations.

    Uses separate session factories: business reads/writes on the main pool,
    audit writes and drain on the worker pool.
    """

    async def test_audit_writes_do_not_block_business_reads(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
        audit_worker_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Fire concurrent audit writes (worker pool) while running business reads (main pool).

        With separate pools, audit writes cannot exhaust the main pool's
        connections.  Business reads should complete without contention.
        """
        sem = asyncio.Semaphore(MAX_TEST_DB_CONNECTIONS)
        business_latency = LatencyResult(label="business_reads_during_audit")
        audit_latency = LatencyResult(label="audit_writes_during_business")
        inserted_ids: list[UUID] = []

        baseline = await _measure_serial_baseline(
            audit_perf_session_factory,
            label="business_reads_baseline",
        )

        async def audit_write() -> None:
            event = make_audit_event(benchmark="mixed_workload")
            async with sem, audit_worker_perf_session_factory() as session:
                record = AuditOutboxRecord(
                    event_source=AuditEventSource.BUSINESS_EVENT,
                    event_payload=event.model_dump(mode="json"),
                )
                async with measure_latency_async(audit_latency):
                    session.add(record)
                    await session.commit()
                inserted_ids.append(record.id)

        async def business_read() -> None:
            async with sem, audit_perf_session_factory() as session, measure_latency_async(business_latency):
                await session.execute(text("SELECT 1"))

        try:
            audit_tasks = [asyncio.create_task(audit_write()) for _ in range(30)]
            read_tasks = [asyncio.create_task(business_read()) for _ in range(30)]
            await asyncio.gather(*audit_tasks, *read_tasks)

            baseline.log()
            business_latency.log()

            logger.info(
                "audit_write_isolation",
                baseline_p95_ms=round(baseline.p95, 3),
                concurrent_p95_ms=round(business_latency.p95, 3),
                audit_p95_ms=round(audit_latency.p95, 3),
            )

        finally:
            await cleanup_outbox_records(audit_worker_perf_session_factory, inserted_ids)

    async def test_audit_drain_does_not_block_business_writes(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
        audit_worker_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Fire concurrent drain SELECTs (worker pool) while running business writes (main pool).

        Drain's FOR UPDATE SKIP LOCKED on ``audit_outbox`` uses the worker
        pool while business writes use the main pool.  The separate pools
        plus PostgreSQL MVCC ensure no cross-workload blocking.
        """
        sem = asyncio.Semaphore(MAX_TEST_DB_CONNECTIONS)
        business_write_latency = LatencyResult(label="business_writes_during_drain")
        drain_latency = LatencyResult(label="drain_during_business_writes")
        inserted_ids: list[UUID] = []

        seed_result = await seed_audit_outbox(
            audit_worker_perf_session_factory,
            row_count=500,
            track_ids=True,
        )
        inserted_ids.extend(seed_result.record_ids)

        async def drain_and_hold() -> None:
            """Drain with a brief hold to force row-lock contention window."""
            async with sem, audit_worker_perf_session_factory() as session, measure_latency_async(drain_latency):
                await session.execute(
                    _DRAIN_SELECT_SQL,
                    {"batch": DRAIN_BATCH_SIZE},
                )
                await asyncio.sleep(0.05)

        async def business_write() -> None:
            """Simulate a business-table write via the main pool."""
            async with sem, audit_perf_session_factory() as session:
                record_id = uuid4()
                async with measure_latency_async(business_write_latency):
                    await session.execute(
                        text(
                            "INSERT INTO audit_outbox (id, created_at, event_source, event_payload) "
                            "VALUES (CAST(:id AS uuid), now(), "
                            "'business_event'::auditeventsource, "
                            '\'{"event_id": "test"}\'::jsonb)'
                        ),
                        {"id": record_id},
                    )
                    await session.commit()
                inserted_ids.append(record_id)

        try:
            drain_tasks = [asyncio.create_task(drain_and_hold()) for _ in range(10)]
            write_tasks = [asyncio.create_task(business_write()) for _ in range(20)]
            await asyncio.gather(*drain_tasks, *write_tasks)

            business_write_latency.log()
            drain_latency.log()

            logger.info(
                "drain_isolation_from_business_writes",
                business_write_p95_ms=round(business_write_latency.p95, 3),
                drain_p95_ms=round(drain_latency.p95, 3),
                business_count=business_write_latency.count,
                drain_count=drain_latency.count,
            )

            assert business_write_latency.count == 20
            assert drain_latency.count == 10

        finally:
            await cleanup_outbox_records(audit_worker_perf_session_factory, inserted_ids)


# ---------------------------------------------------------------------------
# AC: Graceful degradation tested at 3 traffic multipliers (2x, 5x, 10x)
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Test system behavior under increasing traffic multipliers."""

    @pytest.mark.parametrize("multiplier", [2, 5, 10])
    async def test_graceful_degradation_at_traffic_multiplier(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
        audit_worker_perf_session_factory: async_sessionmaker[AsyncSession],
        multiplier: int,
    ) -> None:
        """Scale workload by multiplier and measure latency degradation.

        Audit writes and drain cycles use the worker pool; business queries
        use the main pool.
        """
        sem = asyncio.Semaphore(MAX_TEST_DB_CONNECTIONS)
        audit_writes = BASE_AUDIT_WRITES * multiplier
        drain_cycles = BASE_DRAIN_CYCLES * multiplier
        business_queries = BASE_BUSINESS_QUERIES * multiplier

        audit_latency = LatencyResult(label=f"audit_write_{multiplier}x")
        drain_latency = LatencyResult(label=f"drain_cycle_{multiplier}x")
        business_latency = LatencyResult(label=f"business_query_{multiplier}x")
        inserted_ids: list[UUID] = []

        report = PerformanceReport(
            title=f"graceful_degradation_{multiplier}x",
            metadata={
                "multiplier": multiplier,
                "audit_writes": audit_writes,
                "drain_cycles": drain_cycles,
                "business_queries": business_queries,
                "pool_model": "separate (main + worker)",
            },
        )

        async def audit_write() -> None:
            event = make_audit_event(benchmark="mixed_workload")
            async with sem, audit_worker_perf_session_factory() as session:
                record = AuditOutboxRecord(
                    event_source=AuditEventSource.BUSINESS_EVENT,
                    event_payload=event.model_dump(mode="json"),
                )
                async with measure_latency_async(audit_latency):
                    session.add(record)
                    await session.commit()
                inserted_ids.append(record.id)

        async def drain_cycle() -> None:
            async with sem, audit_worker_perf_session_factory() as session:
                await _drain_and_delete(session, drain_latency)

        async def business_query() -> None:
            async with sem, audit_perf_session_factory() as session, measure_latency_async(business_latency):
                await session.execute(text("SELECT 1"))

        try:
            seed_result = await seed_audit_outbox(
                audit_worker_perf_session_factory,
                row_count=drain_cycles * DRAIN_BATCH_SIZE,
                track_ids=True,
            )
            inserted_ids.extend(seed_result.record_ids)

            start = time.monotonic()
            all_tasks = (
                [asyncio.create_task(audit_write()) for _ in range(audit_writes)]
                + [asyncio.create_task(drain_cycle()) for _ in range(drain_cycles)]
                + [asyncio.create_task(business_query()) for _ in range(business_queries)]
            )
            await asyncio.gather(*all_tasks)
            elapsed = time.monotonic() - start

            total_ops = audit_writes + drain_cycles + business_queries
            throughput = ThroughputResult(
                label=f"mixed_{multiplier}x",
                total_operations=total_ops,
                elapsed_seconds=elapsed,
            )

            report.add_latency(audit_latency)
            report.add_latency(drain_latency)
            report.add_latency(business_latency)
            report.add_throughput(throughput)
            report.log_all()

            logger.info(
                "graceful_degradation",
                multiplier=multiplier,
                elapsed_s=round(elapsed, 3),
                ops_per_sec=round(throughput.ops_per_second, 1),
                audit_p95_ms=round(audit_latency.p95, 3),
                drain_p95_ms=round(drain_latency.p95, 3),
                business_p95_ms=round(business_latency.p95, 3),
            )

        finally:
            await cleanup_outbox_records(audit_worker_perf_session_factory, inserted_ids)


# ---------------------------------------------------------------------------
# AC: Advisory lock overhead measured
# ---------------------------------------------------------------------------


class TestAdvisoryLockOverhead:
    """Measure the latency overhead of PostgreSQL advisory locks.

    Advisory locks are used by the worker pool for cross-instance
    coordination, so we measure on the worker session factory.
    """

    async def test_advisory_lock_acquisition_latency(
        self,
        audit_worker_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Measure pg_try_advisory_xact_lock acquisition latency.

        Serial acquisition of an uncontested advisory lock to establish
        baseline overhead.  The lock auto-releases on transaction end
        (ROLLBACK via session context manager exit).
        """
        lock_key = int.from_bytes(
            hashlib.sha256(b"perf-test-advisory-lock").digest()[:8],
            "big",
            signed=True,
        )
        iterations = 100

        with_lock = LatencyResult(label="with_advisory_lock")
        without_lock = LatencyResult(label="without_advisory_lock")

        for _ in range(iterations):
            async with audit_worker_perf_session_factory() as session, measure_latency_async(with_lock):
                conn = await session.connection()
                result = await conn.execute(
                    text("SELECT pg_try_advisory_xact_lock(:key)"),
                    {"key": lock_key},
                )
                result.scalar()

        for _ in range(iterations):
            async with audit_worker_perf_session_factory() as session, measure_latency_async(without_lock):
                await session.execute(text("SELECT 1"))

        with_lock.log()
        without_lock.log()

        overhead_ms = with_lock.p50 - without_lock.p50
        overhead_pct = (overhead_ms / without_lock.p50 * 100) if without_lock.p50 > 0 else 0

        logger.info(
            "advisory_lock_overhead",
            with_lock_p50_ms=round(with_lock.p50, 3),
            without_lock_p50_ms=round(without_lock.p50, 3),
            overhead_ms=round(overhead_ms, 3),
            overhead_pct=round(overhead_pct, 1),
            with_lock_p95_ms=round(with_lock.p95, 3),
            without_lock_p95_ms=round(without_lock.p95, 3),
        )

    async def test_advisory_lock_contention_multiple_workers(
        self,
        audit_worker_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Measure advisory lock contention when multiple workers compete.

        Simulates N concurrent workers all attempting to acquire the same
        advisory lock.  Only one should succeed per round; the rest should
        see ``pg_try_advisory_xact_lock`` return ``false`` immediately
        (non-blocking).
        """
        lock_key = int.from_bytes(
            hashlib.sha256(b"audit-outbox-worker").digest()[:8],
            "big",
            signed=True,
        )
        sem = asyncio.Semaphore(MAX_TEST_DB_CONNECTIONS)
        worker_count = 10
        rounds = 5
        acquire_latency = LatencyResult(label="advisory_lock_contention")
        total_acquisitions = 0
        total_skips = 0
        results_lock = asyncio.Lock()

        report = PerformanceReport(
            title="advisory_lock_contention",
            metadata={"worker_count": worker_count, "rounds": rounds},
        )

        async def try_acquire_lock() -> None:
            nonlocal total_acquisitions, total_skips
            async with (
                sem,
                audit_worker_perf_session_factory() as session,
                measure_latency_async(acquire_latency),
            ):
                conn = await session.connection()
                result = await conn.execute(
                    text("SELECT pg_try_advisory_xact_lock(:key)"),
                    {"key": lock_key},
                )
                acquired = bool(result.scalar())
            async with results_lock:
                if acquired:
                    total_acquisitions += 1
                else:
                    total_skips += 1

        for _ in range(rounds):
            tasks = [asyncio.create_task(try_acquire_lock()) for _ in range(worker_count)]
            await asyncio.gather(*tasks)

        report.add_latency(acquire_latency)
        report.log_all()

        logger.info(
            "advisory_lock_contention_result",
            worker_count=worker_count,
            rounds=rounds,
            total_attempts=worker_count * rounds,
            total_acquisitions=total_acquisitions,
            total_skips=total_skips,
            acquire_p95_ms=round(acquire_latency.p95, 3),
        )

        assert total_acquisitions >= rounds, (
            f"Expected at least {rounds} acquisitions (one per round), got {total_acquisitions}"
        )
        assert total_acquisitions + total_skips == worker_count * rounds


# ---------------------------------------------------------------------------
# AC: Maximum safe concurrent load documented
# ---------------------------------------------------------------------------


class TestMaxSafeConcurrentLoad:
    """Find the maximum concurrent audit load before business query impact."""

    async def _run_load_level(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
        audit_worker_perf_session_factory: async_sessionmaker[AsyncSession],
        sem: asyncio.Semaphore,
        level: int,
    ) -> tuple[LatencyResult, LatencyResult, list[UUID]]:
        """Run a single load level and return (business_latency, audit_latency, ids)."""
        business_latency = LatencyResult(label=f"business_at_audit_c{level}")
        audit_latency = LatencyResult(label=f"audit_c{level}")
        level_ids: list[UUID] = []

        drain_count = max(level // 4, 1)
        seed_result = await seed_audit_outbox(
            audit_worker_perf_session_factory,
            row_count=drain_count * DRAIN_BATCH_SIZE,
            track_ids=True,
        )
        level_ids.extend(seed_result.record_ids)

        async def audit_write(
            lat: LatencyResult = audit_latency,
            ids: list[UUID] = level_ids,
        ) -> None:
            event = make_audit_event(benchmark="mixed_workload")
            async with sem, audit_worker_perf_session_factory() as session:
                record = AuditOutboxRecord(
                    event_source=AuditEventSource.BUSINESS_EVENT,
                    event_payload=event.model_dump(mode="json"),
                )
                async with measure_latency_async(lat):
                    session.add(record)
                    await session.commit()
                ids.append(record.id)

        async def drain_cycle() -> None:
            async with sem, audit_worker_perf_session_factory() as session:
                result = await session.execute(
                    _DRAIN_SELECT_SQL,
                    {"batch": DRAIN_BATCH_SIZE},
                )
                rows = result.fetchall()
                if rows:
                    row_ids = [r[0] for r in rows]
                    await session.execute(_DELETE_OUTBOX_RECORDS_BY_IDS, {"ids": row_ids})
                await session.commit()

        async def business_query(lat: LatencyResult = business_latency) -> None:
            async with sem, audit_perf_session_factory() as session, measure_latency_async(lat):
                await session.execute(text("SELECT 1"))

        business_count = 20
        audit_tasks = [asyncio.create_task(audit_write()) for _ in range(level)]
        drain_tasks = [asyncio.create_task(drain_cycle()) for _ in range(drain_count)]
        business_tasks = [asyncio.create_task(business_query()) for _ in range(business_count)]
        await asyncio.gather(*audit_tasks, *drain_tasks, *business_tasks)

        return business_latency, audit_latency, level_ids

    async def test_find_max_safe_concurrent_load(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
        audit_worker_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Ramp up concurrent audit operations to find the inflection point.

        Audit operations use the worker pool; business queries use the main
        pool.  The max safe load is the highest level where business p95
        stays below 2x the baseline.
        """
        sem = asyncio.Semaphore(MAX_TEST_DB_CONNECTIONS)
        inserted_ids: list[UUID] = []

        report = PerformanceReport(
            title="max_safe_concurrent_load",
            metadata={
                "max_db_connections": MAX_TEST_DB_CONNECTIONS,
                "pool_model": "separate (main + worker)",
            },
        )

        baseline = await _measure_serial_baseline(audit_perf_session_factory)

        max_safe_level = 0
        test_levels = [5, 10, 20, 40, 60, 80, 100]

        for level in test_levels:
            business_latency, audit_latency, level_ids = await self._run_load_level(
                audit_perf_session_factory,
                audit_worker_perf_session_factory,
                sem,
                level,
            )

            report.add_latency(business_latency)
            report.add_latency(audit_latency)

            ratio = business_latency.p95 / baseline.p95 if baseline.p95 > 0 else 0

            logger.info(
                "max_safe_load_level",
                audit_concurrency=level,
                business_p95_ms=round(business_latency.p95, 3),
                baseline_p95_ms=round(baseline.p95, 3),
                ratio=round(ratio, 2),
                audit_p95_ms=round(audit_latency.p95, 3),
            )

            if ratio < 2.0:
                max_safe_level = level

            inserted_ids.extend(level_ids)

        report.metadata["max_safe_concurrent_audit_load"] = max_safe_level
        report.metadata["baseline_p95_ms"] = round(baseline.p95, 3)
        report.log_all()

        logger.info(
            "max_safe_concurrent_load_result",
            max_safe_level=max_safe_level,
            tested_levels=test_levels,
            baseline_p95_ms=round(baseline.p95, 3),
            threshold="2x baseline p95",
        )

        await cleanup_outbox_records(audit_worker_perf_session_factory, inserted_ids)


# ---------------------------------------------------------------------------
# Optimal poll_interval x batch_size sweep
# ---------------------------------------------------------------------------


class TestOptimalWorkerConfig:
    """Sweep poll_interval x batch_size to find optimal defaults.

    Simulates the drain worker at various (poll_interval, batch_size)
    combinations while measuring business query p95 impact on the
    main pool.  Reports the combination with the lowest business
    latency impact and highest drain throughput.
    """

    _POLL_INTERVALS: ClassVar[list[float]] = [1.0, 3.0, 5.0, 10.0]
    _BATCH_SIZES: ClassVar[list[int]] = [50, 100, 250, 500]

    async def _run_sweep_config(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
        audit_worker_perf_session_factory: async_sessionmaker[AsyncSession],
        sem: asyncio.Semaphore,
        poll_interval: float,
        batch_size: int,
        seed_rows: int,
        duration_cycles: int,
    ) -> tuple[LatencyResult, LatencyResult, int, list[UUID]]:
        """Run one (poll_interval, batch_size) config and return metrics.

        Returns (business_latency, drain_latency, rows_drained, inserted_ids).
        """
        business_latency = LatencyResult(label=f"business_pi{poll_interval}_bs{batch_size}")
        drain_latency = LatencyResult(label=f"drain_pi{poll_interval}_bs{batch_size}")
        inserted_ids: list[UUID] = []
        total_drained = 0
        drain_lock = asyncio.Lock()

        seed_result = await seed_audit_outbox(
            audit_worker_perf_session_factory,
            row_count=seed_rows,
            track_ids=True,
        )
        inserted_ids.extend(seed_result.record_ids)

        async def drain_cycle() -> None:
            nonlocal total_drained
            await asyncio.sleep(poll_interval)
            async with sem, audit_worker_perf_session_factory() as session:
                async with measure_latency_async(drain_latency):
                    result = await session.execute(
                        _DRAIN_SELECT_SQL,
                        {"batch": batch_size},
                    )
                    rows = result.fetchall()
                    if rows:
                        row_ids = [r[0] for r in rows]
                        await session.execute(_DELETE_OUTBOX_RECORDS_BY_IDS, {"ids": row_ids})
                    await session.commit()
                async with drain_lock:
                    total_drained += len(rows)

        async def business_query() -> None:
            async with sem, audit_perf_session_factory() as session, measure_latency_async(business_latency):
                await session.execute(text("SELECT 1"))

        drain_tasks = [asyncio.create_task(drain_cycle()) for _ in range(duration_cycles)]
        business_tasks = [asyncio.create_task(business_query()) for _ in range(20)]
        await asyncio.gather(*drain_tasks, *business_tasks)

        return business_latency, drain_latency, total_drained, inserted_ids

    async def test_poll_interval_batch_size_sweep(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
        audit_worker_perf_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Sweep poll_interval x batch_size and report optimal combination.

        For each configuration, seeds rows, runs drain cycles at the given
        poll interval with the given batch size, and measures business
        query p95 on the main pool.
        """
        sem = asyncio.Semaphore(MAX_TEST_DB_CONNECTIONS)
        all_inserted_ids: list[UUID] = []
        seed_rows = 1000
        duration_cycles = 5

        baseline = await _measure_serial_baseline(audit_perf_session_factory)

        report = PerformanceReport(
            title="poll_interval_batch_size_sweep",
            metadata={
                "poll_intervals": self._POLL_INTERVALS,
                "batch_sizes": self._BATCH_SIZES,
                "seed_rows": seed_rows,
                "baseline_p95_ms": round(baseline.p95, 3),
            },
        )

        best_config: dict[str, object] = {}
        best_ratio: float = float("inf")

        for poll_interval in self._POLL_INTERVALS:
            for batch_size in self._BATCH_SIZES:
                business_lat, drain_lat, rows_drained, ids = await self._run_sweep_config(
                    audit_perf_session_factory,
                    audit_worker_perf_session_factory,
                    sem,
                    poll_interval=poll_interval,
                    batch_size=batch_size,
                    seed_rows=seed_rows,
                    duration_cycles=duration_cycles,
                )
                all_inserted_ids.extend(ids)

                report.add_latency(business_lat)
                report.add_latency(drain_lat)

                ratio = business_lat.p95 / baseline.p95 if baseline.p95 > 0 else 0

                logger.info(
                    "sweep_config_result",
                    poll_interval=poll_interval,
                    batch_size=batch_size,
                    business_p95_ms=round(business_lat.p95, 3),
                    drain_p95_ms=round(drain_lat.p95, 3),
                    rows_drained=rows_drained,
                    ratio_vs_baseline=round(ratio, 2),
                )

                if ratio < best_ratio:
                    best_ratio = ratio
                    best_config = {
                        "poll_interval": poll_interval,
                        "batch_size": batch_size,
                        "business_p95_ms": round(business_lat.p95, 3),
                        "drain_p95_ms": round(drain_lat.p95, 3),
                        "rows_drained": rows_drained,
                        "ratio_vs_baseline": round(ratio, 2),
                    }

        report.metadata["best_config"] = best_config
        report.log_all()

        logger.info(
            "optimal_worker_config",
            best_poll_interval=best_config.get("poll_interval"),
            best_batch_size=best_config.get("batch_size"),
            best_business_p95_ms=best_config.get("business_p95_ms"),
            best_ratio=best_config.get("ratio_vs_baseline"),
        )

        await cleanup_outbox_records(audit_worker_perf_session_factory, all_inserted_ids)
