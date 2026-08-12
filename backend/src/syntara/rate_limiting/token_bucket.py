"""Token bucket rate limiter backed by Redis.

Provides :class:`TokenBucket` which wraps
:class:`~syntara.rate_limiting.redis_client.RateLimitRedisClient` and
returns structured :class:`TokenBucketResult` objects.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from syntara.rate_limiting.redis_client import RateLimitRedisClient

logger = structlog.stdlib.get_logger(__name__)

_KEY_PREFIX = "syntara:rate_limit:user"


@dataclass(frozen=True, slots=True)
class TokenBucketResult:
    """Outcome of a token bucket check."""

    allowed: bool
    remaining: int
    limit: int
    reset_at: float
    retry_after: float | None = None


class TokenBucket:
    """Token bucket rate limiter using Redis for cross-worker consistency.

    Args:
        redis_client: Connected :class:`RateLimitRedisClient`.

    """

    def __init__(self, redis_client: RateLimitRedisClient) -> None:
        """Initialise with the given Redis client."""
        self._redis = redis_client

    async def consume(
        self,
        user_id: str,
        max_tokens: int,
        window_seconds: int,
    ) -> TokenBucketResult:
        """Attempt to consume one token for *user_id*.

        Args:
            user_id: Unique identifier for the rate limit subject.
            max_tokens: Bucket capacity (requests per window).
            window_seconds: Window duration in seconds.

        Returns:
            A :class:`TokenBucketResult` with the outcome.

        """
        key = f"{_KEY_PREFIX}:{user_id}"
        now = time.time()

        allowed, remaining, reset_epoch = await self._redis.execute_rate_limit(
            key=key,
            max_tokens=max_tokens,
            window_seconds=window_seconds,
            now_ts=now,
        )

        retry_after: float | None = None
        if not allowed:
            retry_after = max(0.0, reset_epoch - now)

        return TokenBucketResult(
            allowed=allowed,
            remaining=remaining,
            limit=max_tokens,
            reset_at=reset_epoch,
            retry_after=retry_after,
        )
