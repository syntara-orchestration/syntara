"""Isolated lifecycle runner for subscription supervision tests; no broker I/O."""

import asyncio

from syntara.eventstreams.core.runtime import RunnerStatus, RuntimeRevision, RuntimeState
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot


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
        self.accepting = False
        self.started = False
        self.stopped = False
        self.start_calls = 0
        self.drain_calls = 0
        self.stop_calls = 0

    @property
    def status(self) -> RunnerStatus:
        """Return the transport-neutral view supplied to the supervisor."""
        return self.observation

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
        self.started = self.accepting = True
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
        self.accepting = False
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
        self.accepting = False
        if self.stop_error is not None:
            raise self.stop_error
        self.stopped = True
        self.observation = RunnerStatus(state=RuntimeState.STOPPED)
        self.trace.append(("stop", RuntimeRevision.from_snapshot(self.snapshot)))
        self.exited.set()
