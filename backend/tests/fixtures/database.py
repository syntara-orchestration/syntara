"""Database fixtures: PostgreSQL container and test sessions."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest_asyncio
import structlog
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession
from testcontainers.postgres import PostgresContainer

from syntara.core.config.base import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    import sqlalchemy

logger = structlog.stdlib.get_logger(__name__)

_SCLORG_ADMIN_PASSWORD = "pg-admin-test"  # noqa: S105

TEST_DB_USER = os.getenv("APP_DB_USER", "admin")
TEST_DB_PASSWORD = os.getenv("APP_DB_PASSWORD", "admin")
TEST_DB_HOST = os.getenv("APP_DB_HOST", "localhost")
TEST_DB_PORT = os.getenv("APP_DB_PORT", "5432")
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _get_alembic_config(db_url: str) -> Config:
    """Build an Alembic Config pointing at the test database."""
    alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location",
        str(PROJECT_ROOT / "src" / "syntara" / "core" / "database" / "migrations"),
    )
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    return alembic_cfg


def _safe_url(url: str | sqlalchemy.engine.URL) -> str:
    """Render URL with credentials redacted for logging."""
    return make_url(str(url)).render_as_string(hide_password=True)


async def _upgrade_database_schema(db_url: str) -> None:
    """Apply Alembic migrations to the test database (runs in a thread)."""
    logger.debug("Applying Alembic migrations to test database %s", db_url)
    try:
        await asyncio.to_thread(command.upgrade, _get_alembic_config(db_url), "head")
        logger.debug("Successfully applied migrations to %s", db_url)
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("Failed to apply migrations to %s", _safe_url(db_url))
        raise


@pytest_asyncio.fixture(scope="session")
async def test_db_engine(worker_id: str) -> AsyncGenerator[AsyncEngine, None]:
    """Create a test database engine with the migrated schema.

    Auto-starts a PostgreSQL container via testcontainers (requires Docker or Podman).
    Each xdist worker gets its own container for full isolation.
    """
    logger.debug("Starting PostgreSQL container for worker '%s'", worker_id)
    postgres_image = os.getenv("POSTGRES_IMAGE", "quay.io/sclorg/postgresql-15-c9s")
    pg_container = PostgresContainer(postgres_image)
    if "sclorg" in postgres_image:
        pg_container.with_env("POSTGRESQL_USER", pg_container.username)
        pg_container.with_env("POSTGRESQL_PASSWORD", pg_container.password)
        pg_container.with_env("POSTGRESQL_DATABASE", pg_container.dbname)
        pg_container.with_env("POSTGRESQL_ADMIN_PASSWORD", _SCLORG_ADMIN_PASSWORD)
    with pg_container as pg:
        test_database_url = pg.get_connection_url(driver="asyncpg")
        engine = create_async_engine(test_database_url, echo=False, poolclass=NullPool)

        with tempfile.NamedTemporaryFile(mode="w", suffix="-admin-pw", delete=False) as pw_file:
            pw_file.write("test-admin-password")
            pw_path = pw_file.name
        os.environ["APP_ADMIN_PASSWORD_PATH"] = pw_path
        get_settings.cache_clear()
        try:
            await _upgrade_database_schema(test_database_url)
            logger.debug("Test database ready (container) for worker '%s'", worker_id)
            yield engine
            await engine.dispose()
        finally:
            os.environ.pop("APP_ADMIN_PASSWORD_PATH", None)
            Path(pw_path).unlink(missing_ok=True)


@pytest_asyncio.fixture
async def test_db_session(test_db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session with rollback-based isolation.

    Uses a connection-level transaction that is rolled back after each test,
    so every test starts with a clean database without paying the cost of
    TRUNCATE on every table.
    """
    async with test_db_engine.connect() as conn:
        transaction = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest_asyncio.fixture(scope="session")
async def test_session_factory(test_db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory from the test database engine."""
    return async_sessionmaker(test_db_engine, class_=AsyncSession, expire_on_commit=False)
