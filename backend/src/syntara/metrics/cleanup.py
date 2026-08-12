"""Periodic cleanup worker for the in-memory metrics store.

Wires the existing :meth:`MetricsRecorder.cleanup` (time-based eviction of
stale records) into a :class:`PeriodicWorker` so that expired records are
pruned automatically without waiting for the ``deque`` ``maxlen`` cap.

Uses ``coordinate=False`` because each process owns its own in-memory
store and must trim it independently.
"""

from __future__ import annotations

import asyncio
import ctypes
import ctypes.util
import gc
import sys
from typing import TYPE_CHECKING

import structlog

from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.workers.periodic import PeriodicWorker
from syntara.metrics.dependencies import get_metrics_recorder

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)

_libc: ctypes.CDLL | None = None
if sys.platform == "linux":
    _libc_name = ctypes.util.find_library("c")
    if _libc_name:
        _libc = ctypes.CDLL(_libc_name, use_errno=True)


def release_memory_to_os() -> None:
    """Ask glibc to return freed heap pages to the OS.

    On Linux, CPython's allocator (pymalloc) and glibc can both retain
    freed pages in the process address space.  ``malloc_trim(0)`` nudges
    glibc to release them.  This is a no-op on non-Linux platforms.
    """
    if _libc is not None and hasattr(_libc, "malloc_trim"):
        _libc.malloc_trim(0)


async def cleanup_stale_metrics(
    _session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Evict expired records from the process-local metrics store.

    This is the callback invoked by :class:`PeriodicWorker` each cycle.
    The ``session_factory`` parameter is required by the worker interface
    but unused here since the metrics store is purely in-memory.

    Always calls ``gc.collect()`` and ``malloc_trim`` regardless of whether
    records were pruned, to combat glibc per-thread arena fragmentation
    that can otherwise retain hundreds of MB of freed heap pages.
    """
    recorder = get_metrics_recorder()
    removed = await asyncio.to_thread(recorder.cleanup)
    if removed:
        logger.debug("metrics_cleanup_completed", records_removed=removed)
    gc.collect()
    release_memory_to_os()


def get_metrics_cleanup_worker() -> PeriodicWorker:
    """Return the application-wide metrics-cleanup PeriodicWorker."""
    settings = get_settings()
    return PeriodicWorker(
        name="metrics-store-cleanup",
        interval_seconds=settings.metrics_cleanup_interval_seconds,
        session_factory=AsyncSessionLocal,
        callback=cleanup_stale_metrics,
        coordinate=False,
    )
