"""Disposable Redis wakeups; message contents never supply desired state."""

import asyncio
import contextlib
from collections.abc import Callable

import structlog

from syntara.core.cache.base import BaseRedisClient
from syntara.core.cache.pubsub_client import PubSubMixin
from syntara.core.constants import EventWorkerDefaults

logger = structlog.stdlib.get_logger(__name__)


class EventHintRedisClient(BaseRedisClient, PubSubMixin):
    """Reuse platform Redis configuration and bounded connection pools."""

    _client_name = "event-subscription-hints"


class SubscriptionHintListener:
    """Listen independently of reconciliation; lost or unavailable hints are harmless."""

    def __init__(self, request_reconcile: Callable[[], None], client: EventHintRedisClient | None = None) -> None:
        """Inject a wakeup callback and optionally an isolated Redis client."""
        self._request = request_reconcile
        self._client = client if client is not None else EventHintRedisClient()
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    def start(self) -> None:
        """Begin listening without delaying startup/readiness on Redis."""
        if not self._closed and (self._task is None or self._task.done()):
            self._task = asyncio.create_task(self._listen(), name="event-subscription-hints")

    async def _listen(self) -> None:
        while not self._closed:
            pubsub = None
            try:
                async with asyncio.timeout(EventWorkerDefaults.HINT_TIMEOUT_SECONDS):
                    pubsub = await self._client.pubsub_subscribe(EventWorkerDefaults.HINT_CHANNEL)
                while not self._closed:
                    async with asyncio.timeout(EventWorkerDefaults.HINT_TIMEOUT_SECONDS * 2):
                        message = await pubsub.get_message(
                            ignore_subscribe_messages=True, timeout=EventWorkerDefaults.HINT_TIMEOUT_SECONDS
                        )
                    if message is not None and message.get("type") == "message":
                        self._request()
            except Exception:  # noqa: BLE001 - optional hints must never stop authoritative reconciliation
                logger.warning("event_subscription_hints_unavailable")
            finally:
                try:
                    async with asyncio.timeout(EventWorkerDefaults.HINT_TIMEOUT_SECONDS):
                        if pubsub is not None:
                            await pubsub.aclose()  # type: ignore[no-untyped-call]  # Redis PubSub SDK boundary
                        await self._client.disconnect()
                except Exception:  # noqa: BLE001 - cleanup of an unavailable optional dependency is best effort
                    logger.warning("event_subscription_hints_close_incomplete")
            if not self._closed:
                await asyncio.sleep(EventWorkerDefaults.RECONCILE_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """Stop wakeups and close the process-owned Redis connection pool."""
        self._closed = True
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
