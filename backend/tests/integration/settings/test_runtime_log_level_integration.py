"""Integration tests: DB -> SettingsCache -> apply_runtime_log_level -> logger.

Verifies the full round-trip from a database-backed runtime setting through
to actual Python logger level changes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from syntara.core.logging.logging import apply_runtime_log_level
from syntara.settings.cache.settings_cache import SettingsCache, set_runtime_settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Generator

    from sqlmodel.ext.asyncio.session import AsyncSession

# The key used by apply_runtime_log_level() in production.
_LOG_LEVEL_KEY = "logging.log_level"

_LOGGER_NAMES = ("uvicorn", "uvicorn.error", "uvicorn.access")

# language=SQL
_UPSERT_LOG_LEVEL = """
INSERT INTO runtime_settings
    (id, key, name, category, value_type, value, default_value,
     requires_restart, version, labels, created_at, updated_at)
VALUES
    (gen_random_uuid(), :key, 'Log Level', 'system', 'string',
     CAST(:value AS jsonb), CAST('"INFO"' AS jsonb),
     false, 1, '{}'::jsonb, now(), now())
ON CONFLICT (key) DO UPDATE SET value = CAST(:value AS jsonb)
"""


async def _set_log_level_value(
    session: AsyncSession,
    value: str,
) -> None:
    """Upsert the logging.log_level runtime setting to *value*."""
    await session.exec(  # type: ignore[call-overload]
        text(_UPSERT_LOG_LEVEL),
        params={"key": _LOG_LEVEL_KEY, "value": f'"{value}"'},
    )
    await session.commit()
    # Evict any ORM-cached RuntimeSetting objects so subsequent
    # ORM queries see the raw-SQL change.
    session.expire_all()


@pytest.fixture
async def _restore_log_level_setting(test_db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Restore the logging.log_level value to its seeded default after the test."""
    yield
    await test_db_session.rollback()
    await test_db_session.exec(  # type: ignore[call-overload]
        text("UPDATE runtime_settings SET value = NULL WHERE key = :key"),
        params={"key": _LOG_LEVEL_KEY},
    )
    await test_db_session.commit()


@pytest.fixture
def _scoped_runtime_cache(
    test_session_factory: Callable[[], object],
) -> Generator[None, None, None]:
    """Install a SettingsCache for the test, restore the previous one after."""
    import syntara.settings.cache.settings_cache as _sc

    prev = _sc._runtime_settings
    cache = SettingsCache(session_factory=test_session_factory)
    set_runtime_settings(cache)
    yield
    _sc._runtime_settings = prev


@pytest.fixture
def _preserve_log_levels() -> Generator[None, None, None]:
    """Save and restore logger levels around the test."""
    root = logging.getLogger()
    originals = {"": root.level, **{n: logging.getLogger(n).level for n in _LOGGER_NAMES}}
    yield
    root.setLevel(originals[""])
    for name in _LOGGER_NAMES:
        logging.getLogger(name).setLevel(originals[name])


@pytest.mark.asyncio
@pytest.mark.usefixtures("_restore_log_level_setting", "_scoped_runtime_cache", "_preserve_log_levels")
async def test_db_log_level_propagates_to_loggers(
    test_db_session: AsyncSession,
) -> None:
    """Set logging.log_level = WARNING in DB, verify loggers change."""
    await _set_log_level_value(test_db_session, "WARNING")

    await apply_runtime_log_level()

    assert logging.getLogger().level == logging.WARNING
    for name in _LOGGER_NAMES:
        assert logging.getLogger(name).level == logging.WARNING


@pytest.mark.asyncio
@pytest.mark.usefixtures("_restore_log_level_setting", "_scoped_runtime_cache", "_preserve_log_levels")
async def test_invalid_log_level_falls_back_to_catalog_default(
    test_db_session: AsyncSession,
) -> None:
    """Set logging.log_level = INVALID, verify fallback to catalog default INFO."""
    await _set_log_level_value(test_db_session, "INVALID")

    await apply_runtime_log_level()

    # Read-time validation in _validate_against_catalog rejects "INVALID"
    # (not in allowed_values) and returns the catalog default_value "INFO".
    assert logging.getLogger().level == logging.INFO
