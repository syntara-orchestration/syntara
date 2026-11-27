"""Transport-neutral local runtime contracts, without scheduling authority."""

import random
import sqlite3
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import Field

from syntara.core.constants import EventSchedulingDefaults
from syntara.core.exceptions import SyntaraError
from syntara.eventstreams.core.deduplication import DeliveryValue
from syntara.eventstreams.core.inspection_spool import InspectionSpool
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot


def connection_retry_delay(failure_count: int) -> float:
    """Return jittered exponential backoff for a positive connection failure count."""
    # Retries have no attempt limit; bound the exponent before computing it.
    exponent = min(failure_count - 1, EventSchedulingDefaults.MAX_BACKOFF_SECONDS.bit_length())
    return float(
        min(2**exponent, EventSchedulingDefaults.MAX_BACKOFF_SECONDS) * random.uniform(0.5, 1.0)  # noqa: S311 - connection retry jitter, not security
    )


class RuntimeState(StrEnum):
    """Local convergence, distinct from desired state and durable delivery outcomes."""

    STOPPED = "stopped"
    STARTING = "starting"
    ACTIVE = "active"
    DRAINING = "draining"
    BACKOFF = "backoff"
    BLOCKED = "blocked"


class RuntimeFailureCode(StrEnum):
    """Safe runtime failures; never retain underlying exception text."""

    CONFIGURATION_UNAVAILABLE = "configuration_unavailable"
    CONNECTION_UNAVAILABLE = "connection_unavailable"
    RUNNER_FAILED = "runner_failed"
    STOP_INCOMPLETE = "stop_incomplete"
    PLACEMENT_LOST = "placement_lost"
    LOCAL_RUNNER_BUSY = "local_runner_busy"


class SubscriptionRuntimeError(SyntaraError):
    """Factory/adapter failure classified by the supervisor's retry policy."""

    def __init__(self, code: RuntimeFailureCode, *, transient: bool = False, reason: str | None = None) -> None:
        """Expose a fixed reason and retry classification without customer data."""
        self.code = code
        self.transient = transient
        self.reason = reason if reason is not None else code.value
        super().__init__(self.reason)


class RunnerStatus(DeliveryValue):
    """Sanitized observation, never evidence authorizing scheduling or commits."""

    state: RuntimeState
    reason: str | None = Field(default=None, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    permanent_content_error: bool = False


class RuntimeRevision(DeliveryValue):
    """Publication and source binding applied to one immutable runner."""

    source_id: UUID
    source_generation: int
    configuration_revision: int
    published_version_id: UUID

    @classmethod
    def from_snapshot(cls, snapshot: SubscriptionSnapshot) -> "RuntimeRevision":
        """Include publication changes that do not increment configuration revision."""
        return cls(
            source_id=snapshot.source_id,
            source_generation=snapshot.source_generation,
            configuration_revision=snapshot.configuration_revision,
            published_version_id=snapshot.published_version_id,
        )


class SubscriptionRuntimeStatus(RunnerStatus):
    """Requested and applied local state for later reconciliation/control callers."""

    subscription_id: UUID
    desired_revision: RuntimeRevision | None
    desired_active: bool
    applied_revision: RuntimeRevision | None
    failure_count: int = 0
    retry_at: datetime | None = None
    circuit_open: bool = False


@dataclass
class PendingInspections:
    """Exact replay evidence for one partition, bounded at intake."""

    offsets: set[int] = field(default_factory=set)
    matches: dict[int, datetime] = field(default_factory=dict)
    read_gap: tuple[int, int] | None = None
    _spill: InspectionSpool | None = field(default=None, init=False, repr=False, compare=False)
    _spill_shared: bool = field(default=False, init=False, repr=False, compare=False)
    _spill_match_overlaps: set[int] = field(default_factory=set, init=False, repr=False, compare=False)

    def __len__(self) -> int:
        """Count pending evidence for intake budgeting."""
        spilled = self._spill.count if self._spill is not None else 0
        return len(self.offsets) + len(self.matches) + spilled - len(self._spill_match_overlaps)

    @property
    def first(self) -> int | None:
        """Return the first offset that still requires inspection or delivery."""
        candidates = (
            min(self.offsets, default=None),
            min(self.matches, default=None),
            self._spill.first if self._spill is not None else None,
        )
        return min((offset for offset in candidates if offset is not None), default=None)

    def reserve_replay_read(self, limit: int) -> bool:
        """Keep room for the next result, spilling old exact evidence if needed."""
        if len(self.offsets) + len(self.matches) < limit:
            return True
        try:
            spill = self._writable_spill()
            spill.save(self.offsets, self.matches)
        except (OSError, sqlite3.Error):
            return False
        self.offsets.clear()
        self.matches.clear()
        self._spill_match_overlaps.clear()
        return True

    def gap_covers(self, start: int, offset: int) -> bool:
        """Return whether a verified read skipped this part of the cursor."""
        return self.read_gap is not None and self.read_gap[0] <= start <= offset < self.read_gap[1]

    def _writable_spill(self) -> InspectionSpool:
        try:
            if self._spill is None:
                self._spill = InspectionSpool()
            elif self._spill_shared:
                self._spill = self._spill.copy()
        except OSError as exc:
            msg = "Local replay evidence storage is unavailable"
            raise sqlite3.OperationalError(msg) from exc
        self._spill_shared = False
        return self._spill

    def remember(self, offset: int) -> None:
        """Remember a delivered offset unless its match is already known."""
        if offset in self.matches or offset in self.offsets:
            return
        # Record the observation before inspecting spilled evidence. An I/O
        # failure must leave this offset guarded.
        self.offsets.add(offset)
        if self._spill is not None:
            with suppress(sqlite3.Error):
                if self._spill.find(offset)[0]:
                    self.offsets.discard(offset)

    def remember_match(self, offset: int, received_at: datetime) -> None:
        """Freeze the first match and receipt time for this offset."""
        original = self.matches.setdefault(offset, received_at)
        self.offsets.discard(offset)
        if self._spill is None:
            return
        # Keep the in-memory match until the spill can confirm it.
        with suppress(sqlite3.Error):
            exists, saved = self._spill.find(offset)
            if exists:
                if saved is None:
                    # Count the known row once even if saving the match fails.
                    self._spill_match_overlaps.add(offset)
                    self._writable_spill().remember_match(offset, original)
                del self.matches[offset]
                self._spill_match_overlaps.discard(offset)

    def requires_delivery(self, offset: int) -> bool:
        """Require terminal evidence when validation alone cannot resolve an offset."""
        return self.matched_at(offset) is not None

    def matched_at(self, offset: int) -> datetime | None:
        """Read the original receipt time for a previously matched record."""
        saved = self._spill.find(offset)[1] if self._spill is not None else None
        return saved if saved is not None else self.matches.get(offset)

    def resolve(self, offset: int) -> None:
        """Retire evidence for the resolved offset."""
        if self._spill is not None and self._spill.find(offset)[0] and not self._writable_spill().resolve(offset):
            self._spill = None
        self.offsets.discard(offset)
        self.matches.pop(offset, None)
        self._spill_match_overlaps.discard(offset)

    def cover_before(self, next_offset: int) -> None:
        """Retire offsets covered by an authoritative group checkpoint."""
        first_spilled = self._spill.first if self._spill is not None else None
        if (
            first_spilled is not None
            and first_spilled < next_offset
            and not self._writable_spill().cover_before(next_offset)
        ):
            self._spill = None
        self.offsets = {offset for offset in self.offsets if offset >= next_offset}
        self.matches = {offset: received_at for offset, received_at in self.matches.items() if offset >= next_offset}
        self._spill_match_overlaps.intersection_update(self.matches)

    def copy(self) -> "PendingInspections":
        """Copy evidence before sharing it across runner or assignment lifetimes."""
        duplicate = PendingInspections(self.offsets.copy(), self.matches.copy(), self.read_gap)
        duplicate._spill = self._spill
        duplicate._spill_shared = self._spill_shared = self._spill is not None
        duplicate._spill_match_overlaps = self._spill_match_overlaps.copy()
        return duplicate


class SubscriptionRunner(Protocol):
    """One immutable runtime; stop must also close admission and partial startup."""

    @property
    def snapshot(self) -> SubscriptionSnapshot:
        """Return the frozen subscription binding used to construct this runner."""
        ...

    @property
    def status(self) -> RunnerStatus:
        """Observe initialization/holds without exposing transport internals."""
        ...

    def bind_placement(self, permits_admission: Callable[[], bool]) -> None:
        """Hold admission closed and install the live placement guard before startup."""
        ...

    def open_admission(self) -> bool:
        """Open only under the current guard, after the supervisor rechecks startup."""
        ...

    def pending_inspections(self) -> dict[int, PendingInspections]:
        """Return positions that still require inspection when this runner stops."""
        ...

    def restore_inspections(self, inspections: dict[int, PendingInspections]) -> None:
        """Restore outstanding inspections from the same publication before startup."""
        ...

    async def close_admission(self) -> None:
        """Pause and bound drain after placement loss; preserve admitted delivery tokens."""
        ...

    async def start(self) -> None:
        """Start idempotently; classify configuration/connection failures safely."""
        ...

    async def run(self) -> None:
        """Serve until drained/stopped, releasing client resources on exit."""
        ...

    async def drain(self) -> None:
        """Close admission before waiting; preserve all unresolved durable evidence."""
        ...

    async def stop(self) -> None:
        """Drain and stop idempotently; raise if client shutdown is incomplete."""
        ...


class SubscriptionRunnerFactory(Protocol):
    """Compose completed services/client outside the transport-neutral supervisor."""

    async def __call__(self, snapshot: SubscriptionSnapshot) -> SubscriptionRunner:
        """Resolve the initial binding; classify failures with SubscriptionRuntimeError.

        Return an unstarted runner for exactly this snapshot; startup must not
        open intake before open_admission. Clean up any
        resources if construction fails before returning. Do not open a database
        transaction across client startup. The supervisor separately rechecks
        connection revisions during ordinary reconciliation.
        """
        ...
