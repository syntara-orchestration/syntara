"""Dedicated database session factory for audit outbox worker.

Provides a separate connection pool exclusively for the AuditOutboxWorker
background task, isolating worker operations (SELECT/DELETE from audit_outbox)
from the main application request path.

This eliminates connection pool contention between:
- Application requests (using AsyncSessionLocal from core.database.session)
- Audit worker background processing (using audit_worker_session_factory)

The audit_outbox table remains in the main database, preserving transactional
integrity for CRUD trigger writes. Only the connection pool is separated.
"""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import get_settings
from syntara.core.database.ssl import build_ssl_connect_args

settings = get_settings()

_ssl_connect_args = build_ssl_connect_args(
    ssl_mode=settings.db_ssl_mode,
    ssl_root_cert=settings.db_ssl_root_cert,
    ssl_cert=settings.db_ssl_cert,
    ssl_key=settings.db_ssl_key,
)

# Dedicated async engine for audit worker (separate connection pool)
# Sized smaller than main pool since only background worker uses it
audit_worker_engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=settings.audit_worker_pool_size,
    max_overflow=settings.audit_worker_max_overflow,
    pool_timeout=settings.db_pool_timeout_seconds,
    pool_pre_ping=True,
    pool_recycle=3600,  # Recycle connections after 1 hour
    connect_args=_ssl_connect_args,
)

# Dedicated session factory for audit worker
# Worker SELECT/DELETE operations use this pool instead of the main pool
AuditWorkerAsyncSessionLocal = async_sessionmaker(
    audit_worker_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
)
