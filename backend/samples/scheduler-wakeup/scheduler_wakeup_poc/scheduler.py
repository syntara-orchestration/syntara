"""Shared bounded scheduling core used by every transport adapter."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from .contracts import Claim, PassResult
from .metrics import Metrics


class ClaimingStore(Protocol):
    async def claim_ready(self, queue: str, owner: str, limit: int) -> list[Claim]: ...


Dispatch = Callable[[Claim], Awaitable[bool]]


class SchedulingCore:
    """Coalesces hints while preserving DB-backed claim ownership."""

    def __init__(
        self,
        store: ClaimingStore,
        owner_id: str,
        dispatch: Dispatch,
        *,
        claim_batch_size: int = 32,
        dispatch_limit: int = 128,
        metrics: Metrics | None = None,
    ) -> None:
        self._store = store
        self._owner_id = owner_id
        self._dispatch = dispatch
        self._claim_batch_size = claim_batch_size
        self._pass_lock = asyncio.Lock()
        self._credits = asyncio.Semaphore(dispatch_limit)
        self._dispatch_tasks: set[asyncio.Task[None]] = set()
        self.metrics = metrics or Metrics()

    async def run_pass(self, queue: str) -> PassResult:
        """Claim one bounded batch and hand it to supervised dispatch tasks."""
        async with self._pass_lock:
            claims = await self._store.claim_ready(queue, self._owner_id, self._claim_batch_size)
            self.metrics.increment("scheduling_passes")
            for claim in claims:
                await self._credits.acquire()
                task = asyncio.create_task(self._run_dispatch(claim), name=f"dispatch-{claim.attempt_id}")
                self._dispatch_tasks.add(task)
                task.add_done_callback(self._dispatch_tasks.discard)
            self.metrics.counters["claims"] += len(claims)
            return PassResult(
                claimed_count=len(claims),
                deferred_count=0,
                immediate_more=len(claims) == self._claim_batch_size,
            )

    async def _run_dispatch(self, claim: Claim) -> None:
        try:
            await self._dispatch(claim)
        finally:
            self._credits.release()

    async def wait_for_dispatches(self) -> None:
        """Wait for work claimed by this scheduler to reach the fake dispatcher."""
        while self._dispatch_tasks:
            await asyncio.gather(*tuple(self._dispatch_tasks))


class WakeDrainLoop:
    """Correct event clearing order for a volatile, coalescing wake source."""

    def __init__(self, scheduler: SchedulingCore) -> None:
        self._scheduler = scheduler
        self._events: dict[str, asyncio.Event] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def wake(self, queue: str) -> None:
        event = self._events.setdefault(queue, asyncio.Event())
        event.set()
        if queue not in self._tasks or self._tasks[queue].done():
            self._tasks[queue] = asyncio.create_task(self._run(queue), name=f"wake-drain-{queue}")

    async def wait_idle(self, queue: str) -> None:
        task = self._tasks.get(queue)
        if task is not None:
            await task
        await self._scheduler.wait_for_dispatches()

    async def _run(self, queue: str) -> None:
        event = self._events[queue]
        while True:
            await event.wait()
            event.clear()
            while True:
                result = await self._scheduler.run_pass(queue)
                if not result.immediate_more:
                    break
                await asyncio.sleep(0)
            if not event.is_set():
                return
