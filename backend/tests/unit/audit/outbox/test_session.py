"""Tests for audit worker session factory.

Verifies that the audit worker has a dedicated connection pool separate from
the main application pool, addressing connection pool contention issues.
"""

from sqlalchemy.ext.asyncio import AsyncEngine

from syntara.audit.outbox.session import AuditWorkerAsyncSessionLocal, audit_worker_engine
from syntara.core.database.session import engine as main_engine


def test_audit_worker_has_separate_engine() -> None:
    """Audit worker engine should be separate from main engine."""
    assert audit_worker_engine is not main_engine, "Audit worker should have its own engine"
    assert isinstance(audit_worker_engine, AsyncEngine)
    assert isinstance(main_engine, AsyncEngine)


def test_audit_worker_has_separate_pool() -> None:
    """Audit worker pool should be separate from main pool."""
    assert audit_worker_engine.pool is not main_engine.pool, "Pools should be separate instances"


def test_audit_worker_pool_size() -> None:
    """Audit worker pool should be sized appropriately (smaller than main)."""
    worker_pool_size = audit_worker_engine.pool.size()  # type: ignore[attr-defined]
    main_pool_size = main_engine.pool.size()  # type: ignore[attr-defined]

    # Worker pool should be smaller since only background worker uses it
    assert worker_pool_size < main_pool_size, "Worker pool should be smaller than main pool"
    assert worker_pool_size > 0, "Worker pool should have at least 1 connection"


def test_audit_worker_session_factory_exists() -> None:
    """Audit worker session factory should be properly configured."""
    assert AuditWorkerAsyncSessionLocal is not None
    assert callable(AuditWorkerAsyncSessionLocal)


def test_audit_worker_connects_to_same_database() -> None:
    """Audit worker should connect to the same database URL as main pool.

    Only the connection pool is separate - both pools connect to the same database
    to preserve transactional integrity for CRUD trigger writes.
    """
    main_url = str(main_engine.url)
    worker_url = str(audit_worker_engine.url)

    # Both should have the same database connection URL
    assert main_url == worker_url, "Both pools should connect to the same database"
