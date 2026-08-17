"""Pub/Sub mixin for Redis channel messaging.

Provides ``publish`` and ``subscribe`` operations that can be mixed
into any :class:`~syntara.core.cache.base.BaseRedisClient` subclass.

Used by the settings subsystem to broadcast change notifications
across processes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError

from syntara.core.cache.base import redis_error_handler

if TYPE_CHECKING:
    import redis.asyncio as redis

logger = structlog.stdlib.get_logger(__name__)


class PubSubMixin:
    """Mixin providing async Redis Pub/Sub operations.

    Requires the host class to provide ``_ensure_connected() -> redis.Redis``.
    """

    def _ensure_connected(self) -> redis.Redis:  # pragma: no cover - abstract
        """Return a connected Redis client (provided by BaseRedisClient)."""
        raise NotImplementedError

    async def pubsub_publish(self, channel: str, message: str) -> int:
        """Publish *message* to *channel*.

        Returns the number of subscribers that received the message.

        Raises:
            RedisConnectionError: If the connection fails.

        """
        client = self._ensure_connected()
        async with redis_error_handler("pubsub_publish", channel=channel):
            count: int = await client.publish(channel, message)
            return count

    async def pubsub_subscribe(self, channel: str) -> redis.client.PubSub:
        """Create a PubSub subscription on *channel*.

        The caller is responsible for reading messages and eventually
        calling ``unsubscribe`` / ``aclose`` on the returned object.

        Raises:
            RedisConnectionError: If the connection fails.

        """
        client = self._ensure_connected()
        async with redis_error_handler("pubsub_subscribe", channel=channel):
            pubsub: Any = client.pubsub()
            await pubsub.subscribe(channel)
            logger.info("pubsub_subscribed", channel=channel)
            return pubsub  # type: ignore[no-any-return]

    async def ping(self) -> bool:
        """Return ``True`` if the server responds to PING.

        Raises:
            RedisConnectionError: If the connection fails.

        """
        client = self._ensure_connected()
        try:
            await client.ping()  # type: ignore[misc]
            return True
        except (RedisConnectionError, ResponseError):
            raise
        except OSError as e:
            msg = f"Network error: {e}"
            raise RedisConnectionError(msg) from e
