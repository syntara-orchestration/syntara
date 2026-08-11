"""Unit tests for the token bucket rate limiter."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from syntara.rate_limiting.token_bucket import TokenBucket, TokenBucketResult


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Mock Redis client for token bucket tests."""
    return AsyncMock()


@pytest.fixture
def bucket(mock_redis_client: AsyncMock) -> TokenBucket:
    """Token bucket instance with mock Redis."""
    return TokenBucket(redis_client=mock_redis_client)


class TestTokenBucketResult:
    """Tests for TokenBucketResult."""

    def test_allowed_result(self) -> None:
        result = TokenBucketResult(allowed=True, remaining=9, limit=10, reset_at=1000.0)
        assert result.allowed is True
        assert result.remaining == 9
        assert result.limit == 10
        assert result.retry_after is None

    def test_denied_result(self) -> None:
        result = TokenBucketResult(allowed=False, remaining=0, limit=10, reset_at=1005.0, retry_after=5.0)
        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after == 5.0

    def test_frozen(self) -> None:
        result = TokenBucketResult(allowed=True, remaining=1, limit=10, reset_at=1.0)
        with pytest.raises(AttributeError):
            result.allowed = False  # type: ignore[misc]


class TestTokenBucket:
    """Tests for TokenBucket."""

    @pytest.mark.asyncio
    async def test_consume_allowed(self, bucket: TokenBucket, mock_redis_client: AsyncMock) -> None:
        mock_redis_client.execute_rate_limit.return_value = (True, 9, 1060.0)

        result = await bucket.consume(user_id="user-1", max_tokens=10, window_seconds=60)

        assert result.allowed is True
        assert result.remaining == 9
        assert result.limit == 10
        assert result.retry_after is None
        mock_redis_client.execute_rate_limit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_consume_denied(self, bucket: TokenBucket, mock_redis_client: AsyncMock) -> None:
        future_reset = 9999999999.0
        mock_redis_client.execute_rate_limit.return_value = (False, 0, future_reset)

        result = await bucket.consume(user_id="user-1", max_tokens=10, window_seconds=60)

        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after is not None
        assert result.retry_after > 0

    @pytest.mark.asyncio
    async def test_consume_key_format(self, bucket: TokenBucket, mock_redis_client: AsyncMock) -> None:
        mock_redis_client.execute_rate_limit.return_value = (True, 5, 1060.0)

        await bucket.consume(user_id="abc-123", max_tokens=10, window_seconds=60)

        call_kwargs = mock_redis_client.execute_rate_limit.call_args
        assert call_kwargs.kwargs["key"] == "syntara:rate_limit:user:abc-123"

    @pytest.mark.asyncio
    async def test_consume_passes_parameters(self, bucket: TokenBucket, mock_redis_client: AsyncMock) -> None:
        mock_redis_client.execute_rate_limit.return_value = (True, 99, 1060.0)

        with patch("syntara.rate_limiting.token_bucket.time") as mock_time:
            mock_time.time.return_value = 1000.0
            await bucket.consume(user_id="u1", max_tokens=100, window_seconds=120)

        call_kwargs = mock_redis_client.execute_rate_limit.call_args.kwargs
        assert call_kwargs["max_tokens"] == 100
        assert call_kwargs["window_seconds"] == 120
        assert call_kwargs["now_ts"] == 1000.0

    @pytest.mark.asyncio
    async def test_retry_after_zero_floor(self, bucket: TokenBucket, mock_redis_client: AsyncMock) -> None:
        """retry_after is floored at 0 when reset_epoch is in the past."""
        mock_redis_client.execute_rate_limit.return_value = (False, 0, 0.0)

        result = await bucket.consume(user_id="user-1", max_tokens=10, window_seconds=60)

        assert result.retry_after == 0.0
