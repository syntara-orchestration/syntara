"""Unit tests for database metrics instrumentation.

Tests cover the three database metric families:
- DATABASE_QUERY_RESPONSE_TIME — recorded on every SQL statement
- DATABASE_CONNECTION_POOL_UTILIZATION — sampled after every query
- DATABASE_TRANSACTION_RATE — incremented on each COMMIT
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from prometheus_client import CollectorRegistry

from syntara.metrics.database import (
    _after_cursor_execute,
    _before_cursor_execute,
    _classify_statement,
    _on_commit,
    install_database_metrics,
)
from syntara.metrics.recorder import MetricsRecorder
from syntara.metrics.types import MetricType

_EXECUTEMANY = False
_PATCH_RECORDER = "syntara.metrics.dependencies.get_metrics_recorder"


@pytest.fixture
def recorder() -> MetricsRecorder:
    """Fresh MetricsRecorder with an isolated Prometheus registry."""
    return MetricsRecorder(
        retention_seconds=3600,
        max_records=10_000,
        prometheus_registry=CollectorRegistry(),
    )


def _make_conn(
    *,
    pool_size: int = 10,
    checked_out: int = 2,
    overflow: int = 0,
    max_overflow: int = 10,
) -> MagicMock:
    """Build a mock SQLAlchemy Connection with pool metrics via public API."""
    from sqlalchemy.pool import QueuePool

    pool = MagicMock(spec=QueuePool)
    pool.size.return_value = pool_size
    pool.checkedout.return_value = checked_out
    pool.overflow.return_value = overflow
    pool._max_overflow = max_overflow
    engine = MagicMock()
    engine.pool = pool
    conn = MagicMock()
    conn.engine = engine
    conn.info = {}
    return conn


def _fire_before(conn: MagicMock, statement: str = "SELECT 1") -> None:
    """Helper to call _before_cursor_execute with the standard event signature."""
    _before_cursor_execute(conn, None, statement, None, None, _EXECUTEMANY)


def _fire_after(conn: MagicMock, statement: str = "SELECT 1") -> None:
    """Helper to call _after_cursor_execute with the standard event signature."""
    _after_cursor_execute(conn, None, statement, None, None, _EXECUTEMANY)


# =============================================================================
# Statement classification
# =============================================================================


class TestClassifyStatement:
    """Tests for _classify_statement helper."""

    def test_select(self) -> None:
        assert _classify_statement("SELECT id FROM users") == "SELECT"

    def test_insert(self) -> None:
        assert _classify_statement("INSERT INTO users (name) VALUES ('a')") == "INSERT"

    def test_update(self) -> None:
        assert _classify_statement("UPDATE users SET name='b'") == "UPDATE"

    def test_delete(self) -> None:
        assert _classify_statement("DELETE FROM users WHERE id=1") == "DELETE"

    def test_leading_whitespace(self) -> None:
        assert _classify_statement("  \n  SELECT 1") == "SELECT"

    def test_case_insensitive(self) -> None:
        assert _classify_statement("select * from t") == "SELECT"

    def test_other_statement(self) -> None:
        assert _classify_statement("CREATE TABLE t (id int)") == "OTHER"

    def test_empty_string(self) -> None:
        assert _classify_statement("") == "OTHER"


# =============================================================================
# Before/after cursor execute events
# =============================================================================


class TestBeforeAfterCursorExecute:
    """Tests for the SQLAlchemy event listener pair."""

    def test_before_stashes_timestamp(self) -> None:
        """_before_cursor_execute stores a start timestamp on conn.info."""
        conn = _make_conn()
        _fire_before(conn)
        assert "_nexus_query_start" in conn.info
        assert isinstance(conn.info["_nexus_query_start"], float)

    def test_after_records_query_duration(self, recorder: MetricsRecorder) -> None:
        """_after_cursor_execute records DATABASE_QUERY_RESPONSE_TIME."""
        conn = _make_conn()
        _fire_before(conn)

        with patch(_PATCH_RECORDER, return_value=recorder):
            _fire_after(conn)

        results = list(recorder.query(metric_types={MetricType.DATABASE_QUERY_RESPONSE_TIME}))
        assert len(results) == 1
        assert results[0].value >= 0
        assert results[0].unit == "ms"
        assert results[0].labels["statement_type"] == "SELECT"

    def test_after_records_pool_utilization(self, recorder: MetricsRecorder) -> None:
        """_after_cursor_execute records DATABASE_CONNECTION_POOL_UTILIZATION."""
        conn = _make_conn(pool_size=10, checked_out=2, overflow=0, max_overflow=10)
        _fire_before(conn)

        with patch(_PATCH_RECORDER, return_value=recorder):
            _fire_after(conn)

        results = list(recorder.query(metric_types={MetricType.DATABASE_CONNECTION_POOL_UTILIZATION}))
        assert len(results) == 1
        assert results[0].value == pytest.approx(2 / 20)  # 2 / (10 + 10)
        assert results[0].labels["checked_out"] == "2"
        assert results[0].labels["pool_size"] == "10"

    def test_after_without_before_is_noop(self, recorder: MetricsRecorder) -> None:
        """When _before_cursor_execute was not called, after is a safe no-op."""
        conn = _make_conn()

        with patch(_PATCH_RECORDER, return_value=recorder):
            _fire_after(conn)

        assert recorder.store.count() == 0

    def test_after_pops_start_key(self, recorder: MetricsRecorder) -> None:
        """The start timestamp is consumed (popped) after recording."""
        conn = _make_conn()
        _fire_before(conn)

        with patch(_PATCH_RECORDER, return_value=recorder):
            _fire_after(conn)

        assert "_nexus_query_start" not in conn.info

    def test_statement_type_label_for_insert(self, recorder: MetricsRecorder) -> None:
        """INSERT statement gets the correct label."""
        conn = _make_conn()
        _fire_before(conn, "INSERT INTO t VALUES (1)")

        with patch(_PATCH_RECORDER, return_value=recorder):
            _fire_after(conn, "INSERT INTO t VALUES (1)")

        results = list(recorder.query(metric_types={MetricType.DATABASE_QUERY_RESPONSE_TIME}))
        assert results[0].labels["statement_type"] == "INSERT"

    def test_recording_error_does_not_propagate(self) -> None:
        """Exceptions from the recorder are swallowed (best-effort recording)."""
        conn = _make_conn()
        _fire_before(conn)

        broken = MagicMock()
        broken.record.side_effect = RuntimeError("oops")

        with patch(_PATCH_RECORDER, return_value=broken):
            _fire_after(conn)


# =============================================================================
# Commit event
# =============================================================================


class TestOnCommit:
    """Tests for the commit event listener."""

    def test_commit_records_transaction_rate(self, recorder: MetricsRecorder) -> None:
        """Each COMMIT increments DATABASE_TRANSACTION_RATE."""
        conn = _make_conn()

        with patch(_PATCH_RECORDER, return_value=recorder):
            _on_commit(conn)
            _on_commit(conn)
            _on_commit(conn)

        results = list(recorder.query(metric_types={MetricType.DATABASE_TRANSACTION_RATE}))
        assert len(results) == 3
        assert all(r.value == 1.0 for r in results)

    def test_commit_increments_counter(self, recorder: MetricsRecorder) -> None:
        """Each COMMIT increments the db_transactions counter in the summary."""
        with patch(_PATCH_RECORDER, return_value=recorder):
            _on_commit(MagicMock())
            _on_commit(MagicMock())

        assert recorder.get_summary().db_transactions == 2

    def test_commit_error_does_not_propagate(self) -> None:
        """Exceptions in transaction recording are swallowed."""
        broken = MagicMock()
        broken.record.side_effect = RuntimeError("oops")

        with patch(_PATCH_RECORDER, return_value=broken):
            _on_commit(MagicMock())


# =============================================================================
# install_database_metrics
# =============================================================================


class TestInstallDatabaseMetrics:
    """Tests for the install_database_metrics entry point."""

    def test_registers_event_listeners(self) -> None:
        """install_database_metrics attaches all three event listeners."""
        from sqlalchemy import event

        async_engine = MagicMock()
        sync_engine = MagicMock()
        async_engine.sync_engine = sync_engine

        with (
            patch.object(event, "contains", return_value=False),
            patch.object(event, "listen") as listen_mock,
        ):
            install_database_metrics(async_engine)

        assert listen_mock.call_count == 3
        event_names = {call.args[1] for call in listen_mock.call_args_list}
        assert event_names == {"before_cursor_execute", "after_cursor_execute", "commit"}

    def test_idempotent(self) -> None:
        """Calling install twice does not duplicate listeners."""
        from sqlalchemy import event

        async_engine = MagicMock()
        sync_engine = MagicMock()
        async_engine.sync_engine = sync_engine

        with (
            patch.object(event, "contains", return_value=True),
            patch.object(event, "listen") as listen_mock,
        ):
            install_database_metrics(async_engine)

        listen_mock.assert_not_called()


# =============================================================================
# Prometheus dispatch — database metrics
# =============================================================================


class TestDatabasePrometheusDispatch:
    """Verify that database metrics update Prometheus instruments."""

    def test_query_time_updates_histogram(self, recorder: MetricsRecorder) -> None:
        """DATABASE_QUERY_RESPONSE_TIME updates the Prometheus histogram."""
        recorder.record(
            MetricType.DATABASE_QUERY_RESPONSE_TIME,
            15.0,
            unit="ms",
            labels={"statement_type": "SELECT"},
        )

        sample_sum = recorder.prometheus.database_query_response_time_seconds.labels(
            component="database",
            statement_type="SELECT",
        )._sum.get()
        assert sample_sum > 0

    def test_pool_utilization_updates_gauge(self, recorder: MetricsRecorder) -> None:
        """DATABASE_CONNECTION_POOL_UTILIZATION updates the Prometheus gauge."""
        recorder.record(
            MetricType.DATABASE_CONNECTION_POOL_UTILIZATION,
            0.35,
            labels={"checked_out": "7", "pool_size": "20", "overflow": "0", "max_overflow": "20"},
        )

        value = recorder.prometheus.database_connection_pool_utilization.labels(
            component="database",
        )._value.get()
        assert value == pytest.approx(0.35)

    def test_transaction_rate_updates_counter(self, recorder: MetricsRecorder) -> None:
        """DATABASE_TRANSACTION_RATE increments the Prometheus counter."""
        recorder.record(MetricType.DATABASE_TRANSACTION_RATE, 1.0, labels={})
        recorder.record(MetricType.DATABASE_TRANSACTION_RATE, 1.0, labels={})

        value = recorder.prometheus.database_transaction_rate_tps.labels(
            component="database",
        )._value.get()
        assert value == pytest.approx(2.0)


# =============================================================================
# Pool utilization calculation
# =============================================================================


class TestPoolUtilizationCalculation:
    """Verify pool utilization ratio is computed correctly."""

    def test_utilization_ratio(self, recorder: MetricsRecorder) -> None:
        """Utilization = checked_out / (pool_size + max_overflow)."""
        conn = _make_conn(pool_size=10, checked_out=7, overflow=2, max_overflow=5)
        _fire_before(conn)

        with patch(_PATCH_RECORDER, return_value=recorder):
            _fire_after(conn)

        results = list(recorder.query(metric_types={MetricType.DATABASE_CONNECTION_POOL_UTILIZATION}))
        assert len(results) == 1
        assert results[0].value == pytest.approx(7 / 15)  # 7 / (10 + 5)

    def test_unlimited_overflow_yields_zero_utilization(self, recorder: MetricsRecorder) -> None:
        """When max_overflow is -1 (unlimited), utilization is 0.0."""
        conn = _make_conn(pool_size=10, checked_out=5, overflow=3, max_overflow=-1)
        _fire_before(conn)

        with patch(_PATCH_RECORDER, return_value=recorder):
            _fire_after(conn)

        results = list(recorder.query(metric_types={MetricType.DATABASE_CONNECTION_POOL_UTILIZATION}))
        assert len(results) == 1
        assert results[0].value == pytest.approx(0.0)

    def test_no_pool_is_noop(self, recorder: MetricsRecorder) -> None:
        """When pool is None, no utilization metric is recorded."""
        conn = _make_conn()
        conn.engine.pool = None
        _fire_before(conn)

        with patch(_PATCH_RECORDER, return_value=recorder):
            _fire_after(conn)

        query_results = list(recorder.query(metric_types={MetricType.DATABASE_QUERY_RESPONSE_TIME}))
        pool_results = list(recorder.query(metric_types={MetricType.DATABASE_CONNECTION_POOL_UTILIZATION}))
        assert len(query_results) == 1
        assert len(pool_results) == 0

    def test_pool_without_checkedout_is_noop(self, recorder: MetricsRecorder) -> None:
        """Pools like NullPool that lack checkedout() skip utilization recording."""
        conn = _make_conn()
        del conn.engine.pool.checkedout
        _fire_before(conn)

        with patch(_PATCH_RECORDER, return_value=recorder):
            _fire_after(conn)

        pool_results = list(recorder.query(metric_types={MetricType.DATABASE_CONNECTION_POOL_UTILIZATION}))
        assert len(pool_results) == 0
