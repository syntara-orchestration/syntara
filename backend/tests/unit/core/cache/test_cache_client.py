"""Unit tests for CacheMixin operations."""

from __future__ import annotations

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
