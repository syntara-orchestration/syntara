"""Optional terminal-reference cache; PostgreSQL remains authoritative on every hit."""

import asyncio
from collections.abc import Callable

import structlog
from redis.exceptions import RedisError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.cache.base import BaseRedisClient
from syntara.core.cache.cache_client import CacheMixin
from syntara.core.constants import EventDeliveryDefaults
from syntara.eventstreams.core.deduplication import DeliveryIdentity, TerminalDelivery, TerminalReferenceCache
from syntara.eventstreams.services.deduplication_store import EventDeliveryStore

logger = structlog.stdlib.get_logger(__name__)


class DeliveryRedisClient(BaseRedisClient, CacheMixin):
    """Store only the immutable terminal digest, with a disposable short TTL."""

    _client_name = "event_delivery"

    async def get(self, identity: DeliveryIdentity) -> str | None:
        """Read a reference without granting any processing or resolution authority."""
        return await self.cache_get(identity.cache_key)

    async def put(self, identity: DeliveryIdentity) -> None:
        """Write only an immutable reference, never claims, payloads or credentials."""
        await self.cache_setex(identity.cache_key, EventDeliveryDefaults.TERMINAL_CACHE_TTL_SECONDS, identity.digest)


class EventDeliveryTerminalLookup:
    """Verify database state in a fresh transaction and populate cache after commit."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        *,
        cache: TerminalReferenceCache | None = None,
    ) -> None:
        """Inject optional cache access; missing Redis needs no replacement service."""
        self.session_factory = session_factory
        self.cache = cache

    async def lookup(self, identity: DeliveryIdentity) -> TerminalDelivery | None:
        """Return database evidence regardless of absent, stale or malformed cache content."""
        if self.cache is not None:
            try:
                async with asyncio.timeout(EventDeliveryDefaults.TERMINAL_CACHE_TIMEOUT_SECONDS):
                    await self.cache.get(identity)
            except (RedisError, OSError, TimeoutError, ValueError):
                logger.warning("event_delivery_terminal_cache_read_unavailable")
        async with self.session_factory() as session, session.begin():
            terminal = await EventDeliveryStore(session).lookup_terminal(identity)
        # The transaction has committed before the cache is populated. A cache
        # hit never skips the independent database read above.
        if terminal is not None and self.cache is not None:
            try:
                async with asyncio.timeout(EventDeliveryDefaults.TERMINAL_CACHE_TIMEOUT_SECONDS):
                    await self.cache.put(identity)
            except (RedisError, OSError, TimeoutError, ValueError):
                logger.warning("event_delivery_terminal_cache_write_unavailable")
        return terminal
