"""Unit tests for SettingsCache.

Tests cover:
- get() reads from DB and returns resolved value
- get() raises KeyError for unknown catalog keys
- invalidate() is a safe no-op
- get_runtime_settings() / set_runtime_settings() singleton management
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.settings.cache.settings_cache import (
    CachedValue,
    SettingsCache,
    get_runtime_settings,
    set_runtime_settings,
)
from syntara.settings.models.runtime_setting import RuntimeSetting, SettingCategory, SettingValueType


def _make_setting(
    key: str = "logging.log_level",
    value: object = None,
    default_value: object = "INFO",
) -> RuntimeSetting:
    """Build an unsaved RuntimeSetting for use in mock returns."""
    return RuntimeSetting(
        id=uuid4(),
        name="Test Setting",
        key=key,
        category=SettingCategory.AI_LLM,
        value_type=SettingValueType.STRING,
        value=value,
        default_value=default_value,
    )


@pytest.fixture
def mock_session_factory() -> MagicMock:
    """A mock async_sessionmaker."""
    return MagicMock()


@pytest.fixture
def cache(mock_session_factory: MagicMock) -> SettingsCache:
    """A SettingsCache wired to a mock session factory."""
    return SettingsCache(session_factory=mock_session_factory)


# ---------------------------------------------------------------------------
# get() — DB reads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_default_value_when_value_is_none(cache: SettingsCache) -> None:
    """get() returns default_value when value is None."""
    setting = _make_setting(value=None, default_value="INFO")

    mock_store = AsyncMock()
    mock_store.get = AsyncMock(return_value=setting)

    with patch(
        "syntara.settings.cache.settings_cache.SettingsStore",
        return_value=mock_store,
    ):
        result = await cache.get("logging.log_level")

    assert result == "INFO"


@pytest.mark.asyncio
async def test_get_returns_value_when_set(cache: SettingsCache) -> None:
    """get() returns value when it is set (not None)."""
    setting = _make_setting(value="WARNING", default_value="INFO")

    mock_store = AsyncMock()
    mock_store.get = AsyncMock(return_value=setting)

    with patch(
        "syntara.settings.cache.settings_cache.SettingsStore",
        return_value=mock_store,
    ):
        result = await cache.get("logging.log_level")

    assert result == "WARNING"


@pytest.mark.asyncio
async def test_get_raises_for_unknown_key(cache: SettingsCache) -> None:
    """get() raises KeyError immediately for keys not in the catalog, without hitting the DB."""
    mock_store = AsyncMock()
    mock_store.get = AsyncMock(return_value=None)

    with (
        patch(
            "syntara.settings.cache.settings_cache.SettingsStore",
            return_value=mock_store,
        ),
        pytest.raises(KeyError, match="not in catalog"),
    ):
        await cache.get("does.not.exist")

    mock_store.get.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_key_not_cached(cache: SettingsCache) -> None:
    """Unknown keys are not stored in L1, keeping the cache bounded."""
    with patch("syntara.settings.cache.settings_cache.SettingsStore"), pytest.raises(KeyError):
        await cache.get("attacker.injected.key")

    assert "attacker.injected.key" not in cache._cache


# ---------------------------------------------------------------------------
# get_cached() — synchronous L1 read
# ---------------------------------------------------------------------------


def test_get_cached_returns_value_when_populated(cache: SettingsCache) -> None:
    """get_cached() returns the cached value from L1."""
    cache._cache["logging.log_level"] = CachedValue(value="DEBUG", fetched_at=0, ttl_seconds=60)
    assert cache.get_cached("logging.log_level") == "DEBUG"


def test_get_cached_returns_none_on_miss(cache: SettingsCache) -> None:
    """get_cached() returns None when the key is not in L1."""
    assert cache.get_cached("logging.log_level") is None


# ---------------------------------------------------------------------------
# invalidate() — no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalidate_noop_does_not_raise(cache: SettingsCache) -> None:
    """invalidate() on any key does not raise."""
    await cache.invalidate("any.key")


# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------


def test_get_runtime_settings_raises_when_not_initialised() -> None:
    """get_runtime_settings() raises RuntimeError before set_runtime_settings() is called."""
    set_runtime_settings(None)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="SettingsCache has not been initialised"):
        get_runtime_settings()


def test_set_and_get_runtime_settings(mock_session_factory: MagicMock) -> None:
    """set_runtime_settings() registers the singleton returned by get_runtime_settings()."""
    cache = SettingsCache(session_factory=mock_session_factory)
    set_runtime_settings(cache)

    assert get_runtime_settings() is cache

    # cleanup
    set_runtime_settings(None)  # type: ignore[arg-type]


def test_set_runtime_settings_replaces_existing(mock_session_factory: MagicMock) -> None:
    """Calling set_runtime_settings() a second time replaces the previous singleton."""
    first = SettingsCache(session_factory=mock_session_factory)
    second = SettingsCache(session_factory=mock_session_factory)

    set_runtime_settings(first)
    assert get_runtime_settings() is first

    set_runtime_settings(second)
    assert get_runtime_settings() is second

    # cleanup
    set_runtime_settings(None)  # type: ignore[arg-type]
