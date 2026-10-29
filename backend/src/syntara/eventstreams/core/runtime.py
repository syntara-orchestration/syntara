"""Transport-neutral local runtime contracts, without scheduling authority."""

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import Field

from syntara.core.exceptions import SyntaraError
from syntara.eventstreams.core.deduplication import DeliveryValue
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot


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
    """Factory/adapter classification; only explicitly transient errors are retried."""

    def __init__(self, code: RuntimeFailureCode, *, transient: bool = False) -> None:
        """Expose a fixed reason and retry classification without customer data."""
        self.code = code
        self.transient = transient
        super().__init__(code.value)


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
        transaction across client startup or install live credential refresh.
        """
        ...
