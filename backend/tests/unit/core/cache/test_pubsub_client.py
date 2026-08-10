"""Unit tests for PubSubMixin operations."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError

from syntara.core.cache.base import BaseRedisClient
from syntara.core.cache.pubsub_client import PubSubMixin


class _TestPubSubClient(BaseRedisClient, PubSubMixin):
    _client_name = "test-pubsub"


def _mock_settings() -> MagicMock:
    mock = MagicMock()
    mock.cache_host = "localhost"
    mock.cache_port = 6379
    mock.cache_db = 0
    mock.cache_password = None
    mock.cache_connection_pool_size = 5
    return mock


def _make_client() -> tuple[_TestPubSubClient, AsyncMock]:
    """Return a client with a mock Redis instance injected."""
    with patch("syntara.core.cache.base.get_settings", return_value=_mock_settings()):
        client = _TestPubSubClient()
    mock_redis = AsyncMock()
    client._client = mock_redis
    return client, mock_redis


class TestPubSubPublish:
    """Tests for PubSubMixin.pubsub_publish."""

    @pytest.mark.asyncio
    async def test_publishes_message(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.publish = AsyncMock(return_value=3)

        count = await client.pubsub_publish("ch", "msg")

        assert count == 3
        mock_redis.publish.assert_awaited_once_with("ch", "msg")

    @pytest.mark.asyncio
    async def test_raises_on_connection_error(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.publish = AsyncMock(side_effect=RedisConnectionError("down"))

        with pytest.raises(RedisConnectionError):
            await client.pubsub_publish("ch", "msg")

    @pytest.mark.asyncio
    async def test_wraps_os_error(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.publish = AsyncMock(side_effect=OSError("network"))

        with pytest.raises(RedisConnectionError, match="Network error"):
            await client.pubsub_publish("ch", "msg")


class TestPubSubSubscribe:
    """Tests for PubSubMixin.pubsub_subscribe."""

    @pytest.mark.asyncio
    async def test_returns_pubsub_object(self) -> None:
        client, mock_redis = _make_client()
        mock_pubsub = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

        result = await client.pubsub_subscribe("ch")

        assert result is mock_pubsub
        mock_pubsub.subscribe.assert_awaited_once_with("ch")


class TestPing:
    """Tests for PubSubMixin.ping."""

    @pytest.mark.asyncio
    async def test_returns_true_on_success(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.ping = AsyncMock()

        result = await client.ping()

        assert result is True

    @pytest.mark.asyncio
    async def test_raises_on_connection_error(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.ping = AsyncMock(side_effect=RedisConnectionError("down"))

        with pytest.raises(RedisConnectionError):
            await client.ping()

    @pytest.mark.asyncio
    async def test_raises_on_response_error(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.ping = AsyncMock(side_effect=ResponseError("AUTH required"))

        with pytest.raises(ResponseError):
            await client.ping()

    @pytest.mark.asyncio
    async def test_wraps_os_error(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.ping = AsyncMock(side_effect=OSError("network"))

        with pytest.raises(RedisConnectionError, match="Network error"):
            await client.ping()
