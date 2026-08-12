"""Integration tests for the token bucket rate limiter against real Redis.

Exercises the Lua script's arithmetic (refill, consumption, denial, reset
timing) using a real Redis instance spun up by testcontainers.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from syntara.rate_limiting.redis_client import RateLimitRedisClient
from syntara.rate_limiting.token_bucket import TokenBucket

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def _unique_user() -> str:
    return f"test-user-{uuid.uuid4()}"


@pytest_asyncio.fixture
async def rate_limit_client(test_cache: None) -> AsyncGenerator[RateLimitRedisClient, None]:
    """Create a RateLimitRedisClient connected to the test Redis container."""
    client = RateLimitRedisClient()
    async with client:
        yield client


@pytest_asyncio.fixture
async def bucket(rate_limit_client: RateLimitRedisClient) -> TokenBucket:
    """Create a TokenBucket backed by the test Redis client."""
    return TokenBucket(redis_client=rate_limit_client)


class TestBasicTokenConsumption:
    """First request initialises the bucket; subsequent requests decrement."""

    @pytest.mark.asyncio
    async def test_first_request_allowed(self, bucket: TokenBucket) -> None:
        result = await bucket.consume(user_id=_unique_user(), max_tokens=10, window_seconds=60)

        assert result.allowed is True
        assert result.remaining == 9
        assert result.limit == 10
        assert result.retry_after is None

    @pytest.mark.asyncio
    async def test_exhaust_bucket(self, bucket: TokenBucket) -> None:
        user = _unique_user()

        for i in range(10):
            result = await bucket.consume(user_id=user, max_tokens=10, window_seconds=60)
            assert result.allowed is True
            assert result.remaining == 10 - 1 - i

        denied = await bucket.consume(user_id=user, max_tokens=10, window_seconds=60)
        assert denied.allowed is False
        assert denied.remaining == 0
        assert denied.retry_after is not None
        assert denied.retry_after > 0

    @pytest.mark.asyncio
    async def test_single_token_bucket(self, bucket: TokenBucket) -> None:
        user = _unique_user()

        first = await bucket.consume(user_id=user, max_tokens=1, window_seconds=60)
        assert first.allowed is True
        assert first.remaining == 0

        second = await bucket.consume(user_id=user, max_tokens=1, window_seconds=60)
        assert second.allowed is False


class TestTokenRefill:
    """Tokens refill proportionally to elapsed time."""

    @pytest.mark.asyncio
    async def test_partial_refill_after_wait(self, rate_limit_client: RateLimitRedisClient) -> None:
        """After exhausting a 10-token / 2s bucket, waiting ~1s refills ~5 tokens."""
        user = _unique_user()
        tb = TokenBucket(redis_client=rate_limit_client)

        for _ in range(10):
            await tb.consume(user_id=user, max_tokens=10, window_seconds=2)

        denied = await tb.consume(user_id=user, max_tokens=10, window_seconds=2)
        assert denied.allowed is False

        await asyncio.sleep(1.1)

        result = await tb.consume(user_id=user, max_tokens=10, window_seconds=2)
        assert result.allowed is True
        assert result.remaining >= 3

    @pytest.mark.asyncio
    async def test_full_refill_after_window(self, rate_limit_client: RateLimitRedisClient) -> None:
        """After a full window elapses, the bucket is back to max capacity."""
        user = _unique_user()
        tb = TokenBucket(redis_client=rate_limit_client)

        for _ in range(5):
            await tb.consume(user_id=user, max_tokens=5, window_seconds=1)

        denied = await tb.consume(user_id=user, max_tokens=5, window_seconds=1)
        assert denied.allowed is False

        await asyncio.sleep(1.1)

        result = await tb.consume(user_id=user, max_tokens=5, window_seconds=1)
        assert result.allowed is True
        assert result.remaining == 4


class TestUserIsolation:
    """Each user has an independent bucket."""

    @pytest.mark.asyncio
    async def test_separate_users_independent(self, bucket: TokenBucket) -> None:
        user_a = _unique_user()
        user_b = _unique_user()

        for _ in range(5):
            await bucket.consume(user_id=user_a, max_tokens=5, window_seconds=60)

        denied = await bucket.consume(user_id=user_a, max_tokens=5, window_seconds=60)
        assert denied.allowed is False

        result_b = await bucket.consume(user_id=user_b, max_tokens=5, window_seconds=60)
        assert result_b.allowed is True
        assert result_b.remaining == 4


class TestConcurrentRequests:
    """Concurrent consume calls are atomic thanks to the Lua script."""

    @pytest.mark.asyncio
    async def test_concurrent_consumers_respect_limit(self, test_cache: None) -> None:
        user = _unique_user()
        max_tokens = 10

        async def consume_once() -> bool:
            async with RateLimitRedisClient() as client:
                tb = TokenBucket(redis_client=client)
                result = await tb.consume(user_id=user, max_tokens=max_tokens, window_seconds=60)
                return bool(result.allowed)

        results = await asyncio.gather(*[consume_once() for _ in range(20)])

        allowed_count = sum(results)
        assert allowed_count == max_tokens


class TestRetryAfterAccuracy:
    """retry_after should approximate the actual wait needed for the next token."""

    @pytest.mark.asyncio
    async def test_retry_after_is_reasonable(self, bucket: TokenBucket) -> None:
        user = _unique_user()
        window = 10

        for _ in range(5):
            await bucket.consume(user_id=user, max_tokens=5, window_seconds=window)

        denied = await bucket.consume(user_id=user, max_tokens=5, window_seconds=window)
        assert denied.retry_after is not None
        assert 0 < denied.retry_after <= window
