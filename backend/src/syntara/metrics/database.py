"""Database metrics instrumentation via SQLAlchemy engine events.

Records three metric families for the ``DATABASE`` component category:

* **DATABASE_QUERY_RESPONSE_TIME** — wall-clock duration of each SQL
  statement executed through the async engine.
* **DATABASE_CONNECTION_POOL_UTILIZATION** — ratio of checked-out
  connections to the pool capacity, sampled after every query.
* **DATABASE_TRANSACTION_RATE** — incremented on each ``COMMIT``.

All recordings go through :func:`get_metrics_recorder` so they appear in
both the in-memory store (``/_internal/metrics/records``) and the
Prometheus scrape endpoint (``/metrics``).

Usage::

    from syntara.metrics.database import install_database_metrics
    install_database_metrics(engine)

Call once at application startup, after the engine is created.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import event

if TYPE_CHECKING:
    from sqlalchemy import Connection
    from sqlalchemy.engine import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine
    from sqlalchemy.pool import Pool

    from syntara.metrics.recorder import MetricsRecorder

logger = structlog.stdlib.get_logger(__name__)

_QUERY_START_KEY = "_nexus_query_start"


def _before_cursor_execute(
    conn: Connection,
    _cursor: Any,  # noqa: ANN401
    _statement: str,
    _parameters: Any,  # noqa: ANN401
    _context: Any,  # noqa: ANN401
    _executemany: bool,  # noqa: FBT001
) -> None:
    """Stash the start timestamp on the connection so ``after`` can compute duration."""
    conn.info[_QUERY_START_KEY] = time.perf_counter()


def _after_cursor_execute(
    conn: Connection,
    _cursor: Any,  # noqa: ANN401
    statement: str,
    _parameters: Any,  # noqa: ANN401
    _context: Any,  # noqa: ANN401
    _executemany: bool,  # noqa: FBT001
) -> None:
    """Record query duration, pool utilization, and transaction rate."""
    start: float | None = conn.info.pop(_QUERY_START_KEY, None)
    if start is None:
        return

    duration_ms = (time.perf_counter() - start) * 1000

    try:
        from syntara.metrics.dependencies import get_metrics_recorder  # noqa: PLC0415
        from syntara.metrics.types import MetricType  # noqa: PLC0415

        recorder = get_metrics_recorder()

        recorder.record(
            MetricType.DATABASE_QUERY_RESPONSE_TIME,
            duration_ms,
            unit="ms",
            labels={"statement_type": _classify_statement(statement)},
        )

        _record_pool_utilization(conn, recorder)
    except Exception:  # noqa: BLE001
        logger.debug("database_metrics_recording_failed", exc_info=True)


def _on_commit(_conn: Connection) -> None:
    """Increment the database transaction counter on each COMMIT."""
    try:
        from syntara.metrics.dependencies import get_metrics_recorder  # noqa: PLC0415
        from syntara.metrics.types import MetricType  # noqa: PLC0415

        recorder = get_metrics_recorder()
        recorder.record(MetricType.DATABASE_TRANSACTION_RATE, 1.0, labels={})
        recorder.increment("db_transactions")
    except Exception:  # noqa: BLE001
        logger.debug("database_transaction_metric_failed", exc_info=True)


def _record_pool_utilization(conn: Connection, recorder: MetricsRecorder) -> None:
    """Sample the connection pool and record utilization as a ratio.

    Uses the ``QueuePool`` public API (``size()``, ``checkedout()``,
    ``overflow()``) and the stable ``_max_overflow`` attribute to compute
    capacity correctly, rather than parsing the ``status()`` string.

    Pools that are not ``QueuePool`` (e.g. ``NullPool``, ``StaticPool``)
    are silently skipped.
    """
    from sqlalchemy.pool import QueuePool as _QueuePool  # noqa: PLC0415

    from syntara.metrics.types import MetricType  # noqa: PLC0415

    pool: Pool | None = conn.engine.pool
    if not isinstance(pool, _QueuePool):
        return

    checked_out: int = pool.checkedout()
    pool_size: int = pool.size()
    overflow: int = pool.overflow()
    max_overflow: int = pool._max_overflow  # noqa: SLF001

    capacity = 0 if max_overflow == -1 else pool_size + max_overflow

    utilization = checked_out / capacity if capacity > 0 else 0.0

    recorder.record(
        MetricType.DATABASE_CONNECTION_POOL_UTILIZATION,
        utilization,
        labels={
            "checked_out": str(checked_out),
            "pool_size": str(pool_size),
            "overflow": str(overflow),
            "max_overflow": str(max_overflow),
        },
    )


def _classify_statement(statement: str) -> str:
    """Derive a coarse statement type label from the SQL text.

    Returns one of ``SELECT``, ``INSERT``, ``UPDATE``, ``DELETE``, or
    ``OTHER``.  Only the first non-whitespace token is inspected.
    """
    first_word = statement.lstrip().split(None, 1)[0].upper() if statement else "OTHER"
    if first_word in {"SELECT", "INSERT", "UPDATE", "DELETE"}:
        return first_word
    return "OTHER"


def install_database_metrics(async_engine: AsyncEngine) -> None:
    """Attach SQLAlchemy event listeners to the engine's sync internals.

    Must be called once per engine at application startup.  Safe to call
    with the same engine multiple times (listeners are not duplicated).

    Args:
        async_engine: The :class:`~sqlalchemy.ext.asyncio.AsyncEngine`
            whose underlying synchronous engine will be instrumented.

    """
    sync_engine: Engine = async_engine.sync_engine

    if not event.contains(sync_engine, "before_cursor_execute", _before_cursor_execute):
        event.listen(sync_engine, "before_cursor_execute", _before_cursor_execute)

    if not event.contains(sync_engine, "after_cursor_execute", _after_cursor_execute):
        event.listen(sync_engine, "after_cursor_execute", _after_cursor_execute)

    if not event.contains(sync_engine, "commit", _on_commit):
        event.listen(sync_engine, "commit", _on_commit)

    logger.info("database_metrics_installed", engine=str(sync_engine.url))
