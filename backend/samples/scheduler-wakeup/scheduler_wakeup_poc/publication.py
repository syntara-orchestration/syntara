"""Transactional-outbox publisher for advisory Scheduler wake hints."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Protocol

from .contracts import WakeHint, WakePublisher
from .models import utc_now


class OutboxStore(Protocol):
    async def due_outbox(self, owner: str, limit: int) -> list[object]: ...

    async def mark_outbox_accepted(self, event_id: object, owner: str, token: int) -> bool: ...

    async def record_publish_failure(
        self, event_id: object, owner: str, token: int, error: str, retry_at: datetime
    ) -> bool: ...


class WakeOutboxPublisher:
    """Leases committed outbox rows and hands only their queue hint to a transport.

    A transport acknowledgement means only that the hint was accepted.  It
    never changes ownership of an execution; that remains a Scheduler/store
    transaction.  The lease token prevents a late failed publisher from
    overwriting a newer publisher's result.
    """

    def __init__(
        self,
        store: OutboxStore,
        publisher: WakePublisher,
        owner_id: str,
        *,
        retry_delay: timedelta = timedelta(seconds=1),
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._store = store
        self._publisher = publisher
        self._owner_id = owner_id
        self._retry_delay = retry_delay
        self._now = now

    async def publish_due(self, limit: int = 100) -> int:
        """Attempt a bounded batch, returning the number accepted."""
        events = await self._store.due_outbox(self._owner_id, limit)
        accepted = 0
        for event in events:
            try:
                await self._publisher.publish(WakeHint(event_id=event.event_id, queue=event.queue))
            except Exception as exc:  # transport errors must leave a durable retry intent
                await self._store.record_publish_failure(
                    event.event_id,
                    self._owner_id,
                    event.publication_lease_token,
                    type(exc).__name__,
                    self._now() + self._retry_delay,
                )
                continue
            if await self._store.mark_outbox_accepted(
                event.event_id, self._owner_id, event.publication_lease_token
            ):
                accepted += 1
        return accepted
