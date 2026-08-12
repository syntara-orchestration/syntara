"""Key-value cache mixin for per-key TTL storage.

Provides ``get`` / ``setex`` / ``delete`` operations that can be mixed
into any :class:`~syntara.core.cache.base.BaseRedisClient` subclass.

Used by the settings subsystem as an L2 cache between in-process
memory and PostgreSQL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from syntara.core.cache.base import redis_error_handler

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

        Raises:
            RedisConnectionError: If the connection fails.

        """
        client = self._ensure_connected()
        async with redis_error_handler("cache_setex", key=key):
            await client.setex(key, ttl_seconds, value)

    async def cache_delete(self, key: str) -> bool:
        """Delete *key*.  Returns ``True`` if the key existed.

        Raises:
            RedisConnectionError: If the connection fails.

        """
        client = self._ensure_connected()
        async with redis_error_handler("cache_delete", key=key):
            count: int = await client.delete(key)
            return count > 0
