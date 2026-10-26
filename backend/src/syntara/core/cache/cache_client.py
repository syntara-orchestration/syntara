"""Key-value cache mixin for per-key TTL storage.

Provides ``get`` / ``setex`` / ``delete`` operations that can be mixed
into any :class:`~syntara.core.cache.base.BaseRedisClient` subclass.

Used by the settings subsystem as an L2 cache between in-process
memory and PostgreSQL.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from syntara.core.cache.base import redis_error_handler, redis_operation_with_backoff

if TYPE_CHECKING:
    import redis.asyncio as redis


class CacheMixin:
    """Mixin providing async Redis key-value cache operations.

    Requires the host class to provide ``_ensure_connected() -> redis.Redis``.
    """

    def _ensure_connected(self) -> redis.Redis:  # pragma: no cover - abstract
        """Return a connected Redis client (provided by BaseRedisClient)."""
        raise NotImplementedError

    async def cache_get(self, key: str) -> str | None:
        """Return the value for *key*, or ``None`` on miss.

        Raises:
            RedisConnectionError: If the connection fails.

        """
        client = self._ensure_connected()
        async with redis_error_handler("cache_get", key=key):
            result: str | None = await client.get(key)
            return result

    async def cache_setex(self, key: str, ttl_seconds: int, value: str) -> None:
        """Store *value* at *key* with a TTL.

        Automatically retries with exponential backoff on transient pool exhaustion
        errors (up to 3 retries, 10ms-500ms backoff).

        Raises:
            RedisConnectionError: If the connection fails after retries exhausted.

        """
        client = self._ensure_connected()

        async def _setex() -> None:
            async with redis_error_handler("cache_setex", key=key):
                await client.setex(key, ttl_seconds, value)

        await redis_operation_with_backoff(_setex, "cache_setex", key=key)

    async def cache_set_until(
        self, key: str, valid_until: datetime, value: str, *, only_if_absent: bool = False
    ) -> None:
        """Store with SET/PXAT; callers bound the whole operation with a deadline.

        Pool acquisition and retries happen inside that caller's timeout. Retries
        reuse the original absolute expiry and never refresh a proof's lifetime.
        Milliseconds are rounded down so Redis cannot expire after valid_until.
        Immutable-proof callers use only_if_absent to preserve an existing
        entry's original deadline even when a later writer has longer settings.
        """
        if valid_until.tzinfo is None or valid_until.utcoffset() is None:
            msg = "Cache deadline must be timezone-aware"
            raise ValueError(msg)
        if valid_until <= datetime.now(UTC):
            return
        deadline_ms = (valid_until - datetime(1970, 1, 1, tzinfo=UTC)) // timedelta(milliseconds=1)
        client = self._ensure_connected()

        async def _set_until() -> None:
            if valid_until <= datetime.now(UTC):
                return
            async with redis_error_handler("cache_set_until", key=key):
                if only_if_absent:
                    await client.set(key, value, pxat=deadline_ms, nx=True)
                else:
                    await client.set(key, value, pxat=deadline_ms)

        await redis_operation_with_backoff(_set_until, "cache_set_until", key=key)

    async def cache_delete(self, key: str) -> bool:
        """Delete *key*.  Returns ``True`` if the key existed.

        Automatically retries with exponential backoff on transient pool exhaustion
        errors (up to 3 retries, 10ms-500ms backoff).

        Raises:
            RedisConnectionError: If the connection fails after retries exhausted.

        """
        client = self._ensure_connected()

        async def _delete() -> bool:
            async with redis_error_handler("cache_delete", key=key):
                count: int = await client.delete(key)
                return count > 0

        return await redis_operation_with_backoff(_delete, "cache_delete", key=key)
