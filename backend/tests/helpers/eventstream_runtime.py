"""Isolated lifecycle runner for subscription supervision tests; no broker I/O."""

import asyncio
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from syntara.eventstreams.core.placement import PlacementAuthority, SubscriptionPlacementLease, WorkerIdentity
from syntara.eventstreams.core.runtime import RunnerStatus, RuntimeRevision, RuntimeState
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot


def confirmed_placement(snapshot: SubscriptionSnapshot) -> PlacementAuthority:
    """Inject confirmed ownership to isolate supervisor tests from placement persistence."""
    worker = WorkerIdentity(deployment_id=snapshot.deployment_id)
    authority = PlacementAuthority(worker, snapshot.subscription_id)
    now = datetime.now(UTC)
    authority.confirm(
        SubscriptionPlacementLease(
            subscription_id=snapshot.subscription_id,
            owner=worker,
            confirmed_at=now,
            expires_at=now + timedelta(seconds=60),
        ),
        request_started=time.monotonic(),
    )
    return authority


class IsolatedSubscriptionRunner:
    """Exercise real supervision with explicit lifecycle barriers and safe observations."""

    def __init__(self, snapshot: SubscriptionSnapshot, trace: list[tuple[str, RuntimeRevision]]) -> None:
        """Keep the exact frozen binding and record only observable lifecycle actions."""
        self.snapshot = snapshot
        self.trace = trace
        self.observation = RunnerStatus(state=RuntimeState.STARTING)
        self.start_error: Exception | None = None
        self.run_error: Exception | None = None
        self.stop_error: Exception | None = None
        self.start_release: asyncio.Event | None = None
        self.drain_release: asyncio.Event | None = None
        self.start_entered = asyncio.Event()
        self.run_entered = asyncio.Event()
        self.drain_entered = asyncio.Event()
        self.exited = asyncio.Event()
        self._accepting = False
        self._placement: Callable[[], bool] | None = None
        self.open_calls = 0
        self.started = False
        self.stopped = False
        self.start_calls = 0
        self.drain_calls = 0
        self.stop_calls = 0

    @property
    def status(self) -> RunnerStatus:
        """Return the transport-neutral view supplied to the supervisor."""
        return self.observation

    @property
    def accepting(self) -> bool:
        """Observe synchronous admission closure before asynchronous stop finishes."""
        return self._accepting and (self._placement is None or self._placement())

    def bind_placement(self, permits_admission: Callable[[], bool]) -> None:
        """Install authority before startup without opening admission."""
        self._placement = permits_admission
        self._accepting = False

    def open_admission(self) -> bool:
        """Allow tests to distinguish client startup from admitted processing."""
        self.open_calls += 1
        self._accepting = not self.stopped and self._placement is not None and self._placement()
        return self._accepting

    async def start(self) -> None:
        """Permit a test to hold or fail startup without opening any connection."""
        if self.started:
            return
        self.start_calls += 1
        self.start_entered.set()
        if self.start_release is not None:
            await self.start_release.wait()
        if self.start_error is not None:
            raise self.start_error
        self.started = True
        self._accepting = self._placement is None
        self.observation = RunnerStatus(state=RuntimeState.ACTIVE)
        self.trace.append(("start", RuntimeRevision.from_snapshot(self.snapshot)))

    async def run(self) -> None:
        """Mirror the completed runner's resource cleanup on normal/failed exit."""
        self.run_entered.set()
        try:
            if self.run_error is not None:
                raise self.run_error
            await self.exited.wait()
        finally:
            await self.stop()

    async def drain(self) -> None:
        """Close admission before a controllable drain wait."""
        self.drain_calls += 1
        self._accepting = False
        self.observation = RunnerStatus(state=RuntimeState.DRAINING)
        self.drain_entered.set()
        self.trace.append(("drain", RuntimeRevision.from_snapshot(self.snapshot)))
        if self.drain_release is not None:
            await self.drain_release.wait()
        self.exited.set()

    async def stop(self) -> None:
        """Fail visibly or confirm idempotent local shutdown."""
        if self.stopped:
            return
        self.stop_calls += 1
        self._accepting = False
        if self.stop_error is not None:
            raise self.stop_error
        self.stopped = True
        self.observation = RunnerStatus(state=RuntimeState.STOPPED)
        self.trace.append(("stop", RuntimeRevision.from_snapshot(self.snapshot)))
        self.exited.set()

    async def close_admission(self) -> None:
        """Use the same bounded-drain port as the real runner."""
        await self.drain()
