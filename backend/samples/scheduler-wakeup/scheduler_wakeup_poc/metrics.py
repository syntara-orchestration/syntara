"""Small, transport-neutral metrics surface for PoC reporting."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from time import monotonic_ns


@dataclass
class Metrics:
    """In-memory counters and timestamp samples, suitable for test assertions."""

    counters: Counter[str] = field(default_factory=Counter)
    timestamps_ns: dict[str, int] = field(default_factory=dict)

    def increment(self, name: str) -> None:
        self.counters[name] += 1

    def mark(self, stage: str, correlation_id: str) -> None:
        self.timestamps_ns[f"{correlation_id}:{stage}"] = monotonic_ns()

    def latency_ms(self, start: str, end: str, correlation_id: str) -> float | None:
        begin = self.timestamps_ns.get(f"{correlation_id}:{start}")
        finish = self.timestamps_ns.get(f"{correlation_id}:{end}")
        return None if begin is None or finish is None else (finish - begin) / 1_000_000
