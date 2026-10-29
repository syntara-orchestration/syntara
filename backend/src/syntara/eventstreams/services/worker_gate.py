"""Process-local dependency and lifecycle trust for the completed runner gate."""

import time
from collections.abc import Callable, Iterable
from uuid import UUID

from syntara.core.constants import EventWorkerDefaults
from syntara.eventstreams.core.runtime import RuntimeRevision
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.placement_service import SubscriptionPlacementService


class EventWorkerGate:
    """Local reads only; PostgreSQL and Kafka retain their independent authority."""

    def __init__(self, placement: SubscriptionPlacementService, *, clock: Callable[[], float] = time.monotonic) -> None:
        """Start closed until registration and authoritative desired-state reconciliation."""
        self._placement = placement
        self._clock = clock
        self._healthy = False
        self._accepting = True
        self._generation = 0
        self._write_generation: int | None = None
        self._until = 0.0
        self._membership_until = 0.0
        self._desired: dict[UUID, RuntimeRevision] = {}
        self._blocked: set[UUID] = set()

    @property
    def generation(self) -> int:
        """Identify failures observed after a reconciliation started."""
        return self._generation

    @property
    def scheduling_open(self) -> bool:
        """Prepared recovery requires database trust, independently of placement."""
        return self._healthy

    def database_failed(self) -> None:
        """Close every local cached-hit commit and new scheduling attempt."""
        self._healthy = False
        self._generation += 1

    def dependency_failed(self, snapshot: SubscriptionSnapshot) -> None:
        """Require authoritative lifecycle/recovery evidence before reopening."""
        self._blocked.add(snapshot.source_id)
        self.database_failed()

    def membership_confirmed(self, deadline: float, *, generation: int) -> None:
        """Record a committed heartbeat write without clearing a newer failure."""
        self._membership_until = deadline
        if generation == self._generation:
            self._write_generation = generation

    def reconciled(
        self,
        snapshots: Iterable[SubscriptionSnapshot],
        blocked_sources: set[UUID],
        *,
        generation: int,
        started: float,
    ) -> bool:
        """Require authoritative reads and a write confirmed since the last failure."""
        if generation != self._generation or self._write_generation != generation:
            return False
        self._desired = {snapshot.source_id: RuntimeRevision.from_snapshot(snapshot) for snapshot in snapshots}
        self._blocked = blocked_sources
        self._until = started + EventWorkerDefaults.RECONCILE_INTERVAL_SECONDS * 2
        self._healthy = True
        return True

    def admission_open(self, snapshot: SubscriptionSnapshot) -> bool:
        """Recovery holds fence new intake even while its owned transport repairs."""
        return self.transport_open(snapshot) and self.resolution_open(snapshot)

    def transport_open(self, snapshot: SubscriptionSnapshot) -> bool:
        """Allow a currently owned transport to start with record intake fenced."""
        return (
            self._accepting
            and self._healthy
            and self._clock() < min(self._until, self._membership_until)
            and self._desired.get(snapshot.source_id) == RuntimeRevision.from_snapshot(snapshot)
            and self._placement.authority(snapshot.subscription_id).is_current()
        )

    def resolution_open(self, snapshot: SubscriptionSnapshot) -> bool:
        """Block record advancement under recovery holds; frozen repair is independent."""
        return self._healthy and snapshot.source_id not in self._blocked

    def cache_trusted(self) -> bool:
        """Report database trust; let the cache provider enforce external epoch/skew assumptions."""
        return self._healthy

    def close_admission(self) -> None:
        """Close intake while preserving resolution of admitted handoffs during drain."""
        self._accepting = False
