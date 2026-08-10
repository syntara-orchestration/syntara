"""Redis client for token bucket rate limiting.

Extends :class:`~syntara.core.cache.base.BaseRedisClient` with a Lua
script that atomically checks and decrements tokens.  The script is
registered once via ``SCRIPT LOAD`` and executed with ``EVALSHA`` for
subsequent calls.
"""

from __future__ import annotations

import structlog

from syntara.core.cache.base import BaseRedisClient, redis_error_handler
from syntara.core.cache.cache_client import CacheMixin

logger = structlog.stdlib.get_logger(__name__)

_RATE_LIMIT_LUA = """
local key        = KEYS[1]
local max_tokens = tonumber(ARGV[1])
local window     = tonumber(ARGV[2])
local now        = tonumber(ARGV[3])

local data    = redis.call('HMGET', key, 'tokens', 'last_ts')
local tokens  = tonumber(data[1])
local last_ts = tonumber(data[2])

if tokens == nil then
    -- First request: initialise bucket at full capacity minus one
    tokens  = max_tokens - 1
    last_ts = now
    redis.call('HMSET', key, 'tokens', tokens, 'last_ts', last_ts)
    redis.call('EXPIRE', key, window + 1)
    return {1, math.floor(tokens), tostring(now + window)}
end

-- Refill proportionally to elapsed time
local elapsed   = math.max(now - last_ts, 0)
local refill    = (elapsed / window) * max_tokens
local new_tokens = math.min(tokens + refill, max_tokens)

-- Try to consume one token
if new_tokens >= 1 then
    new_tokens = new_tokens - 1
    redis.call('HMSET', key, 'tokens', new_tokens, 'last_ts', now)
    redis.call('EXPIRE', key, window + 1)
    return {1, math.floor(new_tokens), tostring(now + window)}
else
    -- Denied: compute when the next token will be available
    redis.call('HMSET', key, 'tokens', new_tokens, 'last_ts', now)
    redis.call('EXPIRE', key, window + 1)
    local deficit     = 1 - new_tokens
    local refill_rate = max_tokens / window
    local wait        = deficit / refill_rate
    return {0, 0, tostring(now + wait)}
end
"""


class RateLimitRedisClient(BaseRedisClient, CacheMixin):
    """Redis client specialised for token bucket rate limiting."""

    _client_name: str = "rate_limit"

    def __init__(self) -> None:
        """Initialise the client and clear the script cache."""
        super().__init__()
        self._script_sha: str | None = None

    async def _ensure_script(self) -> str:
        """Load the Lua script into Redis and cache its SHA."""
        if self._script_sha is not None:
            return self._script_sha
        client = self._ensure_connected()
        async with redis_error_handler("script_load"):
            sha: str = await client.script_load(_RATE_LIMIT_LUA)
            self._script_sha = sha
            return sha

    async def execute_rate_limit(
        self,
        key: str,
        max_tokens: int,
        window_seconds: int,
        now_ts: float,
    ) -> tuple[bool, int, float]:
        """Execute the token bucket check atomically.

        Args:
            key: Redis key for this bucket.
            max_tokens: Bucket capacity (requests per window).
            window_seconds: Refill window in seconds.
            now_ts: Current epoch timestamp.

        Returns:
            ``(allowed, remaining, reset_epoch)`` tuple.

        """
        client = self._ensure_connected()
        sha = await self._ensure_script()
        async with redis_error_handler("rate_limit_check", key=key):
            result = await client.evalsha(  # type: ignore[misc]
                sha,
                1,
                key,
                max_tokens,
                window_seconds,
                now_ts,
            )
            allowed = bool(int(result[0]))
            remaining = int(result[1])
            reset_epoch = float(result[2])
            return allowed, remaining, reset_epoch
