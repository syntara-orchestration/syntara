"""Unit tests for APIUsageAccumulator."""

import threading

from syntara.telemetry.api_usage_accumulator import APIUsageAccumulator


class TestAccumulatorRecord:
    """Tests for the record() method."""

    def test_record_adds_to_caller_ids(self):
        acc = APIUsageAccumulator()
        acc.record("hash-1", "user", "/api/v1/workflows", "GET", "api")

        snapshot = acc.drain()
        assert "hash-1" in snapshot.caller_ids
        assert snapshot.callers_by_type == {"user": 1}
        assert snapshot.callers_by_interface == {"api": 1}

    def test_record_deduplicates_same_caller(self):
        acc = APIUsageAccumulator()
        acc.record("hash-1", "user", "/api/v1/workflows", "GET", "api")
        acc.record("hash-1", "user", "/api/v1/executions", "POST", "api")

        snapshot = acc.drain()
        assert len(snapshot.caller_ids) == 1
        assert snapshot.callers_by_type == {"user": 1}

    def test_record_counts_distinct_callers(self):
        acc = APIUsageAccumulator()
        acc.record("hash-1", "user", "/api/v1/workflows", "GET", "api")
        acc.record("hash-2", "service_account", "/api/v1/workflows", "GET", "api")
        acc.record("hash-3", "user", "/api/v1/executions", "POST", "ui")

        snapshot = acc.drain()
        assert len(snapshot.caller_ids) == 3
        assert snapshot.callers_by_type == {"user": 2, "service_account": 1}
        assert snapshot.callers_by_interface == {"api": 2, "ui": 1}

    def test_record_accumulates_feature_usage(self):
        acc = APIUsageAccumulator()
        acc.record("hash-1", "user", "/api/v1/workflows", "GET", "api")
        acc.record("hash-2", "user", "/api/v1/workflows", "GET", "api")
        acc.record("hash-1", "user", "/api/v1/workflows", "POST", "api")

        snapshot = acc.drain()
        assert snapshot.feature_usage[("/api/v1/workflows", "GET", "api")] == 2
        assert snapshot.feature_usage[("/api/v1/workflows", "POST", "api")] == 1

    def test_record_separates_by_interface(self):
        acc = APIUsageAccumulator()
        acc.record("hash-1", "user", "/api/v1/workflows", "GET", "api")
        acc.record("hash-1", "user", "/api/v1/workflows", "GET", "ui")

        snapshot = acc.drain()
        assert snapshot.feature_usage[("/api/v1/workflows", "GET", "api")] == 1
        assert snapshot.feature_usage[("/api/v1/workflows", "GET", "ui")] == 1
        assert snapshot.callers_by_interface == {"api": 1, "ui": 1}


class TestAccumulatorDrain:
    """Tests for the drain() method."""

    def test_drain_returns_correct_snapshot(self):
        acc = APIUsageAccumulator()
        acc.record("hash-1", "user", "/api/v1/workflows", "GET", "api")
        acc.record("hash-2", "service_account", "/api/v1/executions", "POST", "api")

        snapshot = acc.drain()

        assert len(snapshot.caller_ids) == 2
        assert snapshot.callers_by_type == {"user": 1, "service_account": 1}
        assert snapshot.callers_by_interface == {"api": 2}
        assert snapshot.feature_usage[("/api/v1/workflows", "GET", "api")] == 1
        assert snapshot.feature_usage[("/api/v1/executions", "POST", "api")] == 1

    def test_drain_resets_state(self):
        acc = APIUsageAccumulator()
        acc.record("hash-1", "user", "/api/v1/workflows", "GET", "api")

        first = acc.drain()
        assert len(first.caller_ids) == 1

        second = acc.drain()
        assert len(second.caller_ids) == 0
        assert second.callers_by_type == {}
        assert second.callers_by_interface == {}
        assert second.feature_usage == {}

    def test_empty_drain(self):
        acc = APIUsageAccumulator()
        snapshot = acc.drain()

        assert len(snapshot.caller_ids) == 0
        assert snapshot.callers_by_type == {}
        assert snapshot.callers_by_interface == {}
        assert snapshot.feature_usage == {}

    def test_snapshot_is_immutable(self):
        acc = APIUsageAccumulator()
        acc.record("hash-1", "user", "/api/v1/workflows", "GET", "api")
        snapshot = acc.drain()

        acc.record("hash-2", "user", "/api/v1/executions", "POST", "api")

        assert "hash-2" not in snapshot.caller_ids
        assert len(snapshot.caller_ids) == 1


class TestAccumulatorThreadSafety:
    """Tests for concurrent access to the accumulator."""

    def test_concurrent_records_no_data_loss(self):
        acc = APIUsageAccumulator()
        num_threads = 10
        records_per_thread = 100

        def worker(thread_id: int) -> None:
            for i in range(records_per_thread):
                acc.record(
                    f"hash-{thread_id}-{i}",
                    "user",
                    "/api/v1/workflows",
                    "GET",
                    "api",
                )

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        snapshot = acc.drain()
        assert len(snapshot.caller_ids) == num_threads * records_per_thread
        assert snapshot.feature_usage[("/api/v1/workflows", "GET", "api")] == num_threads * records_per_thread
