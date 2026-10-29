"""Disposable Redis wakeups; message contents never supply desired state."""

import asyncio
import contextlib
from collections.abc import Callable

import structlog

from syntara.core.constants import EventWorkerDefaults
from syntara.eventstreams.services.worker_redis import EventWorkerRedisClient

logger = structlog.stdlib.get_logger(__name__)


class SubscriptionHintListener:
    """Listen independently of reconciliation; lost or unavailable hints are harmless."""

    def __init__(self, request_reconcile: Callable[[], None], client: EventWorkerRedisClient) -> None:
        """Borrow the process-owned event Redis client without owning its pool."""
        self._request = request_reconcile
        self._client = client
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
                except Exception:  # noqa: BLE001 - cleanup of an unavailable optional dependency is best effort
                    logger.warning("event_subscription_hints_close_incomplete")
            if not self._closed:
                await asyncio.sleep(EventWorkerDefaults.RECONCILE_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """Stop wakeups and close only this listener's Pub/Sub subscription."""
        self._closed = True
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
