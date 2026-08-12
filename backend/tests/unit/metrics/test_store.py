"""Unit tests for the MetricsStore in-memory storage layer."""

from datetime import UTC, datetime, timedelta

from syntara.metrics.store import MetricsStore
from syntara.metrics.types import METRIC_CATEGORIES, MetricRecord, MetricsCategoryType, MetricType


def _make_record(
    metric_type: MetricType = MetricType.LLM_DURATION,
    value: float = 100.0,
    unit: str = "ms",
    labels: dict[str, str] | None = None,
    created_at: datetime | None = None,
) -> MetricRecord:
    """Factory helper for constructing MetricRecord instances."""
    record = MetricRecord(
        metric_type=metric_type,
        value=value,
        unit=unit,
        labels=labels or {},
    )
    if created_at is not None:
        record.created_at = created_at
    return record


# =============================================================================
# Basic CRUD
# =============================================================================


class TestStoreBasicOperations:
    """Tests for add / count / clear."""

    def test_add_and_count(self) -> None:
        """Adding records increments the count."""
        store = MetricsStore()
        assert store.count() == 0
        store.add(_make_record())
        assert store.count() == 1
        store.add(_make_record())
        assert store.count() == 2

    def test_clear(self) -> None:
        """clear() removes all records."""
        store = MetricsStore()
        for _ in range(5):
            store.add(_make_record())
        assert store.count() == 5
        store.clear()
        assert store.count() == 0

    def test_max_records_eviction(self) -> None:
        """Store respects max_records by evicting the oldest record."""
        store = MetricsStore(max_records=3)
        for i in range(5):
            store.add(_make_record(value=float(i)))
        assert store.count() == 3
        values = [r.value for r in store.query()]
        assert values == [2.0, 3.0, 4.0]


# =============================================================================
# Querying
# =============================================================================


class TestStoreQuery:
    """Tests for querying with filters."""

    def test_query_all(self) -> None:
        """Query without filters returns every record."""
        store = MetricsStore()
        for _ in range(3):
            store.add(_make_record())
        results = list(store.query())
        assert len(results) == 3

    def test_query_by_metric_type(self) -> None:
        """Filter by a single MetricType."""
        store = MetricsStore()
        store.add(_make_record(metric_type=MetricType.LLM_DURATION))
        store.add(_make_record(metric_type=MetricType.CACHE_HIT))
        store.add(_make_record(metric_type=MetricType.LLM_DURATION))

        results = list(store.query(metric_types={MetricType.LLM_DURATION}))
        assert len(results) == 2
        assert all(r.metric_type == MetricType.LLM_DURATION for r in results)

    def test_query_by_category(self) -> None:
        """Filter by category name ('llm', 'cache', etc.)."""
        store = MetricsStore()
        store.add(_make_record(metric_type=MetricType.LLM_DURATION))
        store.add(_make_record(metric_type=MetricType.LLM_TOKENS_INPUT))
        store.add(_make_record(metric_type=MetricType.CACHE_HIT))

        results = list(store.query(metric_types=set(METRIC_CATEGORIES[MetricsCategoryType.LLM])))
        assert len(results) == 2

    def test_query_by_time_range(self) -> None:
        """Only records within the time window are returned."""
        store = MetricsStore()
        now = datetime.now(UTC)
        old = now - timedelta(hours=2)
        recent = now - timedelta(minutes=5)

        store.add(_make_record(value=1.0, created_at=old))
        store.add(_make_record(value=2.0, created_at=recent))
        store.add(_make_record(value=3.0, created_at=now))

        results = list(
            store.query(
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(seconds=1),
            )
        )
        assert len(results) == 2
        assert {r.value for r in results} == {2.0, 3.0}

    def test_query_by_labels(self) -> None:
        """Only records whose labels are a superset of the filter are returned."""
        store = MetricsStore()
        store.add(_make_record(labels={"model": "gpt-4", "status": "success"}))
        store.add(_make_record(labels={"model": "claude", "status": "success"}))
        store.add(_make_record(labels={"model": "gpt-4", "status": "error"}))

        results = list(store.query(labels={"model": "gpt-4"}))
        assert len(results) == 2

        results = list(store.query(labels={"model": "gpt-4", "status": "success"}))
        assert len(results) == 1

    def test_query_combined_filters(self) -> None:
        """Multiple filters combine as AND logic."""
        store = MetricsStore()
        store.add(
            _make_record(
                metric_type=MetricType.LLM_DURATION,
                labels={"model": "gpt-4"},
            )
        )
        store.add(
            _make_record(
                metric_type=MetricType.CACHE_HIT,
                labels={"model": "gpt-4"},
            )
        )
        store.add(
            _make_record(
                metric_type=MetricType.LLM_DURATION,
                labels={"model": "claude"},
            )
        )

        results = list(
            store.query(
                metric_types={MetricType.LLM_DURATION},
                labels={"model": "gpt-4"},
            )
        )
        assert len(results) == 1

    def test_query_none_types_returns_everything(self) -> None:
        """metric_types=None returns all records regardless of type."""
        store = MetricsStore()
        store.add(_make_record(metric_type=MetricType.LLM_DURATION))
        store.add(_make_record(metric_type=MetricType.CACHE_HIT))

        results = list(store.query(metric_types=None))
        assert len(results) == 2


# =============================================================================
# Retention / cleanup
# =============================================================================


class TestStoreRetention:
    """Tests for automatic and manual retention enforcement."""

    def test_cleanup_removes_expired(self) -> None:
        """cleanup() removes records older than the retention period."""
        store = MetricsStore(retention_seconds=3600)
        now = datetime.now(UTC)
        store.add(_make_record(value=1.0, created_at=now - timedelta(hours=2)))
        store.add(_make_record(value=2.0, created_at=now))

        removed = store.cleanup()
        assert removed == 1
        assert store.count() == 1

        remaining = next(iter(store.query()))
        assert remaining.created_at >= now - timedelta(seconds=1)

    def test_cleanup_no_expired(self) -> None:
        """cleanup() is a no-op when nothing has expired."""
        store = MetricsStore(retention_seconds=3600)
        store.add(_make_record())
        removed = store.cleanup()
        assert removed == 0
        assert store.count() == 1

    def test_retention_property(self) -> None:
        """Retention property exposes the configured timedelta."""
        store = MetricsStore(retention_seconds=7200)
        assert store.retention == timedelta(seconds=7200)

    def test_max_records_property(self) -> None:
        """Max_records property exposes the configured limit."""
        store = MetricsStore(max_records=500)
        assert store.max_records == 500
