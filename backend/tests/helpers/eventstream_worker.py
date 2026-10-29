"""Isolated committed placement ports for process tests; no live coordination claims."""

import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import UUID

from syntara.eventstreams.core.placement import (
    PlacementLost,
    PlacementUncertainError,
    SubscriptionPlacementLease,
    WorkerIdentity,
    WorkerMembership,
)
from syntara.eventstreams.services.placement_service import SubscriptionPlacementService


class IsolatedPlacementPool:
    """Share authoritative fake rows across process identities in a unit test."""

    def __init__(self, deployment_id: UUID, active: Iterable[UUID] = ()) -> None:
        """Keep only unit-test membership, lease rows, and acknowledgement observations."""
        self.deployment_id = deployment_id
        self.active = set(active)
        self.candidates: Callable[[], Iterable[UUID]] | None = None
        self.members: dict[UUID, WorkerMembership] = {}
        self.leases: dict[UUID, SubscriptionPlacementLease] = {}
        self.trace: list[tuple[str, UUID]] = []


class IsolatedPlacementService(SubscriptionPlacementService):
    """Use real guards/value types while isolating database acknowledgement boundaries."""

    def __init__(self, pool: IsolatedPlacementPool, *, worker_id: UUID | None = None) -> None:
        """Reuse production authority guards with isolated persistence operations."""
        worker = WorkerIdentity(deployment_id=pool.deployment_id)
        if worker_id is not None:
            worker = worker.model_copy(update={"worker_id": worker_id})
        super().__init__(MagicMock(), worker)
        self.pool = pool
        self.claim_error = False
        self.renew_error = False
        self.reject_renewal = False
        self.release_error = False
        self.heartbeat_error = False
        self.claim_limits: list[int] = []

    async def heartbeat_worker(self, worker: WorkerIdentity, *, draining: bool) -> WorkerMembership:
        self._check_worker(worker)
        self._draining = self._draining or draining
        if self.heartbeat_error:
            msg = "isolated heartbeat failure"
            raise PlacementUncertainError(msg)
        member = WorkerMembership(
            worker=worker,
            draining=self._draining,
            heartbeat_until=datetime.now(UTC) + timedelta(seconds=self._settings.event_worker_liveness_seconds),
        )
        self.pool.members[worker.worker_id] = member
        self.pool.trace.append(("draining" if self._draining else "heartbeat", worker.worker_id))
        return member

    async def list_live_workers(self) -> list[WorkerMembership]:
        now = datetime.now(UTC)
        return [member for member in self.pool.members.values() if not member.draining and member.heartbeat_until > now]

    async def claim_subscriptions(self, worker: WorkerIdentity, *, limit: int) -> list[SubscriptionPlacementLease]:
        self._check_worker(worker)
        self._bound(limit)
        self.claim_limits.append(limit)
        if self._draining:
            return []
        if self.pool.candidates is not None:
            self.pool.active = set(self.pool.candidates())
        leases = []
        now, started = datetime.now(UTC), time.monotonic()
        for key in sorted(self.pool.active):
            current = self.pool.leases.get(key)
            if (
                (current is not None and current.expires_at > now)
                or self.authority(key).local_in_use
                or key in self._pending
            ):
                continue
            lease = self._lease(key, now, now + timedelta(seconds=self._settings.event_subscription_lease_seconds))
            self._pending.add(key)
            self.pool.leases[key] = lease
            leases.append(lease)
            if len(leases) == limit:
                break
        if self.claim_error:
            self.distrust()
            msg = "isolated lost claim acknowledgement"
            raise PlacementUncertainError(msg)
        for lease in leases:
            self.pool.trace.append(("claim_commit", lease.subscription_id))
            self._pending.discard(lease.subscription_id)
            self.authority(lease.subscription_id).confirm(lease, request_started=started)
        return leases

    async def reconcile_placement(self, subscription_id: UUID) -> SubscriptionPlacementLease | PlacementLost:
        key = subscription_id
        self.pool.trace.append(("reconcile", key))
        current = self.pool.leases.get(key)
        now = datetime.now(UTC)
        if current is not None and current.owner == self.worker and current.expires_at > now:
            lease = current.model_copy(update={"confirmed_at": now})
            if self.authority(key).confirm(lease, request_started=time.monotonic()):
                self._pending.discard(key)
                return lease
            self._pending.add(key)
        else:
            self._pending.discard(key)
        self.authority(key).invalidate()
        return PlacementLost(subscription_id=key)

    async def renew_placement(self, lease: SubscriptionPlacementLease) -> SubscriptionPlacementLease | PlacementLost:
        key = lease.subscription_id
        self.pool.trace.append(("renew", key))
        if self.renew_error:
            self.distrust()
            msg = "isolated renewal failure"
            raise PlacementUncertainError(msg)
        current = self.pool.leases.get(key)
        now = datetime.now(UTC)
        if (
            self.reject_renewal
            or current is None
            or current.owner != self.worker
            or current.expires_at <= now
            or current.expires_at != lease.expires_at
        ):
            self.authority(key).invalidate()
            return PlacementLost(subscription_id=key)
        renewed = self._lease(key, now, now + timedelta(seconds=self._settings.event_subscription_lease_seconds))
        self.pool.leases[key] = renewed
        self.authority(key).confirm(renewed, request_started=time.monotonic())
        return renewed

    async def release_placement(self, lease: SubscriptionPlacementLease) -> bool:
        key = lease.subscription_id
        assert not self.authority(key).local_in_use
        self.pool.trace.append(("release", key))
        if self.release_error:
            self._pending.add(key)
            self.distrust()
            msg = "isolated lost release acknowledgement"
            raise PlacementUncertainError(msg)
        current = self.pool.leases.get(key)
        self.authority(key).invalidate()
        if current is None or current.owner != self.worker or current.expires_at != lease.expires_at:
            return False
        del self.pool.leases[key]
        return True
