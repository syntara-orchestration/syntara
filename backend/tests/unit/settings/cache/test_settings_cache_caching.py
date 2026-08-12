"""Unit tests for SettingsCache in-memory caching behaviour.

Tests cover:
- Cache hit avoids DB query
- TTL expiry triggers re-fetch
- requires_restart=True settings cached forever
- DB unavailable with stale cache serves stale
- DB unavailable with empty cache propagates exception
- invalidate() forces re-fetch
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.settings.cache.settings_cache import CachedValue, SettingsCache


def _make_cache(store_return: object = None) -> tuple[SettingsCache, AsyncMock]:
    """Create a SettingsCache with a mocked SettingsStore.get().

    Returns the cache and the mock for SettingsStore.get().
    """
    mock_session = AsyncMock()
    mock_store_get = AsyncMock(return_value=store_return)

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=None)

    def session_factory() -> AsyncMock:
        return ctx

    cache = SettingsCache(session_factory=session_factory, default_ttl_seconds=60.0)

    with patch("syntara.settings.cache.settings_cache.SettingsStore") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.get = mock_store_get
        mock_cls.return_value = mock_instance
        # Return via closure so tests can use the patched context
        cache._mock_store_cls = mock_cls  # type: ignore[attr-defined]
        cache._mock_store_get = mock_store_get  # type: ignore[attr-defined]

    return cache, mock_store_get


@pytest.mark.asyncio
async def test_cache_hit_skips_db() -> None:
    """Second get() for the same key returns cached value without DB query."""
    mock_setting = MagicMock()
    mock_setting.value = "WARNING"
    mock_setting.default_value = "INFO"

    cache, _ = _make_cache()

    with patch("syntara.settings.cache.settings_cache.SettingsStore") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.get = AsyncMock(return_value=mock_setting)
        mock_cls.return_value = mock_instance

        # First call — fetches from DB
        result1 = await cache.get("logging.log_level")
        assert result1 == "WARNING"
        assert mock_instance.get.call_count == 1

        # Second call — cache hit, no DB
        result2 = await cache.get("logging.log_level")
        assert result2 == "WARNING"
        assert mock_instance.get.call_count == 1  # still 1


@pytest.mark.asyncio
async def test_ttl_expiry_triggers_refetch() -> None:
    """After TTL expires, get() fetches from DB again."""
    mock_setting = MagicMock()
    mock_setting.value = "DEBUG"
    mock_setting.default_value = "INFO"

    cache, _ = _make_cache()

    with patch("syntara.settings.cache.settings_cache.SettingsStore") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.get = AsyncMock(return_value=mock_setting)
        mock_cls.return_value = mock_instance

        # First call — populates cache
        await cache.get("logging.log_level")
        assert mock_instance.get.call_count == 1

        # Expire the cache entry
        cached = cache._cache["logging.log_level"]
        cached.fetched_at -= cached.ttl_seconds + 1

        # Next call — refetches
        await cache.get("logging.log_level")
        assert mock_instance.get.call_count == 2


@pytest.mark.asyncio
async def test_requires_restart_cached_forever() -> None:
    """Settings with requires_restart=True never expire."""
    cache = SettingsCache(session_factory=AsyncMock(), default_ttl_seconds=10.0)

    # Manually insert a cached value with inf TTL (simulates a requires_restart setting)
    cache._cache["logging.log_level"] = CachedValue(
        value="immutable",
        fetched_at=0.0,  # very old
        ttl_seconds=float("inf"),
    )

    result = await cache.get("logging.log_level")
    assert result == "immutable"


@pytest.mark.asyncio
async def test_db_unavailable_serves_stale() -> None:
    """When DB is down but stale cache exists, return stale value."""
    cache = SettingsCache(session_factory=AsyncMock(), default_ttl_seconds=60.0)

    # Seed a stale cache entry for a known catalog key
    cache._cache["logging.log_level"] = CachedValue(
        value="stale_value",
        fetched_at=0.0,  # expired
        ttl_seconds=1.0,
    )

    with patch.object(cache, "_fetch_from_db", side_effect=ConnectionError("DB down")):
        result = await cache.get("logging.log_level")
        assert result == "stale_value"


@pytest.mark.asyncio
async def test_db_unavailable_no_cache_propagates() -> None:
    """When DB is down and no cache exists, exception propagates."""
    cache = SettingsCache(session_factory=AsyncMock(), default_ttl_seconds=60.0)

    with (
        patch.object(cache, "_fetch_from_db", side_effect=ConnectionError("DB down")),
        pytest.raises(ConnectionError, match="DB down"),
    ):
        await cache.get("logging.log_level")


@pytest.mark.asyncio
async def test_invalidate_forces_refetch() -> None:
    """invalidate() evicts the cache entry so next get() hits DB."""
    mock_setting = MagicMock()
    mock_setting.value = "ERROR"
    mock_setting.default_value = "INFO"

    cache, _ = _make_cache()

    with patch("syntara.settings.cache.settings_cache.SettingsStore") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.get = AsyncMock(return_value=mock_setting)
        mock_cls.return_value = mock_instance

        await cache.get("logging.log_level")
        assert mock_instance.get.call_count == 1

        await cache.invalidate("logging.log_level")
        assert "logging.log_level" not in cache._cache

        await cache.get("logging.log_level")
        assert mock_instance.get.call_count == 2


class TestCachedValue:
    """Tests for the CachedValue dataclass."""

    def test_fresh_within_ttl(self) -> None:
        import time

        cv = CachedValue(value="v", fetched_at=time.monotonic(), ttl_seconds=60.0)
        assert cv.is_fresh() is True

    def test_stale_after_ttl(self) -> None:
        cv = CachedValue(value="v", fetched_at=0.0, ttl_seconds=1.0)
        assert cv.is_fresh() is False

    def test_infinite_ttl_always_fresh(self) -> None:
        cv = CachedValue(value="v", fetched_at=0.0, ttl_seconds=float("inf"))
        assert cv.is_fresh() is True
