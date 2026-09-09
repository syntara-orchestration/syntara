"""Bounded recovery loop shared by transport PoCs."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


class RecoveryService:
    def __init__(self, recover: Callable[[], Awaitable[int]], interval_seconds: float) -> None:
        self._recover = recover
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="scheduler-wakeup-recovery")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    async def _run(self) -> None:
        while not self._stop.is_set():
            await self._recover()
            try:
                await asyncio.wait_for(self._stop.wait(), self._interval_seconds)
            except TimeoutError:
                pass
