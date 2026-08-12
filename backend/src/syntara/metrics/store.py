"""In-memory metrics store with time-based retention and bounded capacity.

This module provides the storage layer for raw metric records.  Records are
kept in a bounded ``collections.deque`` so memory usage stays predictable
even under sustained high throughput.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from syntara.metrics.types import MetricRecord, MetricType


class MetricsStore:
    """Thread-safe in-memory metrics store with configurable retention.

    Args:
        retention_seconds: How long to retain raw metrics (default 24 h).
        max_records: Maximum number of records to store.  When exceeded the
            oldest record is silently evicted.

    """

    def __init__(
        self,
        retention_seconds: int = 3600,
        max_records: int = 100_000,
    ) -> None:
        """Initialise the store with the given retention and capacity limits."""
        self._retention = timedelta(seconds=retention_seconds)
        self._max_records = max_records
        self._records: deque[MetricRecord] = deque(maxlen=max_records)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add(self, record: MetricRecord) -> None:
        """Append a metric record to the store (thread-safe)."""
        with self._lock:
            self._records.append(record)

    # ------------------------------------------------------------------
    # Read / query operations
    # ------------------------------------------------------------------

    def query(
        self,
        *,
        metric_types: set[MetricType] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        labels: dict[str, str] | None = None,
    ) -> Iterator[MetricRecord]:
        """Yield records matching the given filters.

        Args:
            metric_types: When provided, only records whose ``metric_type``
                is in this set are returned.  Pass *None* (the default) to
                return all types.
            start_time: Lower bound of the time window (inclusive).
            end_time: Upper bound of the time window (inclusive).
            labels: Records must have *at least* these key-value pairs.

        """
        now = datetime.now(UTC)
        effective_start = start_time or (now - self._retention)
        effective_end = end_time or now

        with self._lock:
            snapshot = list(self._records)

        for record in snapshot:
            if record.created_at < effective_start or record.created_at > effective_end:
                continue
            if metric_types is not None and record.metric_type not in metric_types:
                continue
            if labels and not all(record.labels.get(k) == v for k, v in labels.items()):
                continue
            yield record

    def count(self) -> int:
        """Return the current number of stored records."""
        with self._lock:
            return len(self._records)

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def cleanup(self) -> int:
        """Remove records older than the retention period.

        Returns:
            The number of records removed.

        """
        cutoff = datetime.now(UTC) - self._retention
        with self._lock:
            original_count = len(self._records)
            self._records = deque(
                (r for r in self._records if r.created_at >= cutoff),
                maxlen=self._max_records,
            )
            return original_count - len(self._records)

    def clear(self) -> None:
        """Remove all records from the store."""
        with self._lock:
            self._records.clear()

    @property
    def retention(self) -> timedelta:
        """The configured retention period."""
        return self._retention

    @property
    def max_records(self) -> int:
        """The configured maximum capacity."""
        return self._max_records
