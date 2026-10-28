"""Unit tests for CacheMixin operations."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from syntara.core.cache.base import BaseRedisClient
from syntara.core.cache.cache_client import CacheMixin


class _TestCacheClient(BaseRedisClient, CacheMixin):
    _client_name = "test-cache"


def _mock_settings() -> MagicMock:
    mock = MagicMock()
    mock.cache_host = "localhost"
    mock.cache_port = 6379
    mock.cache_db = 0
    mock.cache_password = None
    mock.cache_connection_pool_size = 5
    return mock


def _make_client() -> tuple[_TestCacheClient, AsyncMock]:
    """Return a client with a mock Redis instance injected.

    Returns (client, mock_redis) so tests can configure method responses
    on the mock without triggering mypy union-attr errors.
    """
    with patch("syntara.core.cache.base.get_settings", return_value=_mock_settings()):
        client = _TestCacheClient()
    mock_redis = AsyncMock()
    client._client = mock_redis
    return client, mock_redis


class TestCacheGet:
    """Tests for CacheMixin.cache_get."""

    @pytest.mark.asyncio
    async def test_returns_value_on_hit(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.get = AsyncMock(return_value="cached_value")

        result = await client.cache_get("my:key")

        assert result == "cached_value"
        mock_redis.get.assert_awaited_once_with("my:key")

    @pytest.mark.asyncio
    async def test_returns_none_on_miss(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.get = AsyncMock(return_value=None)

        result = await client.cache_get("missing:key")

        assert result is None

    @pytest.mark.asyncio
    async def test_raises_on_connection_error(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.get = AsyncMock(side_effect=RedisConnectionError("down"))

        with pytest.raises(RedisConnectionError):
            await client.cache_get("my:key")

    @pytest.mark.asyncio
    async def test_wraps_os_error(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.get = AsyncMock(side_effect=OSError("network"))

        with pytest.raises(RedisConnectionError, match="Network error"):
            await client.cache_get("my:key")


class TestCacheSetex:
    """Tests for CacheMixin.cache_setex."""

    @pytest.mark.asyncio
    async def test_stores_value_with_ttl(self) -> None:
        client, mock_redis = _make_client()

        await client.cache_setex("my:key", 60, "value")

        mock_redis.setex.assert_awaited_once_with("my:key", 60, "value")

    @pytest.mark.asyncio
    async def test_raises_on_connection_error(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.setex = AsyncMock(side_effect=RedisConnectionError("down"))

        with pytest.raises(RedisConnectionError):
            await client.cache_setex("my:key", 60, "value")


class TestCacheSetUntil:
    """Fixed expiry survives idempotent retries without changing SETEX callers."""

    @pytest.mark.asyncio
    async def test_absolute_expiry_rounds_down_to_milliseconds(self) -> None:
        client, mock_redis = _make_client()
        deadline = datetime.now(UTC) + timedelta(seconds=60, microseconds=123)
        await client.cache_set_until("proof:key", deadline, "proof")
        milliseconds = (deadline - datetime(1970, 1, 1, tzinfo=UTC)) // timedelta(milliseconds=1)
        mock_redis.set.assert_awaited_once_with("proof:key", "proof", pxat=milliseconds)
        mock_redis.setex.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_retries_reuse_exact_absolute_timestamp(self) -> None:
        client, mock_redis = _make_client()
        deadline = datetime.now(UTC) + timedelta(seconds=60)
        mock_redis.set.side_effect = [RedisConnectionError("pool exhausted"), True]
        await client.cache_set_until("proof:key", deadline, "proof")
        first, second = mock_redis.set.await_args_list
        assert first == second

    @pytest.mark.asyncio
    async def test_insert_only_writes_cannot_extend_an_existing_deadline(self) -> None:
        client, mock_redis = _make_client()
        deadline = datetime.now(UTC) + timedelta(seconds=60)
        stored: list[tuple[str, int]] = []

        async def set_value(_key: str, value: str, *, pxat: int, nx: bool) -> bool | None:
            if stored and nx:
                return None
            stored.append((value, pxat))
            return True

        mock_redis.set.side_effect = set_value
        await client.cache_set_until("proof:key", deadline, "first", only_if_absent=True)
        await client.cache_set_until("proof:key", deadline + timedelta(seconds=60), "later", only_if_absent=True)
        assert len(stored) == 1
        assert stored[0][0] == "first"
        assert stored[0][1] == (deadline - datetime(1970, 1, 1, tzinfo=UTC)) // timedelta(milliseconds=1)

    @pytest.mark.asyncio
    async def test_expired_write_never_acquires_a_client(self) -> None:
        client, mock_redis = _make_client()
        with patch.object(client, "_ensure_connected") as connect:
            await client.cache_set_until("proof:key", datetime.now(UTC) - timedelta(seconds=1), "proof")
        connect.assert_not_called()
        mock_redis.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_naive_deadline_is_rejected(self) -> None:
        client, mock_redis = _make_client()
        with pytest.raises(ValueError, match="timezone-aware"):
            await client.cache_set_until("proof:key", datetime(2026, 10, 26, tzinfo=UTC).replace(tzinfo=None), "proof")
        mock_redis.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_retry_skips_a_deadline_that_has_passed(self) -> None:
        client, mock_redis = _make_client()
        now = datetime.now(UTC)
        deadline = now + timedelta(seconds=60)
        mock_redis.set.side_effect = RedisConnectionError("pool exhausted")
        with patch("syntara.core.cache.cache_client.datetime", wraps=datetime) as clock:
            clock.now.side_effect = [now, now, deadline]
            await client.cache_set_until("proof:key", deadline, "proof")
        mock_redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_outer_timeout_bounds_retry_waits(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.set.side_effect = RedisConnectionError("pool exhausted")
        waiting = asyncio.Event()

        async def stalled_backoff(_: float) -> None:
            waiting.set()
            await asyncio.Event().wait()

        with patch("syntara.core.cache.base.asyncio.sleep", side_effect=stalled_backoff):
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.01):
                    await client.cache_set_until("proof:key", datetime.now(UTC) + timedelta(seconds=60), "proof")
        assert waiting.is_set()
        mock_redis.set.assert_awaited_once()


class TestCacheDelete:
    """Tests for CacheMixin.cache_delete."""

    @pytest.mark.asyncio
    async def test_returns_true_when_key_existed(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.delete = AsyncMock(return_value=1)

        result = await client.cache_delete("my:key")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_key_missing(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.delete = AsyncMock(return_value=0)

        result = await client.cache_delete("my:key")

        assert result is False

    @pytest.mark.asyncio
    async def test_raises_on_connection_error(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.delete = AsyncMock(side_effect=RedisConnectionError("down"))

        with pytest.raises(RedisConnectionError):
            await client.cache_delete("my:key")
