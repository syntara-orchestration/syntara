"""Integration tests for SettingsCache against a real PostgreSQL database.

Verifies the full round-trip: session factory → SettingsStore query →
value vs default_value resolution, exercising the real database path
that unit tests cover only with mocks.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import patch
from uuid import uuid4

import pytest

from syntara.settings.cache.settings_cache import SettingsCache
from syntara.settings.catalog import SETTINGS_CATALOG, SettingDefinition
from syntara.settings.exceptions import SettingTypeError
from syntara.settings.models.runtime_setting import RuntimeSetting, SettingCategory, SettingValueType

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from sqlmodel.ext.asyncio.session import AsyncSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@contextmanager
def _catalog_with_key(
    key: str,
    value_type: SettingValueType = SettingValueType.STRING,
) -> Generator[None, None, None]:
    """Temporarily register a test key in SETTINGS_CATALOG.

    Required so that SettingsCache.get() does not reject the key as unknown
    before it reaches the DB.  The catalog is restored after the context exits.
    """
    entry = SettingDefinition(
        key=key,
        name=f"Test {key}",
        category=SettingCategory.SYSTEM,
        value_type=value_type,
        default_value=None,
    )
    with patch("syntara.settings.catalog.SETTINGS_CATALOG", [*SETTINGS_CATALOG, entry]):
        yield


async def _seed_setting(
    session: AsyncSession,
    *,
    key: str,
    value: object = None,
    default_value: object = None,
    value_type: SettingValueType = SettingValueType.STRING,
    category: SettingCategory = SettingCategory.AI_LLM,
) -> RuntimeSetting:
    """Insert a RuntimeSetting row and return the refreshed instance."""
    setting = RuntimeSetting(
        id=uuid4(),
        name=f"Test {key}",
        key=key,
        category=category,
        value_type=value_type,
        value=value,
        default_value=default_value,
    )
    session.add(setting)
    await session.commit()
    await session.refresh(setting)
    return setting


# ---------------------------------------------------------------------------
# get() — value resolution against real DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_default_value_when_value_is_none(
    test_db_session: AsyncSession,
    test_session_factory: Callable[[], object],
) -> None:
    """get() returns default_value from a real DB row when value is NULL."""
    await _seed_setting(
        test_db_session,
        key="test.cache.default_only",
        default_value="the-default",
    )
    cache = SettingsCache(session_factory=test_session_factory)

    with _catalog_with_key("test.cache.default_only"):
        result = await cache.get("test.cache.default_only")

    assert result == "the-default"


@pytest.mark.asyncio
async def test_get_returns_value_when_set(
    test_db_session: AsyncSession,
    test_session_factory: Callable[[], object],
) -> None:
    """get() returns value (not default_value) when both are present."""
    await _seed_setting(
        test_db_session,
        key="test.cache.with_value",
        value="operator-override",
        default_value="the-default",
    )
    cache = SettingsCache(session_factory=test_session_factory)

    with _catalog_with_key("test.cache.with_value"):
        result = await cache.get("test.cache.with_value")

    assert result == "operator-override"


@pytest.mark.asyncio
async def test_get_raises_for_unknown_catalog_key(
    test_session_factory: Callable[[], object],
) -> None:
    """get() raises KeyError for keys not registered in the settings catalog."""
    cache = SettingsCache(session_factory=test_session_factory)

    with pytest.raises(KeyError, match="not in catalog"):
        await cache.get("test.cache.nonexistent")


@pytest.mark.asyncio
async def test_get_returns_none_when_both_value_and_default_are_none(
    test_db_session: AsyncSession,
    test_session_factory: Callable[[], object],
) -> None:
    """get() returns None when a catalog key exists but both DB columns are NULL."""
    await _seed_setting(
        test_db_session,
        key="test.cache.both_none",
        value=None,
        default_value=None,
    )
    cache = SettingsCache(session_factory=test_session_factory)

    with _catalog_with_key("test.cache.both_none"):
        result = await cache.get("test.cache.both_none")

    assert result is None


# ---------------------------------------------------------------------------
# Typed accessors — real DB round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_int_with_real_db(
    test_db_session: AsyncSession,
    test_session_factory: Callable[[], object],
) -> None:
    """get_int() returns an integer value from a real DB row."""
    await _seed_setting(
        test_db_session,
        key="test.cache.max_tokens",
        default_value=4096,
        value_type=SettingValueType.INTEGER,
    )
    cache = SettingsCache(session_factory=test_session_factory)

    with _catalog_with_key("test.cache.max_tokens", SettingValueType.INTEGER):
        result = await cache.get_int("test.cache.max_tokens")

    assert result == 4096
    assert isinstance(result, int)


@pytest.mark.asyncio
async def test_get_float_with_real_db(
    test_db_session: AsyncSession,
    test_session_factory: Callable[[], object],
) -> None:
    """get_float() returns a float value from a real DB row."""
    await _seed_setting(
        test_db_session,
        key="test.cache.temperature",
        value=0.9,
        default_value=0.7,
        value_type=SettingValueType.FLOAT,
    )
    cache = SettingsCache(session_factory=test_session_factory)

    with _catalog_with_key("test.cache.temperature", SettingValueType.FLOAT):
        result = await cache.get_float("test.cache.temperature")

    assert result == 0.9
    assert isinstance(result, float)


@pytest.mark.asyncio
async def test_get_str_with_real_db(
    test_db_session: AsyncSession,
    test_session_factory: Callable[[], object],
) -> None:
    """get_str() returns a string value from a real DB row."""
    await _seed_setting(
        test_db_session,
        key="test.cache.model_name",
        default_value="claude-3.5-sonnet",
        value_type=SettingValueType.STRING,
    )
    cache = SettingsCache(session_factory=test_session_factory)

    with _catalog_with_key("test.cache.model_name"):
        result = await cache.get_str("test.cache.model_name")

    assert result == "claude-3.5-sonnet"


@pytest.mark.asyncio
async def test_get_bool_with_real_db(
    test_db_session: AsyncSession,
    test_session_factory: Callable[[], object],
) -> None:
    """get_bool() returns a boolean value from a real DB row."""
    await _seed_setting(
        test_db_session,
        key="test.cache.feature_flag",
        default_value=True,
        value_type=SettingValueType.BOOLEAN,
    )
    cache = SettingsCache(session_factory=test_session_factory)

    with _catalog_with_key("test.cache.feature_flag", SettingValueType.BOOLEAN):
        result = await cache.get_bool("test.cache.feature_flag")

    assert result is True


@pytest.mark.asyncio
async def test_get_int_with_default_fallback(
    test_db_session: AsyncSession,
    test_session_factory: Callable[[], object],
) -> None:
    """get_int() returns the caller-supplied default when the DB row has no value set."""
    await _seed_setting(
        test_db_session,
        key="test.cache.missing_int",
        value=None,
        default_value=None,
        value_type=SettingValueType.INTEGER,
    )
    cache = SettingsCache(session_factory=test_session_factory)

    with _catalog_with_key("test.cache.missing_int", SettingValueType.INTEGER):
        result = await cache.get_int("test.cache.missing_int", default=42)

    assert result == 42


@pytest.mark.asyncio
async def test_get_int_raises_type_error_for_wrong_type(
    test_db_session: AsyncSession,
    test_session_factory: Callable[[], object],
) -> None:
    """get_int() raises SettingTypeError when the stored value is a string."""
    await _seed_setting(
        test_db_session,
        key="test.cache.wrong_type",
        default_value="not-an-int",
        value_type=SettingValueType.STRING,
    )
    cache = SettingsCache(session_factory=test_session_factory)

    with _catalog_with_key("test.cache.wrong_type", SettingValueType.INTEGER), pytest.raises(SettingTypeError):
        await cache.get_int("test.cache.wrong_type")
