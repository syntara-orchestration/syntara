"""Placement values and process-local admission authority, separate from delivery tokens."""

import asyncio
import time
from collections.abc import Callable
from typing import ClassVar
from uuid import UUID, uuid4

from pydantic import AwareDatetime, ConfigDict, model_validator
from sqlmodel import Field, SQLModel


class PlacementValue(SQLModel):
    """Immutable, non-secret coordination value."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)  # type: ignore[assignment]


class WorkerIdentity(PlacementValue):
    """Persisted Installation UUID plus a fresh UUID for this process incarnation."""

    deployment_id: UUID
    worker_id: UUID = Field(default_factory=uuid4)


class WorkerMembership(PlacementValue):
    """Confirmed database membership; draining excludes new placement claims."""

    worker: WorkerIdentity
    heartbeat_until: AwareDatetime
    draining: bool


class SubscriptionPlacementLease(PlacementValue):
    """Confirmed database ownership; grants neither Kafka assignment nor delivery authority."""

    subscription_id: UUID
    owner: WorkerIdentity
    confirmed_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_deadline(self) -> "SubscriptionPlacementLease":
        """Reject expired database observations before granting startup authority."""
        if self.expires_at <= self.confirmed_at:
            msg = "Placement expiry must follow its database observation"
            raise ValueError(msg)
        return self


class PlacementLost(PlacementValue):
    """No current placement authority, independently of any delivery outcome."""

    subscription_id: UUID


class PlacementUncertainError(RuntimeError):
    """Database outcome unknown; reconcile in a fresh session before authorizing intake."""


class PlacementAuthority:
    """One shared process-local guard per subscription, owned by the placement provider.

    A conservative monotonic deadline starts BEFORE database I/O. Database time
    decides ownership; elapsed local time can only shorten the confirmed budget.
    A lost guard cannot reopen while its previous local consumer is still alive.
    """

    def __init__(
        self, worker: WorkerIdentity, subscription_id: UUID, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """Keep one guard and one local reservation for this process/subscription pair."""
        self.worker = worker
        self.subscription_id = subscription_id
        self._clock = clock
        self._lease: SubscriptionPlacementLease | None = None
        self._deadline = 0.0
        self._trusted = False
        self._local_owner: object | None = None
        self._changed = asyncio.Event()

    @property
    def lease(self) -> SubscriptionPlacementLease | None:
        """Last confirmed lease, also usable for owner-checked release after stopping."""
        return self._lease

    @property
    def local_in_use(self) -> bool:
        """Include delayed construction/startup and incomplete shutdown."""
        return self._local_owner is not None

    def is_current(self) -> bool:
        """Fail closed immediately at the conservative local deadline."""
        if self._trusted and self._clock() >= self._deadline:
            self.invalidate()
        return self._trusted

    def confirm(self, lease: SubscriptionPlacementLease, *, request_started: float) -> bool:
        """Publish a successful commit or reconciled read; callable only by the provider."""
        if lease.owner != self.worker or lease.subscription_id != self.subscription_id:
            msg = "Placement does not match this worker and subscription"
            raise ValueError(msg)
        was_current = self.is_current()
        if self.local_in_use and not was_current:
            return False
        self._lease = lease
        self._deadline = request_started + (lease.expires_at - lease.confirmed_at).total_seconds()
        self._trusted = self._clock() < self._deadline
        self._changed.set()
        return self._trusted

    def invalidate(self) -> None:
        """Close admission on lost/untrusted ownership without changing durable evidence."""
        self._trusted = False
        self._changed.set()

    def reserve_local(self, owner: object) -> bool:
        """Serialize local construction across supervisors sharing this guard."""
        if not self.is_current() or (self._local_owner is not None and self._local_owner is not owner):
            return False
        self._local_owner = owner
        return True

    def local_stopped(self, owner: object) -> None:
        """Only the reserving supervisor can confirm its runner has fully stopped."""
        if self._local_owner is owner:
            self._local_owner = None

    async def wait_lost(self) -> None:
        """Observe renewal/invalidation independently of slow startup and run tasks."""
        while self.is_current():
            self._changed.clear()
            try:
                async with asyncio.timeout(max(0.0, self._deadline - self._clock())):
                    await self._changed.wait()
            except TimeoutError:
                self.invalidate()
