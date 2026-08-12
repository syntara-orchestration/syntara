"""Integration tests for the internal metrics store API.

These endpoints are gated behind the ``metrics.perf_test_mode`` runtime
setting.  Tests install a mock :class:`SettingsCache` so that no database
is required.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry

from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.internal_api import (
    _SETTING_KEY,
    metrics_store_component_kpis,
    metrics_store_kpis,
    metrics_store_records,
    metrics_store_reset,
    metrics_store_summary,
)
from syntara.metrics.recorder import MetricsRecorder
from syntara.metrics.types import MetricType
from syntara.settings.cache.settings_cache import SettingsCache, set_runtime_settings

_PREFIX = "/_internal/metrics"


def _make_mock_cache(*, perf_test_mode: bool = True) -> SettingsCache:
    """Build a SettingsCache mock that returns *perf_test_mode* for the key."""
    cache = AsyncMock(spec=SettingsCache)

    async def _get_bool(key: str, *, default: Any = None) -> bool:  # noqa: ANN401
        if key == _SETTING_KEY:
            return perf_test_mode
        return default if default is not None else False

    cache.get_bool = AsyncMock(side_effect=_get_bool)
    return cache


@pytest.fixture
def recorder() -> MetricsRecorder:
    """Create an isolated MetricsRecorder for each test."""
    return MetricsRecorder(
        retention_seconds=3600,
        max_records=10_000,
        prometheus_registry=CollectorRegistry(),
    )


@pytest.fixture
def client(recorder: MetricsRecorder) -> TestClient:
    """Build a TestClient with internal metrics endpoints and perf_test_mode enabled."""
    set_runtime_settings(_make_mock_cache(perf_test_mode=True))
    app = FastAPI()
    app.get(f"{_PREFIX}/summary")(metrics_store_summary)
    app.get(f"{_PREFIX}/records")(metrics_store_records)
    app.get(f"{_PREFIX}/kpis")(metrics_store_kpis)
    app.get(f"{_PREFIX}/kpis/{{component}}")(metrics_store_component_kpis)
    app.post(f"{_PREFIX}/reset")(metrics_store_reset)
    app.dependency_overrides[get_metrics_recorder] = lambda: recorder
    return TestClient(app)


# ---------------------------------------------------------------------------
# Guard behaviour — perf-test mode disabled
# ---------------------------------------------------------------------------


class TestPerfTestModeGuard:
    """Endpoints return 404 when metrics.perf_test_mode is False."""

    @pytest.fixture(autouse=True)
    def _disable_perf_test(self) -> None:
        set_runtime_settings(_make_mock_cache(perf_test_mode=False))

    @pytest.fixture
    def disabled_client(self, recorder: MetricsRecorder) -> TestClient:
        app = FastAPI()
        app.get(f"{_PREFIX}/summary")(metrics_store_summary)
        app.get(f"{_PREFIX}/records")(metrics_store_records)
        app.get(f"{_PREFIX}/kpis")(metrics_store_kpis)
        app.post(f"{_PREFIX}/reset")(metrics_store_reset)
        app.dependency_overrides[get_metrics_recorder] = lambda: recorder
        return TestClient(app)

    def test_summary_returns_404(self, disabled_client: TestClient) -> None:
        resp = disabled_client.get(f"{_PREFIX}/summary")
        assert resp.status_code == 404

    def test_records_returns_404(self, disabled_client: TestClient) -> None:
        resp = disabled_client.get(f"{_PREFIX}/records")
        assert resp.status_code == 404

    def test_kpis_returns_404(self, disabled_client: TestClient) -> None:
        resp = disabled_client.get(f"{_PREFIX}/kpis")
        assert resp.status_code == 404

    def test_reset_returns_404(self, disabled_client: TestClient) -> None:
        resp = disabled_client.post(f"{_PREFIX}/reset")
        assert resp.status_code == 404

    def test_disabling_flushes_store(self, recorder: MetricsRecorder) -> None:
        """When perf_test_mode flips from True to False the store is cleared."""
        set_runtime_settings(_make_mock_cache(perf_test_mode=True))
        recorder.store_enabled = True
        recorder.record(MetricType.REQUEST_DURATION, 42.0, unit="ms")
        recorder.increment("requests", 1)
        assert recorder.store.count() == 1

        set_runtime_settings(_make_mock_cache(perf_test_mode=False))
        app = FastAPI()
        app.get(f"{_PREFIX}/summary")(metrics_store_summary)
        app.dependency_overrides[get_metrics_recorder] = lambda: recorder
        client = TestClient(app)

        resp = client.get(f"{_PREFIX}/summary")
        assert resp.status_code == 404
        assert recorder.store.count() == 0
        assert recorder.store_enabled is False


# ---------------------------------------------------------------------------
# Summary endpoint
# ---------------------------------------------------------------------------


class TestMetricsStoreSummary:
    """Tests for GET /_internal/metrics/summary."""

    def test_empty_store(self, client: TestClient) -> None:
        resp = client.get(f"{_PREFIX}/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_records"] == 0
        assert data["metric_type_counts"] == {}

    def test_with_records(self, client: TestClient, recorder: MetricsRecorder) -> None:
        recorder.record(MetricType.REQUEST_DURATION, 42.0, unit="ms", labels={"endpoint": "/api/v1/workflows"})
        recorder.record(MetricType.LLM_DURATION, 100.0, unit="ms", labels={"model": "gpt-4"})
        recorder.record(MetricType.CACHE_HIT, 1.0)

        resp = client.get(f"{_PREFIX}/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_records"] == 3
        assert "request_duration_ms" in data["metric_type_counts"]
        assert "llm_duration_ms" in data["metric_type_counts"]
        assert data["oldest_record_at"] is not None
        assert data["newest_record_at"] is not None


# ---------------------------------------------------------------------------
# Records endpoint
# ---------------------------------------------------------------------------


class TestMetricsStoreRecords:
    """Tests for GET /_internal/metrics/records."""

    def test_empty_store(self, client: TestClient) -> None:
        resp = client.get(f"{_PREFIX}/records")
        assert resp.status_code == 200
        data = resp.json()
        assert data["records"] == []
        assert data["total"] == 0

    def test_filter_by_metric_type(self, client: TestClient, recorder: MetricsRecorder) -> None:
        recorder.record(MetricType.REQUEST_DURATION, 42.0, unit="ms")
        recorder.record(MetricType.LLM_DURATION, 100.0, unit="ms", labels={"model": "gpt-4"})

        resp = client.get(f"{_PREFIX}/records", params={"metric_type": "request_duration_ms"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["records"][0]["metric_type"] == "request_duration_ms"

    def test_filter_by_category(self, client: TestClient, recorder: MetricsRecorder) -> None:
        recorder.record(MetricType.LLM_DURATION, 100.0, unit="ms", labels={"model": "gpt-4"})
        recorder.record(MetricType.CACHE_HIT, 1.0)

        resp = client.get(f"{_PREFIX}/records", params={"category": "llm"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_invalid_metric_type(self, client: TestClient) -> None:
        resp = client.get(f"{_PREFIX}/records", params={"metric_type": "nonexistent"})
        assert resp.status_code == 400

    def test_invalid_labels_nested_object(self, client: TestClient) -> None:
        resp = client.get(f"{_PREFIX}/records", params={"labels": '{"a": {"nested": true}}'})
        assert resp.status_code == 400
        assert "flat JSON object" in resp.json()["detail"]

    def test_invalid_labels_array(self, client: TestClient) -> None:
        resp = client.get(f"{_PREFIX}/records", params={"labels": '["a","b"]'})
        assert resp.status_code == 400

    def test_pagination(self, client: TestClient, recorder: MetricsRecorder) -> None:
        for _ in range(5):
            recorder.record(MetricType.REQUEST_DURATION, 10.0, unit="ms")

        resp = client.get(f"{_PREFIX}/records", params={"limit": 2, "offset": 0})
        data = resp.json()
        assert data["total"] == 5
        assert len(data["records"]) == 2
        assert data["limit"] == 2
        assert data["offset"] == 0

    def test_filter_by_labels(self, client: TestClient, recorder: MetricsRecorder) -> None:
        recorder.record(MetricType.REQUEST_DURATION, 10.0, unit="ms", labels={"endpoint": "/api/v1/workflows"})
        recorder.record(MetricType.REQUEST_DURATION, 20.0, unit="ms", labels={"endpoint": "/api/v1/invocations"})

        resp = client.get(
            f"{_PREFIX}/records",
            params={"labels": '{"endpoint": "/api/v1/workflows"}'},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["records"][0]["labels"]["endpoint"] == "/api/v1/workflows"


# ---------------------------------------------------------------------------
# KPI dashboard endpoint
# ---------------------------------------------------------------------------


class TestMetricsStoreKPIs:
    """Tests for GET /_internal/metrics/kpis."""

    def test_empty_dashboard(self, client: TestClient) -> None:
        resp = client.get(f"{_PREFIX}/kpis")
        assert resp.status_code == 200
        data = resp.json()
        assert "generated_at" in data
        assert len(data["components"]) > 0
        component_names = {c["component"] for c in data["components"]}
        assert "api_service" in component_names
        assert "workflow_engine" in component_names
        assert "llm" in component_names
        assert "cache" in component_names
        assert "system_wide" in component_names

    def test_with_api_metrics(self, client: TestClient, recorder: MetricsRecorder) -> None:
        recorder.record(MetricType.REQUEST_DURATION, 50.0, unit="ms")
        recorder.record(MetricType.REQUEST_DURATION, 100.0, unit="ms")
        recorder.record(MetricType.REQUEST_DURATION, 200.0, unit="ms")
        recorder.increment("requests", 3)

        resp = client.get(f"{_PREFIX}/kpis")
        data = resp.json()
        api = next(c for c in data["components"] if c["component"] == "api_service")
        stats = api["metrics"]["response_time_ms"]
        assert stats["count"] == 3
        assert stats["min"] == 50.0
        assert stats["max"] == 200.0

    def test_with_llm_metrics(self, client: TestClient, recorder: MetricsRecorder) -> None:
        recorder.record(MetricType.LLM_DURATION, 250.0, unit="ms", labels={"model": "gpt-4"})
        recorder.record(MetricType.LLM_TTFT, 30.0, unit="ms", labels={"model": "gpt-4"})
        recorder.record(MetricType.LLM_TOKENS_INPUT, 100.0, labels={"model": "gpt-4"})

        resp = client.get(f"{_PREFIX}/kpis")
        data = resp.json()
        llm = next(c for c in data["components"] if c["component"] == "llm")
        assert llm["metrics"]["response_time_ms"]["count"] == 1
        assert llm["metrics"]["ttft_ms"]["count"] == 1

    def test_with_cache_metrics(self, client: TestClient, recorder: MetricsRecorder) -> None:
        recorder.record(MetricType.CACHE_HIT, 1.0)
        recorder.record(MetricType.CACHE_HIT, 1.0)
        recorder.record(MetricType.CACHE_MISS, 1.0)
        recorder.increment("cache_hits", 2)
        recorder.increment("cache_misses", 1)

        resp = client.get(f"{_PREFIX}/kpis")
        data = resp.json()
        cache = next(c for c in data["components"] if c["component"] == "cache")
        assert cache["metrics"]["total_hits"] == 2
        assert cache["metrics"]["total_misses"] == 1
        hit_rate = cache["metrics"]["hit_rate"]
        assert abs(hit_rate - 2 / 3) < 0.01


# ---------------------------------------------------------------------------
# Component KPI endpoint
# ---------------------------------------------------------------------------


class TestRateFromStatusDedup:
    """Tests for _rate_from_status dedup_key behaviour.

    WORKFLOW_STATUS emits two records per execution (started + terminal),
    so _rate_from_status must deduplicate by execution_id to avoid
    inflating the denominator.
    """

    def test_completion_rate_without_dedup_is_diluted(
        self,
        client: TestClient,
        recorder: MetricsRecorder,
    ) -> None:
        """Without dedup, started+completed records halve the rate."""
        for i in range(10):
            recorder.record(
                MetricType.WORKFLOW_STATUS,
                1,
                labels={"execution_id": str(i), "status": "started", "workflow_id": "w1", "workflow_type": "test"},
            )
            recorder.record(
                MetricType.WORKFLOW_STATUS,
                1,
                labels={"execution_id": str(i), "status": "completed", "workflow_id": "w1", "workflow_type": "test"},
            )

        resp = client.get(f"{_PREFIX}/kpis/execution_service")
        data = resp.json()
        completion_rate = data["metrics"]["completion_rate"]
        assert completion_rate > 0.9, f"With dedup_key, completion_rate should be ~1.0, got {completion_rate}"

    def test_completion_rate_reflects_actual_outcomes(
        self,
        client: TestClient,
        recorder: MetricsRecorder,
    ) -> None:
        """9/10 completed → rate should be 0.9, not 9/19 ≈ 0.47."""
        for i in range(10):
            recorder.record(
                MetricType.WORKFLOW_STATUS,
                1,
                labels={"execution_id": str(i), "status": "started", "workflow_id": "w1", "workflow_type": "test"},
            )
        for i in range(9):
            recorder.record(
                MetricType.WORKFLOW_STATUS,
                1,
                labels={"execution_id": str(i), "status": "completed", "workflow_id": "w1", "workflow_type": "test"},
            )

        resp = client.get(f"{_PREFIX}/kpis/execution_service")
        data = resp.json()
        completion_rate = data["metrics"]["completion_rate"]
        assert abs(completion_rate - 0.9) < 0.01, f"Expected completion_rate ≈ 0.9 (9/10), got {completion_rate}"

    def test_creation_success_rate_with_dedup(
        self,
        client: TestClient,
        recorder: MetricsRecorder,
    ) -> None:
        """Workflow engine creation_success_rate also deduplicates correctly."""
        for i in range(5):
            recorder.record(
                MetricType.WORKFLOW_STATUS,
                1,
                labels={"execution_id": str(i), "status": "started", "workflow_id": "w1", "workflow_type": "test"},
            )
            recorder.record(
                MetricType.WORKFLOW_STATUS,
                1,
                labels={"execution_id": str(i), "status": "completed", "workflow_id": "w1", "workflow_type": "test"},
            )

        resp = client.get(f"{_PREFIX}/kpis/workflow_engine")
        data = resp.json()
        rate = data["metrics"]["creation_success_rate"]
        assert rate > 0.9, f"Expected creation_success_rate ~1.0, got {rate}"


class TestMetricsStoreComponentKPIs:
    """Tests for GET /_internal/metrics/kpis/{component}."""

    def test_valid_component(self, client: TestClient) -> None:
        resp = client.get(f"{_PREFIX}/kpis/api_service")
        assert resp.status_code == 200
        assert resp.json()["component"] == "api_service"

    def test_unknown_component(self, client: TestClient) -> None:
        resp = client.get(f"{_PREFIX}/kpis/nonexistent_service")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Reset endpoint
# ---------------------------------------------------------------------------


class TestMetricsStoreReset:
    """Tests for POST /_internal/metrics/reset."""

    def test_reset_clears_store(self, client: TestClient, recorder: MetricsRecorder) -> None:
        recorder.record(MetricType.REQUEST_DURATION, 42.0, unit="ms")
        recorder.record(MetricType.LLM_DURATION, 100.0, unit="ms", labels={"model": "gpt-4"})
        recorder.increment("requests", 2)
        assert recorder.store.count() == 2

        resp = client.post(f"{_PREFIX}/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cleared_records"] == 2
        assert data["status"] == "ok"
        assert recorder.store.count() == 0
