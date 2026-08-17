"""Fixtures for audit subsystem integration tests.

These tests connect to the same PostgreSQL database that the integration
test suite provisions via testcontainers, so they measure real contention
between audit operations and business workloads against a fully-migrated
schema.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import structlog
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData
from syntara.audit.outbox.worker import get_outbox_worker
from syntara.core.models.principal import PrincipalType

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncEngine
    from sqlalchemy.pool import QueuePool

logger = structlog.stdlib.get_logger(__name__)

# Marker applied to the test tag for identifying seeded records
PERF_TEST_MARKER = "perf_test_audit_seed"

# Max simultaneous DB connections from tests (avoids exhausting the target
# PostgreSQL's max_connections, which is shared with the running AO).
MAX_TEST_DB_CONNECTIONS = 20

_health_checks_done = False

INSERT_OUTBOX_RECORD_SQL = text(
    """
    INSERT INTO audit_outbox (id, created_at, event_source, event_payload)
    VALUES (CAST(:id AS uuid), now(), CAST(:source AS auditeventsource), CAST(:payload AS jsonb))
    """
)

DRAIN_SELECT_IDS_SQL = text("SELECT id FROM audit_outbox ORDER BY created_at LIMIT :batch FOR UPDATE SKIP LOCKED")

DELETE_OUTBOX_BY_ID_SQL = text("DELETE FROM audit_outbox WHERE id = :id")

DELETE_OUTBOX_BY_IDS_SQL = text("DELETE FROM audit_outbox WHERE id IN :ids").bindparams(
    bindparam("ids", expanding=True)
)

DELETE_OUTBOX_RECORDS_BY_IDS = DELETE_OUTBOX_BY_IDS_SQL


# ---------------------------------------------------------------------------
# Engine & session fixtures — connect to the integration test database
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def audit_perf_db_url(test_db_engine: AsyncEngine) -> str:
    """Return the asyncpg URL of the integration test database."""
    return test_db_engine.url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def audit_perf_engine(audit_perf_db_url: str) -> AsyncEngine:
    """Create an async engine connected to the live AO database.

    Uses ``NullPool`` so that each connection is created fresh per checkout
    and closed immediately after use.  This avoids asyncpg event-loop
    affinity issues when pytest-asyncio creates a new loop per test
    (``asyncio_default_test_loop_scope=function``).
    """
    engine = create_async_engine(
        audit_perf_db_url,
        echo=False,
        poolclass=NullPool,
    )
    logger.info(
        "audit_perf_engine created (NullPool)",
        url=audit_perf_db_url.rsplit("@", maxsplit=1)[-1],
    )
    return engine


@pytest.fixture(scope="session")
def audit_perf_session_factory(
    audit_perf_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Session factory bound to the live AO database (simulates main app pool)."""
    return async_sessionmaker(
        audit_perf_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture(scope="session")
def audit_worker_perf_session_factory(
    audit_perf_db_url: str,
) -> async_sessionmaker[AsyncSession]:
    """Separate session factory simulating the audit worker's dedicated pool.

    The audit outbox worker uses its own connection
    pool (``audit_worker_pool_size=5``, ``audit_worker_max_overflow=2``)
    isolated from the main application pool.  This fixture provides a
    second NullPool-backed session factory so mixed-workload tests can
    route audit operations through a different session factory than
    business queries, matching the production architecture.
    """
    worker_engine = create_async_engine(
        audit_perf_db_url,
        echo=False,
        poolclass=NullPool,
    )
    logger.info("audit_worker_perf_engine created (NullPool, simulates worker pool)")
    return async_sessionmaker(
        worker_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture
async def audit_perf_session(
    audit_perf_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Per-test session with automatic rollback for read-only probes.

    For tests that need to commit (e.g., seeding), use the session factory
    directly and handle cleanup via the ``cleanup_seeded_records`` fixture.
    """
    async with audit_perf_session_factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Deployment health checks (run once, in the first test's event loop)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _verify_deployment(audit_perf_engine: AsyncEngine) -> None:
    """Run one-time health checks on first test invocation.

    Verifies audit tables exist and CRUD triggers are attached.  Uses a
    module-level flag so the checks only run once across all tests, but
    execute inside a per-test event loop to avoid asyncpg loop-affinity
    issues.
    """
    global _health_checks_done  # noqa: PLW0603
    if _health_checks_done:
        return
    _health_checks_done = True

    async with audit_perf_engine.connect() as conn:
        # Verify audit_outbox table
        result = await conn.execute(
            text("SELECT EXISTS (  SELECT 1 FROM information_schema.tables   WHERE table_name = 'audit_outbox')")
        )
        if not result.scalar():
            pytest.fail(
                "audit_outbox table not found — ensure Alembic migrations have been applied on the target database"
            )

        # Verify audit_table_metadata table
        result = await conn.execute(
            text(
                "SELECT EXISTS (  SELECT 1 FROM information_schema.tables   WHERE table_name = 'audit_table_metadata')"
            )
        )
        if not result.scalar():
            pytest.fail(
                "audit_table_metadata table not found — ensure Alembic "
                "migrations have been applied on the target database"
            )

        # Check CRUD triggers
        result = await conn.execute(
            text("SELECT COUNT(*) FROM pg_trigger WHERE tgname LIKE 'audit_trigger_%' AND tgenabled = 'O'")
        )
        count = result.scalar() or 0

    from tests.integration.audit.drain_helpers import log_drain_settings_for_deployment

    logger.info("audit_perf: verified audit_outbox and audit_table_metadata tables exist")
    log_drain_settings_for_deployment()
    if count == 0:
        logger.warning(
            "audit_perf: no active audit CRUD triggers found — "
            "trigger overhead tests will not produce meaningful results. "
            "Run 'make -C backend db-seed-all' to attach triggers."
        )
    else:
        logger.info("audit_perf: found active CRUD triggers", count=count)


# ---------------------------------------------------------------------------
# Per-test outbox worker state reset
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _reset_outbox_worker_for_test(
    test_db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[None, None]:
    """Isolate the outbox worker singleton between integration tests.

    Two problems this fixture solves:

    1. **Orphaned tasks**: pytest-asyncio uses a new event loop per test function.
       Tasks created by a previous test's cleanup (e.g., DELETE in a finally block)
       may not complete before the loop closes. Those Task objects stay in
       ``worker._pending`` referencing a closed loop. When the next test's
       ``drain()`` calls ``asyncio.gather(*pending)``, awaiting a Task from a
       closed loop can block indefinitely.  Clearing ``_pending`` at test start
       removes these stale references.

    2. **Stale session factory**: The worker singleton holds a session-scoped
       ``_write_session_factory``. Swapping it for a function-scoped factory
       (created after ``_restore_from_template`` has run) ensures every async
       write targets the freshly-restored test database rather than a factory
       that may have cached state from before the restore.
    """
    # Skip reset if the worker singleton has not been initialised yet (e.g. in
    # performance tests that do not boot the full app via session_app/base_client).
    if get_outbox_worker.cache_info().currsize == 0:
        yield
        return

    worker = get_outbox_worker()

    # Remove orphaned Task objects left over from previous test event loops.
    worker._pending.clear()

    original_write_factory = worker._write_session_factory
    original_session_factory = worker._session_factory
    worker._write_session_factory = test_db_session_factory
    worker._session_factory = test_db_session_factory
    try:
        yield
    finally:
        worker._write_session_factory = original_write_factory
        worker._session_factory = original_session_factory


# ---------------------------------------------------------------------------
# Drain recovery helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def quiescent_outbox(
    audit_perf_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Wait for the outbox to reach zero depth before a drain/recovery test."""
    from tests.integration.audit.drain_helpers import (
        DEFAULT_QUIESCENT_TIMEOUT_SECONDS,
        wait_for_quiescent_outbox,
    )

    await wait_for_quiescent_outbox(
        audit_perf_session_factory,
        timeout_seconds=DEFAULT_QUIESCENT_TIMEOUT_SECONDS,
    )


@pytest_asyncio.fixture
async def cleanup_seeded_records(
    audit_perf_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[list[UUID], None]:
    """Collect record IDs during a test, delete them in teardown.

    Usage::

        async def test_something(cleanup_seeded_records, ...):
            ids = cleanup_seeded_records
            # ... insert records, append their UUID ``id`` values to ``ids`` ...
            # teardown deletes them automatically
    """
    record_ids: list[UUID] = []
    yield record_ids

    if not record_ids:
        return

    async with audit_perf_session_factory() as session:
        await session.execute(DELETE_OUTBOX_RECORDS_BY_IDS, {"ids": record_ids})
        await session.commit()
        logger.info("audit_perf: cleaned up seeded records", count=len(record_ids))


# ---------------------------------------------------------------------------
# Shared helpers — used across multiple test modules
# ---------------------------------------------------------------------------

# Max simultaneous DB connections from tests (avoids exhausting the target
# PostgreSQL's max_connections, which is shared with the running AO).
MAX_TEST_DB_CONNECTIONS = 20


async def cleanup_outbox_records(
    session_factory: async_sessionmaker[AsyncSession],
    record_ids: list[UUID],
) -> None:
    """Delete outbox records by ID in 500-row chunks."""
    if not record_ids:
        return
    async with session_factory() as session:
        for chunk_start in range(0, len(record_ids), 500):
            chunk = record_ids[chunk_start : chunk_start + 500]
            await session.execute(DELETE_OUTBOX_RECORDS_BY_IDS, {"ids": chunk})
        await session.commit()


def make_audit_event(*, benchmark: str = "perf_test") -> AuditEvent:
    """Create a realistic AuditEvent for performance benchmarking.

    Args:
        benchmark: Label for the benchmark (used in event_action and
            structured_data to identify the source test).

    """
    return AuditEvent(
        event_category=EventCategory.SYSTEM_OPERATION,
        event_severity=EventSeverity.INFO,
        event_status=EventStatus.SUCCESS,
        event_action=f"perf_test.{benchmark}",
        actor_id=uuid4(),
        actor_type=PrincipalType.SYSTEM,
        actor_username="perf-test-runner",
        source_component="tests.performance.audit",
        resource_urn=f"urn:syntara:perf-test:{uuid4()}",
        resource_name=f"{benchmark}-resource",
        event_message=f"Performance test event ({benchmark})",
        structured_data=AuditContextData(data_type="perf_test", benchmark=benchmark),
    )


def create_pooled_engine(
    db_url: str,
    *,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_timeout: float = 30.0,
    pool_pre_ping: bool = True,
) -> AsyncEngine:
    """Create an async engine with QueuePool for pool-behaviour tests."""
    return create_async_engine(
        db_url,
        echo=False,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_pre_ping=pool_pre_ping,
        pool_recycle=3600,
    )


def make_worker_settings_mock(**overrides: object) -> MagicMock:
    """Return a MagicMock with all attributes needed by AuditOutboxWorker.__init__.

    AuditOutboxWorker reads several settings in its constructor.  On the
    OpenShift performance pod the real ``get_settings()`` may return a leaked
    MagicMock from a previously-patched test (lru_cache + test ordering).
    This helper provides a properly-typed mock so that ``asyncio.Semaphore``
    and the adaptive state machine receive ints/floats, not MagicMock objects.
    """
    defaults: dict[str, object] = {
        "audit_enabled": True,
        "audit_outbox_poll_interval_seconds": 5.0,
        "audit_outbox_batch_size": 100,
        "audit_writer_max_concurrent_writes": 100,
        "audit_writer_max_retries": 3,
        "audit_writer_base_delay_seconds": 0.1,
    }
    defaults.update(overrides)
    mock = MagicMock()
    for attr, value in defaults.items():
        setattr(mock, attr, value)
    return mock


def get_pool_status(engine: AsyncEngine) -> dict[str, int]:
    """Extract current pool metrics from the engine's QueuePool."""
    pool = cast("QueuePool", engine.pool)
    return {
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "total_connections": pool.checkedin() + pool.checkedout(),
    }
