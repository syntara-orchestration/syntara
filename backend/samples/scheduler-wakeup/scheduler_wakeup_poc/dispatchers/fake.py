"""A deterministic fake dispatcher used by correctness and latency tests."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from ..contracts import Claim


class CompletionStore(Protocol):
    async def complete(self, claim: Claim, result: dict[str, Any]) -> bool: ...


class FakeDispatcher:
    def __init__(self, store: CompletionStore) -> None:
        self._store = store
        self.accepted: list[Claim] = []

    async def dispatch(self, claim: Claim, task: dict[str, Any] | None = None) -> bool:
        self.accepted.append(claim)
        await asyncio.sleep(float((task or {}).get("duration_ms", 10)) / 1000)
        return await self._store.complete(claim, {"status": "completed", "dispatcher": "fake"})
