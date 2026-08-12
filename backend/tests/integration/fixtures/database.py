"""Database fixtures specific to integration tests."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
import structlog
from testcontainers.redis import RedisContainer

from syntara.core.config.base import get_settings

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy.engine import URL
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.stdlib.get_logger(__name__)

_SCLORG_ADMIN_PASSWORD = "pg-admin-test"  # noqa: S105


@pytest.fixture(scope="session")
def test_db_admin_url(test_db_engine: AsyncEngine) -> URL:
    """Admin database URL with CREATEDB/DROPDB privilege for DDL fixtures."""
    postgres_image = os.getenv("POSTGRES_IMAGE", "quay.io/sclorg/postgresql-15-c9s")
    if "sclorg" in postgres_image:
        return test_db_engine.url.set(username="postgres", password=_SCLORG_ADMIN_PASSWORD, database="postgres")
    return test_db_engine.url.set(database="postgres")


@pytest.fixture(scope="session")
def test_cache(worker_id: str) -> Generator[None, None, None]:
    """Set up Redis cache for tests via testcontainers."""
    redis_image = os.getenv("REDIS_IMAGE", "quay.io/sclorg/redis-6-c9s")
    logger.debug("Starting Redis container for worker '%s'", worker_id)
    with RedisContainer(redis_image, password="cache") as redis_container:  # noqa: S106
        host = redis_container.get_container_host_ip()
        port = int(redis_container.get_exposed_port(redis_container.port))
        logger.debug("Test Redis ready (container) for worker '%s' at %s:%s", worker_id, host, port)
        os.environ["APP_CACHE_HOST"] = host
        os.environ["APP_CACHE_PORT"] = str(port)
        get_settings.cache_clear()
        try:
            yield
        finally:
            os.environ.pop("APP_CACHE_HOST", None)
            os.environ.pop("APP_CACHE_PORT", None)
            get_settings.cache_clear()
