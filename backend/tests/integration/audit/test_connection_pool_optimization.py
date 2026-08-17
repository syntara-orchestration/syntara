"""Connection Pool Optimization — Pool Sizing, Isolation, and Semaphore Tuning.

Evaluates connection pool optimization strategies for the audit subsystem:

1. **Pool size adjustments** — Tests various pool sizes under audit-heavy
   workloads to find the optimal balance between connection availability
   and PostgreSQL resource consumption.

2. **Separate pool for audit operations** — Compares shared vs. dedicated
   connection pools for audit writes, measuring cross-workload isolation
   and business query impact.

3. **Semaphore tuning** — Evaluates audit_writer_max_concurrent_writes
   settings to find the optimal concurrency limit that maximizes throughput
   without exhausting the connection pool.

Background:
    The Syntara audit subsystem uses two connection pools:
    - Main pool (pool_size=10, max_overflow=20): API requests + CRUD trigger writes
    - Worker pool (pool_size=5, max_overflow=2): Drain SELECT/DELETE + async writes

    The semaphore (audit_writer_max_concurrent_writes=100) limits concurrent
    async writes but doesn't directly map to pool connections — writes may
    queue at the pool checkout level.

Acceptance criteria:
    - Pool size recommendations with supporting data
    - Separate pool vs. shared pool evaluated
    - Semaphore tuning recommendations with supporting data
    - Each recommendation documented with expected improvement and trade-offs
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from syntara.audit.outbox.models import AuditEventSource, AuditOutboxRecord
from tests.integration.audit.conftest import (
    DELETE_OUTBOX_BY_IDS_SQL,
    INSERT_OUTBOX_RECORD_SQL,
    MAX_TEST_DB_CONNECTIONS,
    cleanup_outbox_records,
    create_pooled_engine,
    make_audit_event,
)
from tests.integration.audit.metrics import (
    LatencyResult,
    PerformanceReport,
    ThroughputResult,
    measure_latency_async,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)

POOL_SIZES = [3, 5, 10, 15, 20]

SEMAPHORE_LIMITS = [5, 10, 20, 50, 100]
# Simulated DB hold time per operation for contention tests.
AUDIT_OP_DELAY_SECONDS = 0.02
APP_TX_DELAY_SECONDS = 0.02

INSERT_OUTBOX_RECORD = INSERT_OUTBOX_RECORD_SQL
DELETE_OUTBOX_RECORDS_BY_IDS = DELETE_OUTBOX_BY_IDS_SQL


# ---------------------------------------------------------------------------
# AC: Pool size recommendations with supporting data
# ---------------------------------------------------------------------------


class TestPoolSizeOptimization:
    """Evaluate pool size impact on audit write throughput and business query latency.

    Tests various pool sizes to find the optimal configuration for the
    audit workload.  Larger pools support more concurrent operations but
    consume more PostgreSQL connections (max_connections is a shared resource).
    """

    @pytest.mark.parametrize("pool_size", POOL_SIZES)
    async def test_audit_throughput_at_pool_size(
        self,
        audit_perf_db_url: str,
        pool_size: int,
    ) -> None:
        """Measure audit write throughput at each pool size.

        Creates a dedicated engine with the given pool size and fires
        concurrent audit writes to measure sustained throughput.
        """
        max_overflow = max(pool_size, 5)
        engine = create_pooled_engine(audit_perf_db_url, pool_size=pool_size, max_overflow=max_overflow)
        latency = LatencyResult(label=f"audit_write_pool_{pool_size}")
        total_writes = pool_size * 10
        inserted_ids: list[UUID] = []
        sem = asyncio.Semaphore(pool_size + max_overflow)

        async def write_record() -> None:
            record_id = uuid4()
            event = make_audit_event()
            payload = json.dumps(event.model_dump(mode="json"))

            async with sem:
                start = time.monotonic()
                async with engine.connect() as conn:
                    elapsed_ms = (time.monotonic() - start) * 1000
                    latency.add(elapsed_ms)
                    await conn.execute(
                        INSERT_OUTBOX_RECORD,
                        {"id": record_id, "source": "business_event", "payload": payload},
                    )
                    await conn.commit()
                    inserted_ids.append(record_id)

        try:
            start = time.monotonic()
            tasks = [asyncio.create_task(write_record()) for _ in range(total_writes)]
            await asyncio.gather(*tasks)
            elapsed = time.monotonic() - start

            throughput = ThroughputResult(
                label=f"audit_write_pool_{pool_size}",
                total_operations=total_writes,
                elapsed_seconds=elapsed,
            )
            latency.log()
            throughput.log()

            logger.info(
                "pool_size_throughput",
                pool_size=pool_size,
                max_overflow=max_overflow,
                total_writes=total_writes,
                throughput_ops_sec=round(throughput.ops_per_second, 1),
                checkout_p50_ms=round(latency.p50, 3),
                checkout_p95_ms=round(latency.p95, 3),
            )

        finally:
            # Cleanup using NullPool engine to avoid pool issues
            cleanup_engine = create_async_engine(audit_perf_db_url, poolclass=NullPool)
            async with cleanup_engine.connect() as conn:
                for chunk_start in range(0, len(inserted_ids), 500):
                    chunk = inserted_ids[chunk_start : chunk_start + 500]
                    await conn.execute(DELETE_OUTBOX_RECORDS_BY_IDS, {"ids": chunk})
                await conn.commit()
            await cleanup_engine.dispose()
            await engine.dispose()

    async def test_pool_size_recommendation_report(
        self,
        audit_perf_db_url: str,
    ) -> None:
        """Generate a pool size recommendation report.

        Runs mixed workloads (audit writes + business queries) at each
        pool size and reports the configuration that minimizes business
        query impact while maintaining adequate audit throughput.
        """
        report = PerformanceReport(
            title="pool_size_recommendation",
            metadata={"pool_sizes": POOL_SIZES},
        )
        best_config: dict[str, object] = {}
        best_score: float = 0

        for pool_size in POOL_SIZES:
            max_overflow = max(pool_size, 5)
            engine = create_pooled_engine(audit_perf_db_url, pool_size=pool_size, max_overflow=max_overflow)

            audit_latency = LatencyResult(label=f"audit_pool_{pool_size}")
            business_latency = LatencyResult(label=f"business_pool_{pool_size}")
            audit_count = pool_size * 5
            business_count = 20

            async def audit_write(lat: LatencyResult = audit_latency, eng: AsyncEngine = engine) -> None:
                start = time.monotonic()
                async with eng.connect() as conn:
                    elapsed_ms = (time.monotonic() - start) * 1000
                    lat.add(elapsed_ms)
                    await conn.execute(
                        text("SELECT pg_sleep(:delay_seconds)"), {"delay_seconds": AUDIT_OP_DELAY_SECONDS}
                    )

            async def business_query(lat: LatencyResult = business_latency, eng: AsyncEngine = engine) -> None:
                start = time.monotonic()
                async with eng.connect() as conn:
                    elapsed_ms = (time.monotonic() - start) * 1000
                    lat.add(elapsed_ms)
                    await conn.execute(text("SELECT pg_sleep(:delay_seconds)"), {"delay_seconds": APP_TX_DELAY_SECONDS})

            try:
                audit_tasks = [asyncio.create_task(audit_write()) for _ in range(audit_count)]
                business_tasks = [asyncio.create_task(business_query()) for _ in range(business_count)]
                await asyncio.gather(*audit_tasks, *business_tasks)

                report.add_latency(audit_latency)
                report.add_latency(business_latency)

                score = 1.0 / (business_latency.p95 + 0.001)

                if score > best_score:
                    best_score = score
                    best_config = {
                        "pool_size": pool_size,
                        "max_overflow": max_overflow,
                        "business_p95_ms": round(business_latency.p95, 3),
                        "audit_p95_ms": round(audit_latency.p95, 3),
                    }

                logger.info(
                    "pool_size_mixed_result",
                    pool_size=pool_size,
                    audit_p95_ms=round(audit_latency.p95, 3),
                    business_p95_ms=round(business_latency.p95, 3),
                )

            finally:
                await engine.dispose()

        report.metadata["recommended_config"] = best_config
        report.log_all()

        logger.info(
            "pool_size_recommendation",
            recommended_pool_size=best_config.get("pool_size"),
            recommended_max_overflow=best_config.get("max_overflow"),
            business_p95_ms=best_config.get("business_p95_ms"),
        )


# ---------------------------------------------------------------------------
# AC: Separate pool vs. shared pool evaluated
# ---------------------------------------------------------------------------


class TestPoolIsolation:
    """Compare shared pool vs. separate audit pool for workload isolation.

    The audit worker uses a dedicated pool.  This test
    quantifies the isolation benefit by comparing business query latency
    when audit operations share the main pool vs. use a dedicated pool.
    """

    async def test_shared_pool_business_impact(
        self,
        audit_perf_db_url: str,
    ) -> None:
        """Measure business query latency when audit shares the main pool.

        Both audit writes and business queries use the same connection pool,
        competing for connections.
        """
        shared_engine = create_pooled_engine(audit_perf_db_url, pool_size=10, max_overflow=20)

        business_latency = LatencyResult(label="business_shared_pool")
        audit_latency = LatencyResult(label="audit_shared_pool")
        audit_count = 50
        business_count = 30

        async def audit_write() -> None:
            start = time.monotonic()
            async with shared_engine.connect() as conn:
                elapsed_ms = (time.monotonic() - start) * 1000
                audit_latency.add(elapsed_ms)
                await conn.execute(text("SELECT pg_sleep(:delay_seconds)"), {"delay_seconds": AUDIT_OP_DELAY_SECONDS})

        async def business_query() -> None:
            start = time.monotonic()
            async with shared_engine.connect() as conn:
                elapsed_ms = (time.monotonic() - start) * 1000
                business_latency.add(elapsed_ms)
                await conn.execute(text("SELECT pg_sleep(:delay_seconds)"), {"delay_seconds": APP_TX_DELAY_SECONDS})

        try:
            tasks = [asyncio.create_task(audit_write()) for _ in range(audit_count)] + [
                asyncio.create_task(business_query()) for _ in range(business_count)
            ]
            await asyncio.gather(*tasks)

            business_latency.log()
            audit_latency.log()

            logger.info(
                "shared_pool_impact",
                business_p50_ms=round(business_latency.p50, 3),
                business_p95_ms=round(business_latency.p95, 3),
                audit_p50_ms=round(audit_latency.p50, 3),
                audit_p95_ms=round(audit_latency.p95, 3),
            )

        finally:
            await shared_engine.dispose()

    async def test_separate_pool_business_impact(
        self,
        audit_perf_db_url: str,
    ) -> None:
        """Measure business query latency when audit uses a separate pool.

        Audit writes use a dedicated pool (5+2), business queries use the
        main pool (10+20).  This matches the production architecture.
        """
        main_engine = create_pooled_engine(audit_perf_db_url, pool_size=10, max_overflow=20)
        audit_engine = create_pooled_engine(audit_perf_db_url, pool_size=5, max_overflow=2)

        business_latency = LatencyResult(label="business_separate_pool")
        audit_latency = LatencyResult(label="audit_separate_pool")
        audit_count = 50
        business_count = 30

        async def audit_write() -> None:
            start = time.monotonic()
            async with audit_engine.connect() as conn:
                elapsed_ms = (time.monotonic() - start) * 1000
                audit_latency.add(elapsed_ms)
                await conn.execute(text("SELECT pg_sleep(:delay_seconds)"), {"delay_seconds": AUDIT_OP_DELAY_SECONDS})

        async def business_query() -> None:
            start = time.monotonic()
            async with main_engine.connect() as conn:
                elapsed_ms = (time.monotonic() - start) * 1000
                business_latency.add(elapsed_ms)
                await conn.execute(text("SELECT pg_sleep(:delay_seconds)"), {"delay_seconds": APP_TX_DELAY_SECONDS})

        try:
            tasks = [asyncio.create_task(audit_write()) for _ in range(audit_count)] + [
                asyncio.create_task(business_query()) for _ in range(business_count)
            ]
            await asyncio.gather(*tasks)

            business_latency.log()
            audit_latency.log()

            logger.info(
                "separate_pool_impact",
                business_p50_ms=round(business_latency.p50, 3),
                business_p95_ms=round(business_latency.p95, 3),
                audit_p50_ms=round(audit_latency.p50, 3),
                audit_p95_ms=round(audit_latency.p95, 3),
            )

        finally:
            await main_engine.dispose()
            await audit_engine.dispose()

    async def test_pool_isolation_comparison(
        self,
        audit_perf_db_url: str,
    ) -> None:
        """Side-by-side comparison of shared vs. separate pool isolation.

        Runs the same mixed workload under both configurations and reports
        the isolation benefit in terms of business query p95 reduction.
        """
        audit_count = 50
        business_count = 30

        # Shared pool
        shared_engine = create_pooled_engine(audit_perf_db_url, pool_size=10, max_overflow=20)
        shared_business = LatencyResult(label="shared_business")
        shared_audit = LatencyResult(label="shared_audit")

        async def shared_audit_write() -> None:
            start = time.monotonic()
            async with shared_engine.connect() as conn:
                elapsed_ms = (time.monotonic() - start) * 1000
                shared_audit.add(elapsed_ms)
                await conn.execute(text("SELECT pg_sleep(:delay_seconds)"), {"delay_seconds": AUDIT_OP_DELAY_SECONDS})

        async def shared_business_query() -> None:
            start = time.monotonic()
            async with shared_engine.connect() as conn:
                elapsed_ms = (time.monotonic() - start) * 1000
                shared_business.add(elapsed_ms)
                await conn.execute(text("SELECT pg_sleep(:delay_seconds)"), {"delay_seconds": APP_TX_DELAY_SECONDS})

        tasks = [asyncio.create_task(shared_audit_write()) for _ in range(audit_count)] + [
            asyncio.create_task(shared_business_query()) for _ in range(business_count)
        ]
        await asyncio.gather(*tasks)
        await shared_engine.dispose()

        # Separate pools
        main_engine = create_pooled_engine(audit_perf_db_url, pool_size=10, max_overflow=20)
        audit_engine = create_pooled_engine(audit_perf_db_url, pool_size=5, max_overflow=2)
        sep_business = LatencyResult(label="separate_business")
        sep_audit = LatencyResult(label="separate_audit")

        async def sep_audit_write() -> None:
            start = time.monotonic()
            async with audit_engine.connect() as conn:
                elapsed_ms = (time.monotonic() - start) * 1000
                sep_audit.add(elapsed_ms)
                await conn.execute(text("SELECT pg_sleep(:delay_seconds)"), {"delay_seconds": AUDIT_OP_DELAY_SECONDS})

        async def sep_business_query() -> None:
            start = time.monotonic()
            async with main_engine.connect() as conn:
                elapsed_ms = (time.monotonic() - start) * 1000
                sep_business.add(elapsed_ms)
                await conn.execute(text("SELECT pg_sleep(:delay_seconds)"), {"delay_seconds": APP_TX_DELAY_SECONDS})

        tasks = [asyncio.create_task(sep_audit_write()) for _ in range(audit_count)] + [
            asyncio.create_task(sep_business_query()) for _ in range(business_count)
        ]
        await asyncio.gather(*tasks)
        await main_engine.dispose()
        await audit_engine.dispose()

        improvement_ms = shared_business.p95 - sep_business.p95
        improvement_pct = (improvement_ms / shared_business.p95 * 100) if shared_business.p95 > 0 else 0

        report = PerformanceReport(
            title="pool_isolation_comparison",
            metadata={
                "shared_pool_config": "10+20",
                "separate_main_config": "10+20",
                "separate_audit_config": "5+2",
            },
        )
        report.add_latency(shared_business)
        report.add_latency(sep_business)
        report.log_all()

        logger.info(
            "pool_isolation_comparison",
            shared_business_p95_ms=round(shared_business.p95, 3),
            separate_business_p95_ms=round(sep_business.p95, 3),
            improvement_ms=round(improvement_ms, 3),
            improvement_pct=round(improvement_pct, 1),
            recommendation="separate_pools" if improvement_pct > 10 else "shared_acceptable",
        )


# ---------------------------------------------------------------------------
# AC: Semaphore tuning recommendations
# ---------------------------------------------------------------------------


class TestSemaphoreTuning:
    """Evaluate audit_writer_max_concurrent_writes semaphore tuning.

    The semaphore limits concurrent async audit writes.  If set too low,
    it artificially throttles throughput.  If set too high, it may cause
    pool exhaustion or excessive PostgreSQL connections.
    """

    @pytest.mark.parametrize("semaphore_limit", SEMAPHORE_LIMITS)
    async def test_throughput_at_semaphore_limit(
        self,
        audit_perf_session_factory: async_sessionmaker[AsyncSession],
        semaphore_limit: int,
    ) -> None:
        """Measure audit write throughput at each semaphore limit.

        Fires concurrent writes limited by the semaphore and measures
        how many complete within a fixed time window.
        """
        sem = asyncio.Semaphore(semaphore_limit)
        conn_sem = asyncio.Semaphore(MAX_TEST_DB_CONNECTIONS)
        total_writes = semaphore_limit * 5
        latency = LatencyResult(label=f"semaphore_{semaphore_limit}")
        inserted_ids: list[UUID] = []

        async def write_with_semaphore() -> None:
            event = make_audit_event()
            async with sem, conn_sem, audit_perf_session_factory() as session:
                record = AuditOutboxRecord(
                    event_source=AuditEventSource.BUSINESS_EVENT,
                    event_payload=event.model_dump(mode="json"),
                )
                async with measure_latency_async(latency):
                    session.add(record)
                    await session.commit()
                inserted_ids.append(record.id)

        try:
            start = time.monotonic()
            tasks = [asyncio.create_task(write_with_semaphore()) for _ in range(total_writes)]
            await asyncio.gather(*tasks)
            elapsed = time.monotonic() - start

            throughput = ThroughputResult(
                label=f"semaphore_{semaphore_limit}",
                total_operations=latency.count,
                elapsed_seconds=elapsed,
            )
            latency.log()
            throughput.log()

            logger.info(
                "semaphore_throughput",
                semaphore_limit=semaphore_limit,
                total_writes=latency.count,
                throughput_ops_sec=round(throughput.ops_per_second, 1),
                p50_ms=round(latency.p50, 3),
                p95_ms=round(latency.p95, 3),
            )

        finally:
            await cleanup_outbox_records(audit_perf_session_factory, inserted_ids)

    async def test_semaphore_vs_pool_size_alignment(
        self,
        audit_perf_db_url: str,
    ) -> None:
        """Test whether the semaphore should match the pool's total capacity.

        Compares throughput when semaphore matches pool capacity (optimal
        resource usage) vs. when it exceeds pool capacity (writes queue
        at pool checkout).
        """
        pool_size = 5
        max_overflow = 5
        pool_capacity = pool_size + max_overflow

        report = PerformanceReport(
            title="semaphore_pool_alignment",
            metadata={"pool_size": pool_size, "max_overflow": max_overflow},
        )

        for sem_multiplier in [0.5, 1.0, 2.0, 5.0]:
            sem_limit = int(pool_capacity * sem_multiplier)
            engine = create_pooled_engine(audit_perf_db_url, pool_size=pool_size, max_overflow=max_overflow)
            sem = asyncio.Semaphore(sem_limit)
            latency = LatencyResult(label=f"sem_{sem_limit}_pool_{pool_capacity}")
            total_writes = 50

            async def write(
                lat: LatencyResult = latency, semaphore: asyncio.Semaphore = sem, eng: AsyncEngine = engine
            ) -> None:
                async with semaphore:
                    start = time.monotonic()
                    async with eng.connect() as conn:
                        elapsed_ms = (time.monotonic() - start) * 1000
                        lat.add(elapsed_ms)
                        await conn.execute(text("SELECT pg_sleep(:delay_seconds)"), {"delay_seconds": 0.01})

            try:
                start = time.monotonic()
                tasks = [asyncio.create_task(write()) for _ in range(total_writes)]
                await asyncio.gather(*tasks)
                elapsed = time.monotonic() - start

                throughput = ThroughputResult(
                    label=f"sem_{sem_limit}_pool_{pool_capacity}",
                    total_operations=total_writes,
                    elapsed_seconds=elapsed,
                )
                report.add_latency(latency)
                report.add_throughput(throughput)

                logger.info(
                    "semaphore_pool_alignment",
                    semaphore_limit=sem_limit,
                    pool_capacity=pool_capacity,
                    multiplier=sem_multiplier,
                    throughput_ops_sec=round(throughput.ops_per_second, 1),
                    checkout_p95_ms=round(latency.p95, 3),
                )

            finally:
                await engine.dispose()

        report.log_all()
