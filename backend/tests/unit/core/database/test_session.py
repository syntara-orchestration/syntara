"""Unit tests for database session engine configuration."""

import importlib

import pytest

from syntara.core.config import base as config_module
from syntara.core.database import session as session_module


@pytest.mark.asyncio
async def test_engine_pool_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Engine pool settings should reflect configured values."""
    monkeypatch.setenv("APP_DB_POOL_SIZE", "25")
    monkeypatch.setenv("APP_DB_MAX_OVERFLOW", "7")
    monkeypatch.setenv("APP_DB_POOL_TIMEOUT_SECONDS", "45")

    try:
        # Ensure no old engine remains alive before reloading module-level engine.
        await session_module.engine.dispose()
        config_module.get_settings.cache_clear()

        reloaded_session_module = importlib.reload(session_module)
        pool = reloaded_session_module.engine.sync_engine.pool

        assert pool.size() == 25
        assert pool.timeout() == 45
        assert pool._max_overflow == 7
    finally:
        await session_module.engine.dispose()
        monkeypatch.undo()
        config_module.get_settings.cache_clear()
        importlib.reload(session_module)
