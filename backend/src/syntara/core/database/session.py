"""Database session management with async support and soft delete filtering."""

from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Query, Session
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import get_settings
from syntara.core.constants import FieldLimits
from syntara.core.database.ssl import build_ssl_connect_args

settings = get_settings()

_ssl_connect_args = build_ssl_connect_args(
    ssl_mode=settings.db_ssl_mode,
    ssl_root_cert=settings.db_ssl_root_cert,
    ssl_cert=settings.db_ssl_cert,
    ssl_key=settings.db_ssl_key,
)

logger = structlog.stdlib.get_logger(__name__)


# Create async engine with connection pooling
engine = create_async_engine(
    settings.database_url,
    echo=False,  # Set to True for SQL query logging in development
    pool_size=settings.db_pool_size,  # Maximum number of connections in the pool
    max_overflow=settings.db_max_overflow,  # Maximum overflow connections
    pool_timeout=settings.db_pool_timeout_seconds,  # Timeout waiting for an available connection
    pool_pre_ping=True,  # Verify connections before using them
    pool_recycle=3600,  # Recycle connections after 1 hour
    connect_args=_ssl_connect_args,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
)


def register_sqlalchemy_events() -> None:
    """Register SQLAlchemy event listeners.

    Attaches before_flush listeners for:
    - Audit context propagation (Postgres session variables)
    - Auto-creation of Principal rows for principal subtypes
    """
    from syntara.core.models.principal import _before_flush  # noqa: PLC0415

    target = AsyncSession.sync_session_class

    # Register each handler only if not already registered (idempotency)
    if not event.contains(target, "before_flush", set_audit_context):
        event.listen(target, "before_flush", set_audit_context)
    if not event.contains(target, "before_flush", _before_flush):
        event.listen(target, "before_flush", _before_flush)


def apply_audit_context(session: Session) -> None:
    """Set transaction-scoped Postgres variables for audit triggers.

    Reads actor and workflow context from ContextVars (set by middleware or
    ``actor_context``) and propagates them to Postgres as session variables.

    Called automatically from the ORM ``before_flush`` hook. Callers that issue
    Core/raw SQL DML (which bypasses ``before_flush``) must invoke this before
    the mutating statement so audit triggers see the acting principal.

    Variables are transaction-scoped via SET LOCAL and automatically
    cleared on COMMIT or ROLLBACK.

    Note: SET LOCAL does not support bind parameters, so values are
    directly interpolated. String values are escaped by doubling single
    quotes per PostgreSQL string literal rules. UUIDs are validated format.
    """
    # Import here to avoid circular dependency between session and audit modules
    from syntara.audit.emitter import (  # noqa: PLC0415
        activity_id_context_var,
        actor_context_var,
        execution_id_context_var,
        workflow_id_context_var,
    )

    actor = actor_context_var.get()
    workflow_id = workflow_id_context_var.get()
    execution_id = execution_id_context_var.get()
    activity_id = activity_id_context_var.get()

    # Build SET LOCAL commands with proper string escaping
    # UUIDs are validated format, strings escape single quotes by doubling them
    if actor and actor.actor_id:
        session.execute(text(f"SET LOCAL app.actor_id = '{actor.actor_id}'"))
    if actor and actor.actor_username:
        # Defense-in-depth: cap username length before SQL interpolation
        capped_username = actor.actor_username[: FieldLimits.NAME_MAX_LENGTH]
        escaped_username = capped_username.replace("'", "''")
        session.execute(text(f"SET LOCAL app.actor_username = '{escaped_username}'"))
    if actor and actor.actor_type:
        session.execute(text(f"SET LOCAL app.actor_type = '{actor.actor_type.value}'"))
    if workflow_id:
        try:
            uuid_str = str(UUID(str(workflow_id)))
            session.execute(text(f"SET LOCAL app.workflow_id = '{uuid_str}'"))
        except (TypeError, ValueError):
            logger.warning("Unable to set workflow_id in Postgres session. Invalid UUID.")
    if execution_id:
        try:
            uuid_str = str(UUID(str(execution_id)))
            session.execute(text(f"SET LOCAL app.execution_id = '{uuid_str}'"))
        except (TypeError, ValueError):
            logger.warning("Unable to set execution_id in Postgres session. Invalid UUID.")
    if activity_id:
        # Escape single quotes in activity_id (PostgreSQL string literal escaping)
        escaped_activity_id = activity_id.replace("'", "''")
        session.execute(text(f"SET LOCAL app.activity_id = '{escaped_activity_id}'"))


def set_audit_context(session: Session, _flush_context: object, _instances: object) -> None:
    """SQLAlchemy ``before_flush`` adapter for :func:`apply_audit_context`."""
    apply_audit_context(session)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions.

    **Important**: Services that write data MUST call ``await session.commit()``
    explicitly before returning.  FastAPI runs yield-dependency cleanup *after*
    the HTTP response has been sent to the client, so the ``commit()`` below is
    only a safety net for read-only requests — it must NOT be relied upon for
    write visibility.

    Yields:
        AsyncSession: Database session with automatic cleanup and soft delete filtering.

    Example:
        ```python
        @app.get("/workflows")
        async def list_workflows(db: AsyncSession = Depends(get_db)):
            result = await db.exec(select(Workflow))
            workflows = result.all()
            return workflows
        ```

    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def apply_soft_delete_filter(query: Query[Any]) -> Query[Any]:
    """Apply soft delete filter to query.

    This function adds a WHERE clause to exclude soft-deleted records
    (WHERE deleted_at IS NULL).

    Args:
        query: SQLAlchemy query object

    Returns:
        Query with soft delete filter applied

    Note:
        This is a utility function for manual query building.
        Soft delete filtering is automatically applied via SQLAlchemy events.

    """
    # Get the model class from the query
    column_desc = query.column_descriptions[0].get("type")
    if column_desc is None:
        return query

    model_class = column_desc

    # Check if model has deleted_at column
    mapper = inspect(model_class)
    if (
        mapper is not None
        and hasattr(mapper, "columns")
        and "deleted_at" in mapper.columns
        and hasattr(model_class, "deleted_at")
    ):
        return query.filter(model_class.deleted_at.is_(None))

    return query


# Note: Automatic soft-delete filtering via event listeners is disabled for AsyncSession
# as the 'do_orm_execute' event is not available. Instead, we explicitly filter
# soft-deleted records in API endpoints using .filter(Model.deleted_at.is_(None))

# Register audit context event listener at module load time
register_sqlalchemy_events()
