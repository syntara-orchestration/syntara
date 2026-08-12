"""Unit tests for SettingsCache change notification and polling.

Tests cover:
- on_change rejects requires_restart=True settings
- on_change stores callbacks for later polling
- Poll detects change and fires callbacks
- Poll with no change does not fire callbacks
- Poll with DB error continues gracefully
- Callback errors don't crash the poll loop
- Async callbacks are awaited
- start_watching / stop_watching are idempotent
- First poll seeds cache without firing callbacks
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.settings.cache.settings_cache import _SENTINEL, SettingsCache


def _make_watching_cache() -> SettingsCache:
    """Create a SettingsCache for watching tests."""
    return SettingsCache(session_factory=AsyncMock(), default_ttl_seconds=60.0)


class TestOnChange:
    """Tests for on_change() callback registration."""

    def test_rejects_requires_restart_setting(self) -> None:
        """on_change raises ValueError for requires_restart=True settings."""
        cache = _make_watching_cache()

        # Patch catalog to have a requires_restart=True setting
        fake_defn = MagicMock()
        fake_defn.key = "test.restart"
        fake_defn.requires_restart = True

        cache._catalog_by_key = None
        with (
            patch("syntara.settings.catalog.SETTINGS_CATALOG", [fake_defn]),
            pytest.raises(ValueError, match="requires_restart=True"),
        ):
            cache.on_change("test.restart", lambda _k, _v: None)

    def test_stores_callback(self) -> None:
        """on_change stores the callback for later polling."""
        cache = _make_watching_cache()
        cb = MagicMock()

        cache.on_change("logging.log_level", cb)

        assert "logging.log_level" in cache._watchers
        assert cb in cache._watchers["logging.log_level"]

    def test_multiple_callbacks_for_same_key(self) -> None:
        """Multiple callbacks can be registered for the same key."""
        cache = _make_watching_cache()
        cb1 = MagicMock()
        cb2 = MagicMock()

        cache.on_change("logging.log_level", cb1)
        cache.on_change("logging.log_level", cb2)

        assert len(cache._watchers["logging.log_level"]) == 2


class TestPollWatchedKeys:
    """Tests for the _poll_watched_keys callback."""

    @pytest.mark.asyncio
    async def test_detects_change_and_fires_callback(self) -> None:
        """When DB value differs from watch_values, callback is invoked."""
        cache = _make_watching_cache()
        cb = MagicMock()
        cache.on_change("logging.log_level", cb)

        # Seed watch_values with old value (simulates a previous poll)
        cache._watch_values["logging.log_level"] = "INFO"

        with patch.object(cache, "_fetch_from_db", return_value="DEBUG"):
            await cache._poll_watched_keys(AsyncMock())

        cb.assert_called_once_with("logging.log_level", "DEBUG")

    @pytest.mark.asyncio
    async def test_no_change_does_not_fire_callback(self) -> None:
        """When DB value matches watch_values, callback is not invoked."""
        cache = _make_watching_cache()
        cb = MagicMock()
        cache.on_change("logging.log_level", cb)

        cache._watch_values["logging.log_level"] = "INFO"

        with patch.object(cache, "_fetch_from_db", return_value="INFO"):
            await cache._poll_watched_keys(AsyncMock())

        cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_first_poll_seeds_baseline_without_firing(self) -> None:
        """First poll for a previously-unset key establishes the baseline without firing callbacks."""
        cache = _make_watching_cache()
        cb = MagicMock()
        cache.on_change("logging.log_level", cb)

        # on_change does not seed watch_values when no cached value exists
        assert "logging.log_level" not in cache._watch_values

        with patch.object(cache, "_fetch_from_db", return_value="WARNING"):
            await cache._poll_watched_keys(AsyncMock())

        # Watch values updated to the DB value (baseline now set)
        assert cache._watch_values["logging.log_level"] == "WARNING"
        # Cache also updated
        assert cache._cache["logging.log_level"].value == "WARNING"
        # Callback does NOT fire — first poll is baseline establishment
        cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_error_keeps_stale_and_continues(self) -> None:
        """DB error for one key doesn't affect other watched keys."""
        cache = _make_watching_cache()
        cb_good = MagicMock()
        cb_bad = MagicMock()
        cache.on_change("good.key", cb_good)
        cache.on_change("bad.key", cb_bad)

        # Seed watch_values for both
        cache._watch_values["good.key"] = "old"
        cache._watch_values["bad.key"] = "old"

        async def fetch_side_effect(key: str) -> str:
            if key == "bad.key":
                msg = "DB down"
                raise ConnectionError(msg)
            return "new"

        with patch.object(cache, "_fetch_from_db", side_effect=fetch_side_effect):
            await cache._poll_watched_keys(AsyncMock())

        # good.key changed and callback fired
        cb_good.assert_called_once_with("good.key", "new")
        # bad.key errored, callback not fired, stale value preserved
        cb_bad.assert_not_called()
        assert cache._watch_values["bad.key"] == "old"

    @pytest.mark.asyncio
    async def test_callback_error_does_not_crash_poll(self) -> None:
        """A callback exception is logged but doesn't stop other callbacks."""
        cache = _make_watching_cache()
        cb_bad = MagicMock(side_effect=RuntimeError("boom"))
        cb_good = MagicMock()
        cache.on_change("logging.log_level", cb_bad)
        cache.on_change("logging.log_level", cb_good)

        cache._watch_values["logging.log_level"] = "INFO"

        with patch.object(cache, "_fetch_from_db", return_value="DEBUG"):
            await cache._poll_watched_keys(AsyncMock())

        # Both callbacks were invoked despite the first one raising
        cb_bad.assert_called_once()
        cb_good.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_callback_is_awaited(self) -> None:
        """Async callbacks are properly awaited."""
        cache = _make_watching_cache()
        cb = AsyncMock()
        cache.on_change("logging.log_level", cb)

        cache._watch_values["logging.log_level"] = "INFO"

        with patch.object(cache, "_fetch_from_db", return_value="DEBUG"):
            await cache._poll_watched_keys(AsyncMock())

        cb.assert_awaited_once_with("logging.log_level", "DEBUG")

    @pytest.mark.asyncio
    async def test_empty_watchers_is_noop(self) -> None:
        """Poll with no registered watchers does nothing."""
        cache = _make_watching_cache()

        with patch.object(cache, "_fetch_from_db") as mock_fetch:
            await cache._poll_watched_keys(AsyncMock())

        mock_fetch.assert_not_called()


class TestStartStopWatching:
    """Tests for start_watching() / stop_watching() lifecycle."""

    @pytest.mark.asyncio
    async def test_start_watching_is_idempotent(self) -> None:
        """Calling start_watching twice schedules only one startup."""
        cache = _make_watching_cache()

        with patch.object(cache, "_start_watching_async", new_callable=AsyncMock) as mock_start:
            cache.start_watching()
            cache.start_watching()  # second call should be a no-op

        mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_watching_is_idempotent(self) -> None:
        """Calling stop_watching when not started does nothing."""
        cache = _make_watching_cache()
        await cache.stop_watching()  # should not raise

    @pytest.mark.asyncio
    async def test_stop_watching_stops_worker(self) -> None:
        """stop_watching stops the PeriodicWorker."""
        cache = _make_watching_cache()
        mock_worker = AsyncMock()
        cache._poll_worker = mock_worker

        await cache.stop_watching()

        mock_worker.stop.assert_awaited_once()
        assert cache._poll_worker is None


class TestSentinel:
    """Test that _SENTINEL is a unique marker."""

    def test_sentinel_is_not_none(self) -> None:
        assert _SENTINEL is not None

    def test_sentinel_is_unique(self) -> None:
        assert _SENTINEL != "any string"
        assert _SENTINEL != 0
