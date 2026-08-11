"""Unit tests for BaseRedisClient and SettingsRedisClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import redis.asyncio as redis

from syntara.core.cache.base import BaseRedisClient
from syntara.core.cache.settings_client import SettingsRedisClient


def _mock_settings() -> MagicMock:
    mock = MagicMock()
    mock.cache_host = "redis.example.com"
    mock.cache_port = 6380
    mock.cache_db = 2
    mock.cache_password = MagicMock()
    mock.cache_password.get_secret_value.return_value = "secret"
    mock.cache_connection_pool_size = 5
    return mock


class TestBaseRedisClient:
    """Tests for BaseRedisClient connection lifecycle."""

    def test_connect_creates_redis_client(self) -> None:
        """connect() creates a redis.asyncio.Redis instance from settings."""
        with (
            patch.object(BaseRedisClient, "__init_subclass__", lambda **_kw: None),
            patch("syntara.core.cache.base.get_settings", return_value=_mock_settings()),
        ):
            client = BaseRedisClient()
            client.connect()
            assert isinstance(client._client, redis.Redis)

    def test_connect_is_idempotent(self) -> None:
        """Calling connect() twice does not create a second client."""
        with patch("syntara.core.cache.base.get_settings", return_value=_mock_settings()):
            client = BaseRedisClient()
            client.connect()
            first = client._client
            client.connect()
            assert client._client is first


class TestSettingsRedisClient:
    """Tests for SettingsRedisClient composed class."""

    def test_has_correct_client_name(self) -> None:
        with patch("syntara.core.cache.base.get_settings", return_value=_mock_settings()):
            client = SettingsRedisClient()
            assert client._client_name == "settings"

    def test_has_cache_and_pubsub_methods(self) -> None:
        """SettingsRedisClient has methods from both mixins."""
        with patch("syntara.core.cache.base.get_settings", return_value=_mock_settings()):
            client = SettingsRedisClient()
            assert hasattr(client, "cache_get")
            assert hasattr(client, "cache_setex")
            assert hasattr(client, "cache_delete")
            assert hasattr(client, "pubsub_publish")
            assert hasattr(client, "pubsub_subscribe")
            assert hasattr(client, "ping")
