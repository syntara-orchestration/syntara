"""Unit tests for the rate limit Redis client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from syntara.rate_limiting.redis_client import RateLimitRedisClient


@pytest.fixture
def mock_settings() -> MagicMock:
    """Mock application settings for Redis connection."""
    settings = MagicMock()
    settings.cache_host = "localhost"
    settings.cache_port = 6379
    settings.cache_db = 0
    settings.cache_password = MagicMock()
    settings.cache_password.get_secret_value.return_value = "test"
    settings.cache_connection_pool_size = 10
    return settings


@pytest.fixture
def client(mock_settings: MagicMock) -> RateLimitRedisClient:
    """Rate limit Redis client with mocked settings."""
    with patch("syntara.core.cache.base.get_settings", return_value=mock_settings):
        return RateLimitRedisClient()


class TestRateLimitRedisClient:
    """Tests for RateLimitRedisClient."""

    def test_client_name(self, client: RateLimitRedisClient) -> None:
        assert client._client_name == "rate_limit"

    @pytest.mark.asyncio
    async def test_ensure_script_loads_once(self, client: RateLimitRedisClient) -> None:
        mock_redis = AsyncMock()
        mock_redis.script_load = AsyncMock(return_value="sha256hash")
        client._client = mock_redis

        sha1 = await client._ensure_script()
        sha2 = await client._ensure_script()

        assert sha1 == "sha256hash"
        assert sha2 == "sha256hash"
        mock_redis.script_load.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_rate_limit(self, client: RateLimitRedisClient) -> None:
        mock_redis = AsyncMock()
        mock_redis.script_load = AsyncMock(return_value="sha")
        mock_redis.evalsha = AsyncMock(return_value=[1, 9, "1060.5"])
        client._client = mock_redis

        allowed, remaining, reset_epoch = await client.execute_rate_limit(
            key="test:key", max_tokens=10, window_seconds=60, now_ts=1000.0
        )

        assert allowed is True
        assert remaining == 9
        assert reset_epoch == 1060.5

    @pytest.mark.asyncio
    async def test_execute_rate_limit_denied(self, client: RateLimitRedisClient) -> None:
        mock_redis = AsyncMock()
        mock_redis.script_load = AsyncMock(return_value="sha")
        mock_redis.evalsha = AsyncMock(return_value=[0, 0, "1005.3"])
        client._client = mock_redis

        allowed, remaining, reset_epoch = await client.execute_rate_limit(
            key="test:key", max_tokens=10, window_seconds=60, now_ts=1000.0
        )

        assert allowed is False
        assert remaining == 0
        assert reset_epoch == 1005.3

    @pytest.mark.asyncio
    async def test_execute_rate_limit_redis_error(self, client: RateLimitRedisClient) -> None:
        mock_redis = AsyncMock()
        mock_redis.script_load = AsyncMock(return_value="sha")
        mock_redis.evalsha = AsyncMock(side_effect=RedisConnectionError("connection lost"))
        client._client = mock_redis

        with pytest.raises(RedisConnectionError):
            await client.execute_rate_limit(key="test:key", max_tokens=10, window_seconds=60, now_ts=1000.0)
