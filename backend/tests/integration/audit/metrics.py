"""Metrics collection utilities for audit integration tests.

Provides latency percentile calculation, throughput measurement, and
structured result reporting.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Generator

import structlog

from tests.integration.helpers.perf import compute_percentile

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class LatencyResult:
    """Latency measurement across multiple samples."""

    label: str
    samples: list[float] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.samples)

    @property
    def p50(self) -> float:
        return compute_percentile(self.samples, 50) if self.samples else 0.0

    @property
    def p95(self) -> float:
        return compute_percentile(self.samples, 95) if self.samples else 0.0

    @property
    def p99(self) -> float:
        return compute_percentile(self.samples, 99) if self.samples else 0.0

    @property
    def mean(self) -> float:
        return sum(self.samples) / len(self.samples) if self.samples else 0.0

    @property
    def min_ms(self) -> float:
        return min(self.samples) if self.samples else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.samples) if self.samples else 0.0

    def add(self, elapsed_ms: float) -> None:
        """Record a single latency sample in milliseconds."""
        self.samples.append(elapsed_ms)

    def summary(self) -> dict[str, Any]:
        """Return a dict suitable for structured logging or assertions."""
        return {
            "label": self.label,
            "count": self.count,
            "p50_ms": round(self.p50, 3),
            "p95_ms": round(self.p95, 3),
            "p99_ms": round(self.p99, 3),
            "mean_ms": round(self.mean, 3),
            "min_ms": round(self.min_ms, 3),
            "max_ms": round(self.max_ms, 3),
        }

    def log(self) -> None:
        logger.info("latency_result", **self.summary())


@dataclass
class ThroughputResult:
    """Throughput measurement for a batch operation."""

    label: str
    total_operations: int = 0
    elapsed_seconds: float = 0.0

    @property
    def ops_per_second(self) -> float:
        return self.total_operations / self.elapsed_seconds if self.elapsed_seconds > 0 else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "total_ops": self.total_operations,
            "elapsed_s": round(self.elapsed_seconds, 3),
            "ops_per_sec": round(self.ops_per_second, 1),
        }

    def log(self) -> None:
        logger.info("throughput_result", **self.summary())


@contextmanager
def measure_latency(result: LatencyResult) -> Generator[None, None, None]:
    """Context manager that records elapsed time as a latency sample.

    Usage::

        latency = LatencyResult(label="outbox_write")
        for _ in range(100):
            with measure_latency(latency):
                await do_write()
        latency.log()
    """
    start = time.monotonic()
    yield
    elapsed_ms = (time.monotonic() - start) * 1000
    result.add(elapsed_ms)


@asynccontextmanager
async def measure_latency_async(result: LatencyResult) -> AsyncGenerator[None, None]:
    """Async context manager that records elapsed time as a latency sample.

    Usage::

        latency = LatencyResult(label="outbox_write")
        for _ in range(100):
            async with measure_latency_async(latency):
                await do_write()
        latency.log()
    """
    start = time.monotonic()
    yield
    elapsed_ms = (time.monotonic() - start) * 1000
    result.add(elapsed_ms)


def measure_throughput(
    label: str,
    func: Callable[[], Any],
    iterations: int,
) -> ThroughputResult:
    """Run a synchronous function N times and measure throughput.

    Args:
        label: Human-readable label for the measurement.
        func: The function to call each iteration.
        iterations: Number of times to call the function.

    Returns:
        ThroughputResult with timing data.

    """
    result = ThroughputResult(label=label, total_operations=iterations)
    start = time.monotonic()
    for _ in range(iterations):
        func()
    result.elapsed_seconds = time.monotonic() - start
    result.log()
    return result


@dataclass
class PerformanceReport:
    """Aggregates multiple latency and throughput results for a test."""

    title: str
    latencies: list[LatencyResult] = field(default_factory=list)
    throughputs: list[ThroughputResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_latency(self, result: LatencyResult) -> None:
        self.latencies.append(result)

    def add_throughput(self, result: ThroughputResult) -> None:
        self.throughputs.append(result)

    def log_all(self) -> None:
        """Log all collected results."""
        logger.info("performance_report", title=self.title, **self.metadata)
        for lat in self.latencies:
            lat.log()
        for thr in self.throughputs:
            thr.log()

    def summary(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "latencies": [lat.summary() for lat in self.latencies],
            "throughputs": [thr.summary() for thr in self.throughputs],
            "metadata": self.metadata,
        }
