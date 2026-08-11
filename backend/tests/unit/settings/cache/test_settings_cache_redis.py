"""Unit tests for SettingsCache Redis L2 cache and Pub/Sub integration.

Tests cover:
- L2 cache hit avoids DB query
- L2 miss falls through to DB and populates L2
- Redis error falls through to DB gracefully
- invalidate() clears both L1 and L2
- Pub/Sub listener handles change notifications
- publish_change sends to Redis channel
- publish_change tolerates Redis errors
- start_watching uses Pub/Sub when Redis available
- start_watching falls back to polling when Redis unavailable
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.settings.cache.settings_cache import (
    REDIS_CHANNEL,
    REDIS_KEY_PREFIX,
    SettingsCache,
    _compute_hmac,
    _verify_hmac,
)


def _make_redis_client() -> AsyncMock:
    """Create a mock SettingsRedisClient with both cache and pubsub methods."""
    client = AsyncMock()
    # CacheMixin methods
    client.cache_get = AsyncMock(return_value=None)
    client.cache_setex = AsyncMock()
    client.cache_delete = AsyncMock()
    # PubSubMixin methods
    client.pubsub_publish = AsyncMock()
    client.pubsub_subscribe = AsyncMock()
    client.ping = AsyncMock()
    # Lifecycle
    client.connect = MagicMock()
    client.disconnect = AsyncMock()
    return client


def _make_redis_cache(
    *,
    redis_client: AsyncMock | None = None,
) -> SettingsCache:
    """Create a SettingsCache with a mocked SettingsRedisClient injected."""
    cache = SettingsCache(
        session_factory=AsyncMock(),
        default_ttl_seconds=60.0,
        redis_enabled=False,
    )
    cache._redis_client = redis_client if redis_client is not None else _make_redis_client()
    return cache


class TestRedisL2Cache:
    """Tests for Redis L2 cache read/write behaviour."""

    @pytest.mark.asyncio
    async def test_l2_hit_avoids_db(self) -> None:
        """When L1 misses but L2 has the value, DB is not queried."""
        rc = _make_redis_client()
        rc.cache_get = AsyncMock(return_value=json.dumps("DEBUG"))
        cache = _make_redis_cache(redis_client=rc)

        with patch.object(cache, "_fetch_from_db") as mock_db:
            result = await cache.get("logging.log_level")

        assert result == "DEBUG"
        mock_db.assert_not_called()
        rc.cache_get.assert_called_once_with(f"{REDIS_KEY_PREFIX}logging.log_level")

    @pytest.mark.asyncio
    async def test_l2_miss_fetches_from_db_and_populates_l2(self) -> None:
        """L2 miss falls through to DB, then stores in both L1 and L2."""
        rc = _make_redis_client()
        cache = _make_redis_cache(redis_client=rc)

        with patch.object(cache, "_fetch_from_db", return_value="WARNING"):
            result = await cache.get("logging.log_level")

        assert result == "WARNING"
        assert cache._cache["logging.log_level"].value == "WARNING"
        rc.cache_setex.assert_called_once()
        call_args = rc.cache_setex.call_args
        assert call_args[0][0] == f"{REDIS_KEY_PREFIX}logging.log_level"
        assert json.loads(call_args[0][2]) == "WARNING"

    @pytest.mark.asyncio
    async def test_l1_hit_skips_l2_and_db(self) -> None:
        """When L1 has a fresh value, neither L2 nor DB is queried."""
        rc = _make_redis_client()
        cache = _make_redis_cache(redis_client=rc)

        with patch.object(cache, "_fetch_from_db", return_value="INFO"):
            await cache.get("logging.log_level")

        rc.cache_get.reset_mock()

        with patch.object(cache, "_fetch_from_db") as mock_db:
            result = await cache.get("logging.log_level")

        assert result == "INFO"
        rc.cache_get.assert_not_called()
        mock_db.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_error_falls_through_to_db(self) -> None:
        """Redis error on L2 get silently falls through to DB."""
        rc = _make_redis_client()
        rc.cache_get = AsyncMock(side_effect=ConnectionError("Redis down"))
        rc.cache_setex = AsyncMock(side_effect=ConnectionError("Redis down"))
        cache = _make_redis_cache(redis_client=rc)

        with patch.object(cache, "_fetch_from_db", return_value="ERROR"):
            result = await cache.get("logging.log_level")

        assert result == "ERROR"
        assert cache._cache["logging.log_level"].value == "ERROR"

    @pytest.mark.asyncio
    async def test_no_redis_client_skips_l2(self) -> None:
        """When redis_client is None, L2 is skipped entirely."""
        cache = SettingsCache(
            session_factory=AsyncMock(),
            default_ttl_seconds=60.0,
            redis_enabled=False,
        )

        with patch.object(cache, "_fetch_from_db", return_value="DEBUG"):
            result = await cache.get("logging.log_level")

        assert result == "DEBUG"

    @pytest.mark.asyncio
    async def test_requires_restart_not_cached_in_l2(self) -> None:
        """Settings with requires_restart=True are not stored in Redis L2."""
        rc = _make_redis_client()
        cache = _make_redis_cache(redis_client=rc)

        fake_defn = MagicMock()
        fake_defn.key = "test.restart"
        fake_defn.requires_restart = True

        cache._catalog_by_key = None
        with (
            patch("syntara.settings.catalog.SETTINGS_CATALOG", [fake_defn]),
            patch.object(cache, "_fetch_from_db", return_value="immutable"),
        ):
            await cache.get("test.restart")

        rc.cache_setex.assert_not_called()


class TestInvalidate:
    """Tests for invalidate() clearing both L1 and L2."""

    @pytest.mark.asyncio
    async def test_invalidate_clears_l1_and_l2(self) -> None:
        """invalidate() evicts from both in-memory and Redis caches."""
        rc = _make_redis_client()
        cache = _make_redis_cache(redis_client=rc)

        with patch.object(cache, "_fetch_from_db", return_value="v1"):
            await cache.get("logging.log_level")

        assert "logging.log_level" in cache._cache

        await cache.invalidate("logging.log_level")

        assert "logging.log_level" not in cache._cache
        rc.cache_delete.assert_called_once_with(f"{REDIS_KEY_PREFIX}logging.log_level")

    @pytest.mark.asyncio
    async def test_invalidate_tolerates_redis_error(self) -> None:
        """invalidate() doesn't raise when Redis delete fails."""
        rc = _make_redis_client()
        rc.cache_delete = AsyncMock(side_effect=ConnectionError("Redis down"))
        cache = _make_redis_cache(redis_client=rc)

        cache._cache["test.key"] = MagicMock()

        await cache.invalidate("test.key")
        assert "test.key" not in cache._cache


class TestPublishChange:
    """Tests for publish_change()."""

    @pytest.mark.asyncio
    async def test_publishes_to_channel(self) -> None:
        """publish_change sends HMAC-signed JSON payload to the Redis channel."""
        rc = _make_redis_client()
        cache = _make_redis_cache(redis_client=rc)

        await cache.publish_change("logging.log_level")

        rc.pubsub_publish.assert_called_once()
        channel, payload = rc.pubsub_publish.call_args[0]
        assert channel == REDIS_CHANNEL
        parsed = json.loads(payload)
        assert parsed["key"] == "logging.log_level"
        assert "mac" in parsed
        canonical = json.dumps({"key": "logging.log_level"})
        assert _verify_hmac(canonical, parsed["mac"])

    @pytest.mark.asyncio
    async def test_publish_tolerates_redis_error(self) -> None:
        """publish_change swallows Redis errors."""
        rc = _make_redis_client()
        rc.pubsub_publish = AsyncMock(side_effect=ConnectionError("Redis down"))
        cache = _make_redis_cache(redis_client=rc)

        await cache.publish_change("logging.log_level")

    @pytest.mark.asyncio
    async def test_publish_noop_without_redis_client(self) -> None:
        """publish_change is a no-op when redis_client is None."""
        cache = SettingsCache(
            session_factory=AsyncMock(),
            default_ttl_seconds=60.0,
            redis_enabled=False,
        )
        await cache.publish_change("logging.log_level")


class TestPubSubHMAC:
    """Tests for HMAC signing and verification of Pub/Sub messages."""

    def test_compute_hmac_returns_hex_digest(self) -> None:
        """_compute_hmac returns a consistent hex digest."""
        mac = _compute_hmac('{"key": "test.key"}')
        assert isinstance(mac, str)
        assert len(mac) == 64  # SHA-256 hex digest

    def test_verify_hmac_accepts_valid(self) -> None:
        """_verify_hmac returns True for a correctly signed payload."""
        payload = '{"key": "test.key"}'
        mac = _compute_hmac(payload)
        assert _verify_hmac(payload, mac)

    def test_verify_hmac_rejects_tampered(self) -> None:
        """_verify_hmac returns False when the payload has been tampered."""
        mac = _compute_hmac('{"key": "original"}')
        assert not _verify_hmac('{"key": "tampered"}', mac)

    def test_verify_hmac_rejects_wrong_mac(self) -> None:
        """_verify_hmac returns False for an incorrect MAC."""
        payload = '{"key": "test.key"}'
        assert not _verify_hmac(payload, "0" * 64)

    @pytest.mark.asyncio
    async def test_listener_rejects_unsigned_message(self) -> None:
        """Messages without a mac field are rejected."""
        rc = _make_redis_client()
        cache = _make_redis_cache(redis_client=rc)

        pubsub = AsyncMock()
        unsigned_msg = {
            "type": "message",
            "data": json.dumps({"key": "test.key"}),
        }
        pubsub.get_message = AsyncMock(side_effect=[unsigned_msg, asyncio.CancelledError])
        cache._pubsub = pubsub

        with pytest.raises(asyncio.CancelledError):
            await cache._pubsub_listener()

    @pytest.mark.asyncio
    async def test_listener_rejects_invalid_mac(self) -> None:
        """Messages with an invalid mac are rejected."""
        rc = _make_redis_client()
        cache = _make_redis_cache(redis_client=rc)

        pubsub = AsyncMock()
        bad_mac_msg = {
            "type": "message",
            "data": json.dumps({"key": "test.key", "mac": "0" * 64}),
        }
        pubsub.get_message = AsyncMock(side_effect=[bad_mac_msg, asyncio.CancelledError])
        cache._pubsub = pubsub

        with pytest.raises(asyncio.CancelledError):
            await cache._pubsub_listener()

    @pytest.mark.asyncio
    async def test_listener_accepts_valid_mac(self) -> None:
        """Messages with a valid mac are processed."""
        rc = _make_redis_client()
        cache = _make_redis_cache(redis_client=rc)

        canonical = json.dumps({"key": "logging.log_level"})
        mac = _compute_hmac(canonical)
        valid_msg = {
            "type": "message",
            "data": json.dumps({"key": "logging.log_level", "mac": mac}),
        }

        pubsub = AsyncMock()
        pubsub.get_message = AsyncMock(side_effect=[valid_msg, asyncio.CancelledError])
        cache._pubsub = pubsub

        with (
            patch.object(cache, "_handle_change_notification", new_callable=AsyncMock) as mock_handle,
            pytest.raises(asyncio.CancelledError),
        ):
            await cache._pubsub_listener()

        mock_handle.assert_called_once_with("logging.log_level")


class TestHandleChangeNotification:
    """Tests for _handle_change_notification (Pub/Sub message processing)."""

    @pytest.mark.asyncio
    async def test_refetches_from_db_and_fires_callback(self) -> None:
        """Change notification re-fetches from DB and fires registered callbacks."""
        cache = _make_redis_cache()
        cb = MagicMock()
        cache.on_change("logging.log_level", cb)
        cache._watch_values["logging.log_level"] = "INFO"

        with patch.object(cache, "_fetch_from_db", new_callable=AsyncMock, return_value="DEBUG"):
            await cache._handle_change_notification("logging.log_level")

        assert cache._cache["logging.log_level"].value == "DEBUG"
        cb.assert_called_once_with("logging.log_level", "DEBUG")

    @pytest.mark.asyncio
    async def test_no_callback_when_value_unchanged(self) -> None:
        """No callback is fired when the DB value hasn't actually changed."""
        cache = _make_redis_cache()
        cb = MagicMock()
        cache.on_change("logging.log_level", cb)
        cache._watch_values["logging.log_level"] = "INFO"

        with patch.object(cache, "_fetch_from_db", new_callable=AsyncMock, return_value="INFO"):
            await cache._handle_change_notification("logging.log_level")

        cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_first_notification_seeds_baseline_without_firing(self) -> None:
        """First notification for a previously-unset key establishes baseline without firing."""
        cache = _make_redis_cache()
        cb = MagicMock()
        cache.on_change("logging.log_level", cb)

        with patch.object(cache, "_fetch_from_db", new_callable=AsyncMock, return_value="DEBUG"):
            await cache._handle_change_notification("logging.log_level")

        # Baseline is now set to the DB value
        assert cache._watch_values["logging.log_level"] == "DEBUG"
        # Callback does NOT fire — first notification is baseline establishment
        cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_unwatched_key_updates_cache_only(self) -> None:
        """Notification for an unwatched key still updates L1 cache."""
        cache = _make_redis_cache()

        with patch.object(cache, "_fetch_from_db", new_callable=AsyncMock, return_value="new_value"):
            await cache._handle_change_notification("unwatched.key")

        assert cache._cache["unwatched.key"].value == "new_value"

    @pytest.mark.asyncio
    async def test_db_error_is_handled_gracefully(self) -> None:
        """When DB is unreachable during re-fetch, notification is skipped."""
        cache = _make_redis_cache()
        cache._watch_values["logging.log_level"] = "INFO"

        # Pre-populate L1 cache with the existing value
        from syntara.settings.cache.settings_cache import CachedValue

        cache._cache["logging.log_level"] = CachedValue(value="INFO", fetched_at=0.0, ttl_seconds=60.0)

        with patch.object(cache, "_fetch_from_db", new_callable=AsyncMock, side_effect=ConnectionError("DB down")):
            await cache._handle_change_notification("logging.log_level")

        # Existing cache entry should be preserved (not evicted)
        assert cache._cache["logging.log_level"].value == "INFO"


class TestPubSubListenerCrash:
    """Tests for _pubsub_listener crash-and-cleanup path."""

    @pytest.mark.asyncio
    async def test_listener_crash_cleans_up_pubsub(self) -> None:
        """When the listener crashes, stale pubsub is cleaned up for reconnection."""
        cache = _make_redis_cache()
        mock_pubsub = AsyncMock()

        # Simulate get_message raising an unexpected error
        mock_pubsub.get_message = AsyncMock(side_effect=RuntimeError("unexpected"))
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.aclose = AsyncMock()
        cache._pubsub = mock_pubsub

        await cache._pubsub_listener()

        # Pubsub should be cleaned up so _maybe_reconnect_pubsub can retry
        assert cache._pubsub is None
        mock_pubsub.unsubscribe.assert_awaited_once()
        mock_pubsub.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_listener_propagates_cancelled_error(self) -> None:
        """CancelledError is re-raised for clean shutdown."""
        cache = _make_redis_cache()
        mock_pubsub = AsyncMock()
        mock_pubsub.get_message = AsyncMock(side_effect=asyncio.CancelledError)
        cache._pubsub = mock_pubsub

        with pytest.raises(asyncio.CancelledError):
            await cache._pubsub_listener()

    @pytest.mark.asyncio
    async def test_listener_crash_tolerates_cleanup_failure(self) -> None:
        """If cleanup itself fails, pubsub is still set to None."""
        cache = _make_redis_cache()
        mock_pubsub = AsyncMock()
        mock_pubsub.get_message = AsyncMock(side_effect=RuntimeError("crash"))
        mock_pubsub.unsubscribe = AsyncMock(side_effect=Exception("cleanup failed"))
        cache._pubsub = mock_pubsub

        await cache._pubsub_listener()

        assert cache._pubsub is None


class TestStartWatchingAsync:
    """Tests for _start_watching_async."""

    @pytest.mark.asyncio
    async def test_starts_polling_and_pubsub_when_redis_available(self) -> None:
        """When Redis is available, both polling and Pub/Sub are started."""
        rc = _make_redis_client()
        pubsub_obj = AsyncMock()
        pubsub_obj.get_message = AsyncMock(return_value=None)
        rc.pubsub_subscribe = AsyncMock(return_value=pubsub_obj)

        cache = _make_redis_cache(redis_client=rc)

        with patch("syntara.core.workers.periodic.PeriodicWorker") as mock_pw:
            mock_worker = AsyncMock()
            mock_pw.return_value = mock_worker
            await cache._start_watching_async()

        assert cache._pubsub_task is not None
        rc.pubsub_subscribe.assert_called_once_with(REDIS_CHANNEL)
        mock_pw.assert_called_once()

        await cache.stop_watching()

    @pytest.mark.asyncio
    async def test_starts_polling_only_when_redis_unavailable(self) -> None:
        """When Redis ping fails, polling still starts but no Pub/Sub."""
        rc = _make_redis_client()
        rc.ping = AsyncMock(side_effect=ConnectionError("Redis down"))

        cache = _make_redis_cache(redis_client=rc)

        with patch("syntara.core.workers.periodic.PeriodicWorker") as mock_pw:
            mock_worker = MagicMock()
            mock_pw.return_value = mock_worker
            await cache._start_watching_async()

        assert cache._pubsub_task is None
        mock_pw.assert_called_once()

    @pytest.mark.asyncio
    async def test_starts_polling_only_when_subscribe_fails(self) -> None:
        """When ping succeeds but subscribe fails, polling still starts."""
        rc = _make_redis_client()
        rc.pubsub_subscribe = AsyncMock(side_effect=ConnectionError("subscribe failed"))

        cache = _make_redis_cache(redis_client=rc)

        with patch("syntara.core.workers.periodic.PeriodicWorker") as mock_pw:
            mock_worker = MagicMock()
            mock_pw.return_value = mock_worker
            await cache._start_watching_async()

        assert cache._pubsub_task is None
        assert cache._pubsub is None
        mock_pw.assert_called_once()

    @pytest.mark.asyncio
    async def test_starts_polling_only_without_redis_client(self) -> None:
        """When redis_client is None, polling starts but no Pub/Sub."""
        cache = SettingsCache(
            session_factory=AsyncMock(),
            default_ttl_seconds=60.0,
            redis_enabled=False,
        )

        with patch("syntara.core.workers.periodic.PeriodicWorker") as mock_pw:
            mock_worker = MagicMock()
            mock_pw.return_value = mock_worker
            await cache._start_watching_async()

        assert cache._pubsub_task is None
        mock_pw.assert_called_once()


class TestMaybeReconnectPubsub:
    """Tests for _maybe_reconnect_pubsub."""

    @pytest.mark.asyncio
    async def test_reconnects_when_task_is_done(self) -> None:
        """Reconnects pub/sub when the listener task has completed (died)."""
        rc = _make_redis_client()
        pubsub_obj = AsyncMock()
        pubsub_obj.get_message = AsyncMock(return_value=None)
        rc.pubsub_subscribe = AsyncMock(return_value=pubsub_obj)
        cache = _make_redis_cache(redis_client=rc)

        # Simulate a dead listener task
        async def _noop() -> None:
            pass

        done_task = asyncio.create_task(_noop())
        await done_task
        cache._pubsub_task = done_task

        await cache._maybe_reconnect_pubsub()

        # Should have started a new pub/sub subscription
        rc.pubsub_subscribe.assert_called_once_with(REDIS_CHANNEL)
        assert cache._pubsub_task is not None
        assert cache._pubsub_task is not done_task

        await cache._stop_pubsub()

    @pytest.mark.asyncio
    async def test_noop_when_task_is_running(self) -> None:
        """Does nothing when the listener task is still running."""
        rc = _make_redis_client()
        cache = _make_redis_cache(redis_client=rc)

        cancel_event = asyncio.Event()

        async def _block() -> None:
            await cancel_event.wait()

        running_task = asyncio.create_task(_block())
        cache._pubsub_task = running_task

        await cache._maybe_reconnect_pubsub()

        # Should not have tried to subscribe again
        rc.pubsub_subscribe.assert_not_called()

        running_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await running_task

    @pytest.mark.asyncio
    async def test_acquires_redis_client_when_none(self) -> None:
        """Attempts to create a Redis client when redis_client is None."""
        cache = SettingsCache(
            session_factory=AsyncMock(),
            default_ttl_seconds=60.0,
            redis_enabled=True,
        )

        mock_client = _make_redis_client()
        with patch(
            "syntara.core.cache.settings_client.SettingsRedisClient",
            return_value=mock_client,
        ):
            # After acquiring, it should also try to start pubsub
            pubsub_obj = AsyncMock()
            pubsub_obj.get_message = AsyncMock(return_value=None)
            mock_client.pubsub_subscribe = AsyncMock(return_value=pubsub_obj)
            await cache._maybe_reconnect_pubsub()

        assert cache._redis_client is mock_client
        assert cache._redis_warned is False

        await cache._stop_pubsub()

    @pytest.mark.asyncio
    async def test_tolerates_redis_acquisition_failure(self) -> None:
        """Silently handles failure when trying to acquire a Redis client."""
        cache = SettingsCache(
            session_factory=AsyncMock(),
            default_ttl_seconds=60.0,
            redis_enabled=True,
        )

        mock_client = _make_redis_client()
        mock_client.ping = AsyncMock(side_effect=ConnectionError("still down"))
        with patch(
            "syntara.core.cache.settings_client.SettingsRedisClient",
            return_value=mock_client,
        ):
            await cache._maybe_reconnect_pubsub()

        assert cache._redis_client is None
        assert cache._redis_warned is True

    @pytest.mark.asyncio
    async def test_tolerates_reconnect_failure(self) -> None:
        """Swallows errors when Redis is still down during reconnect."""
        rc = _make_redis_client()
        rc.ping = AsyncMock(side_effect=ConnectionError("still down"))
        cache = _make_redis_cache(redis_client=rc)

        # Simulate dead task
        async def _noop() -> None:
            pass

        done_task = asyncio.create_task(_noop())
        await done_task
        cache._pubsub_task = done_task

        # Should not raise
        await cache._maybe_reconnect_pubsub()
        assert cache._pubsub_task is None


class TestStopWatching:
    """Tests for stop_watching() cleanup."""

    @pytest.mark.asyncio
    async def test_stops_pubsub_and_poll_worker(self) -> None:
        """stop_watching cleans up both Pub/Sub and poll worker."""
        cache = _make_redis_cache()
        mock_worker = AsyncMock()
        cache._poll_worker = mock_worker

        cancel_event = asyncio.Event()

        async def _block() -> None:
            await cancel_event.wait()

        real_task = asyncio.create_task(_block())
        cache._pubsub_task = real_task

        mock_pubsub = AsyncMock()
        cache._pubsub = mock_pubsub

        await cache.stop_watching()

        assert real_task.cancelled()
        mock_worker.stop.assert_awaited_once()
        assert cache._poll_worker is None
        assert cache._pubsub_task is None
        assert cache._pubsub is None  # type: ignore[unreachable]
        assert cache._redis_client is None

    @pytest.mark.asyncio
    async def test_stop_watching_is_idempotent(self) -> None:
        """Calling stop_watching when nothing is running doesn't raise."""
        cache = _make_redis_cache()
        await cache.stop_watching()
