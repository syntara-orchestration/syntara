"""Periodic memory profiler for diagnosing RSS growth.

Enabled by setting the ``SYNTARA_MEMORY_PROFILING`` environment variable
to ``1``.  When active, a background asyncio task periodically logs:

* Process RSS (from ``/proc/self/status``)
* Top Python allocations by source line (via ``tracemalloc``)
* Top live object types by count (via ``gc.get_objects``)

tracemalloc adds measurable overhead (~10-30 % extra memory) so this
is intended for CI / staging diagnosis, not production.
"""

import asyncio
import gc
import linecache
import os
import tracemalloc

import structlog

logger = structlog.stdlib.get_logger("memory_profiler")

INTERVAL_SECONDS = int(os.environ.get("SYNTARA_MEMORY_PROFILING_INTERVAL", "60"))
TOP_ALLOCS = 15
TOP_OBJECTS = 10


def is_enabled() -> bool:
    return os.environ.get("SYNTARA_MEMORY_PROFILING", "") == "1"


def _rss_mb() -> float:
    """Read VmRSS from ``/proc/self/status`` (Linux only)."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024  # kB -> MB
    except OSError:
        pass
    return 0.0


def _format_top_allocations(snapshot: tracemalloc.Snapshot, limit: int = TOP_ALLOCS) -> list[str]:
    stats = snapshot.statistics("lineno")
    lines: list[str] = []
    for idx, stat in enumerate(stats[:limit], 1):
        frame = stat.traceback[0]
        lines.append(f"  #{idx}: {frame.filename}:{frame.lineno} -- {stat.size / 1024:.1f} KiB ({stat.count} blocks)")
        src = linecache.getline(frame.filename, frame.lineno).strip()
        if src:
            lines.append(f"        {src}")
    return lines


def _format_top_objects(limit: int = TOP_OBJECTS) -> list[str]:
    """Count live objects by type."""
    type_counts: dict[str, int] = {}
    for obj in gc.get_objects():
        name = type(obj).__name__
        type_counts[name] = type_counts.get(name, 0) + 1
    sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
    return [f"  {name}: {count}" for name, count in sorted_types[:limit]]


async def memory_profiler_loop() -> None:
    """Periodically log memory diagnostics to stdout."""
    if not tracemalloc.is_tracing():
        tracemalloc.start(25)
        logger.info("tracemalloc started", depth=25)

    while True:
        await asyncio.sleep(INTERVAL_SECONDS)
        try:
            rss = _rss_mb()
            snapshot = tracemalloc.take_snapshot()
            snapshot = snapshot.filter_traces(
                [
                    tracemalloc.Filter(False, "<frozen *>"),
                    tracemalloc.Filter(False, "<unknown>"),
                    tracemalloc.Filter(False, tracemalloc.__file__),
                ]
            )
            current, peak = tracemalloc.get_traced_memory()

            logger.info(
                "memory_profile",
                rss_mb=round(rss, 1),
                traced_current_mb=round(current / 1024 / 1024, 1),
                traced_peak_mb=round(peak / 1024 / 1024, 1),
                pid=os.getpid(),
            )

            top_allocs = _format_top_allocations(snapshot)
            top_objs = _format_top_objects()

            report = (
                f"=== Memory Profile (RSS: {rss:.1f} MB, "
                f"traced: {current / 1024 / 1024:.1f}/{peak / 1024 / 1024:.1f} MB) ===\n"
                "Top allocations by line:\n"
                + "\n".join(top_allocs)
                + "\nTop object types by count:\n"
                + "\n".join(top_objs)
                + "\n"
                + "=" * 60
            )
            print(report, flush=True)  # noqa: T201
        except Exception:
            logger.exception("memory profiler tick failed")
