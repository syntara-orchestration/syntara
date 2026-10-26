"""One process-owned event-domain Redis pool for terminal proofs and hints."""

import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING

from syntara.core.cache.base import redis_error_handler
from syntara.core.cache.pubsub_client import PubSubMixin
from syntara.core.constants import EventWorkerDefaults
from syntara.eventstreams.services.delivery_cache import DeliveryRedisClient

if TYPE_CHECKING:
    from redis.asyncio.client import PubSub


class EventWorkerRedisClient(DeliveryRedisClient, PubSubMixin):
    """Reuse BaseRedisClient + CacheMixin through the completed proof storage adapter."""

    _client_name = "event-worker"

    async def pubsub_subscribe(self, channel: str) -> "PubSub":
        """Retain and close partial subscriptions without disconnecting cache users."""
        pubsub = self._ensure_connected().pubsub()
        try:
            async with redis_error_handler("event_worker_subscribe", channel=channel):
                await pubsub.subscribe(channel)
            return pubsub
        except BaseException:
            with suppress(Exception):
                async with asyncio.timeout(EventWorkerDefaults.HINT_TIMEOUT_SECONDS):
                    await pubsub.aclose()  # type: ignore[no-untyped-call]  # Redis SDK boundary
            raise
