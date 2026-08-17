"""Unit tests for BaseRedisClient and SettingsRedisClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.asyncio as redis
from redis.exceptions import ConnectionError as RedisConnectionError

from syntara.core.cache.base import BaseRedisClient, redis_operation_with_backoff
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


class TestRedisOperationWithBackoff:
    """Tests for redis_operation_with_backoff (pool exhaustion retry helper)."""

    @pytest.fixture(autouse=True)
    def no_real_sleep(self):
        """Patch asyncio.sleep so retry-exhaustion tests run instantly."""
        with patch("syntara.core.cache.base.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            yield mock_sleep

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt_without_retry(self) -> None:
        operation = AsyncMock(return_value="ok")

        result = await redis_operation_with_backoff(operation, "test_op")

        assert result == "ok"
        operation.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retries_and_eventually_succeeds(self, no_real_sleep: AsyncMock) -> None:
        operation = AsyncMock(
            side_effect=[
                RedisConnectionError("pool exhausted"),
                RedisConnectionError("pool exhausted"),
                "ok",
            ]
        )

        result = await redis_operation_with_backoff(operation, "test_op", max_retries=3, initial_backoff_ms=10)

        assert result == "ok"
        assert operation.await_count == 3
        # Two retries scheduled -> two backoff sleeps
        assert no_real_sleep.await_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_exhausting_retries(self, no_real_sleep: AsyncMock) -> None:
        operation = AsyncMock(side_effect=RedisConnectionError("pool exhausted"))

        with pytest.raises(RedisConnectionError, match="pool exhausted"):
            await redis_operation_with_backoff(operation, "test_op", max_retries=3, initial_backoff_ms=10)

        # Initial attempt + 3 retries = 4 calls total
        assert operation.await_count == 4
        assert no_real_sleep.await_count == 3

    @pytest.mark.asyncio
    async def test_non_connection_errors_are_not_retried(self, no_real_sleep: AsyncMock) -> None:
        operation = AsyncMock(side_effect=ValueError("not a redis error"))

        with pytest.raises(ValueError, match="not a redis error"):
            await redis_operation_with_backoff(operation, "test_op", max_retries=3, initial_backoff_ms=10)

        operation.assert_awaited_once()
        no_real_sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_backoff_doubles_each_retry_capped_at_max_with_jitter(self, no_real_sleep: AsyncMock) -> None:
        operation = AsyncMock(side_effect=RedisConnectionError("pool exhausted"))

        with pytest.raises(RedisConnectionError):
            await redis_operation_with_backoff(operation, "test_op", max_retries=4, initial_backoff_ms=100)

        # Full jitter: each sleep is uniform(0, ceiling) where ceiling doubles
        # 100 -> 200 -> 400 -> 500 (capped, since 400*2=800 > 500)
        sleep_calls = [call.args[0] for call in no_real_sleep.await_args_list]
        assert len(sleep_calls) == 4
        ceilings_seconds = [0.1, 0.2, 0.4, 0.5]
        for actual, ceiling in zip(sleep_calls, ceilings_seconds, strict=True):
            assert 0 <= actual <= ceiling, f"sleep {actual} not in [0, {ceiling}]"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("no_real_sleep")
    async def test_records_retry_and_failed_metrics(self) -> None:
        """Retries and final failure are recorded via CACHE_POOL_RETRY, isolated registry."""
        from prometheus_client import CollectorRegistry

        from syntara.metrics.recorder import MetricsRecorder

        recorder = MetricsRecorder(prometheus_registry=CollectorRegistry())
        operation = AsyncMock(side_effect=RedisConnectionError("pool exhausted"))

        with (
            patch("syntara.core.cache.base.get_metrics_recorder", return_value=recorder),
            pytest.raises(RedisConnectionError),
        ):
            await redis_operation_with_backoff(operation, "cache_setex", max_retries=2, initial_backoff_ms=1)

        retry_count = recorder.prometheus.cache_pool_retry_total.labels(
            component="redis", operation="cache_setex", outcome="retry"
        )._value.get()
        failed_count = recorder.prometheus.cache_pool_retry_total.labels(
            component="redis", operation="cache_setex", outcome="failed"
        )._value.get()

        assert retry_count == 2
        assert failed_count == 1

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("no_real_sleep")
    async def test_records_backoff_duration_histogram(self) -> None:
        """Each retry's backoff wait is observed on the backoff duration histogram."""
        from prometheus_client import CollectorRegistry

        from syntara.metrics.recorder import MetricsRecorder

        recorder = MetricsRecorder(prometheus_registry=CollectorRegistry())
        operation = AsyncMock(side_effect=[RedisConnectionError("pool exhausted"), "ok"])

        with patch("syntara.core.cache.base.get_metrics_recorder", return_value=recorder):
            result = await redis_operation_with_backoff(operation, "cache_setex", max_retries=2, initial_backoff_ms=1)

        assert result == "ok"
        sample_sum = recorder.prometheus.cache_pool_retry_backoff_duration_seconds.labels(
            component="redis", operation="cache_setex"
        )._sum.get()
        assert sample_sum > 0

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("no_real_sleep")
    async def test_no_metrics_recorded_on_immediate_success(self) -> None:
        """A successful first attempt records no retry metrics at all."""
        from prometheus_client import CollectorRegistry

        from syntara.metrics.recorder import MetricsRecorder

        recorder = MetricsRecorder(prometheus_registry=CollectorRegistry())
        operation = AsyncMock(return_value="ok")

        with patch("syntara.core.cache.base.get_metrics_recorder", return_value=recorder):
            await redis_operation_with_backoff(operation, "cache_setex")

        assert recorder.store.count() == 0
