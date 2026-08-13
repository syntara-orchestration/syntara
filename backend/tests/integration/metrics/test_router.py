"""Integration tests for the OpenMetrics (Prometheus) scrape endpoint.

Uses a lightweight FastAPI TestClient with an isolated MetricsRecorder so
these tests do not require a running database or external services.

The JSON query/summary/component endpoints were removed from the product
API surface -- Prometheus + Grafana is the production observability path.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry

from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.openmetrics import openmetrics_endpoint
from syntara.metrics.recorder import MetricsRecorder
from syntara.metrics.types import MetricType


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
    """Build a TestClient with the OpenMetrics endpoint at /metrics."""
    app = FastAPI()
    app.get("/metrics")(openmetrics_endpoint)
    app.dependency_overrides[get_metrics_recorder] = lambda: recorder
    return TestClient(app)


# =============================================================================
# GET /metrics (OpenMetrics / Prometheus scrape endpoint)
# =============================================================================


class TestOpenMetricsEndpoint:
    """Tests for the OpenMetrics scrape endpoint."""

    def test_returns_text_plain(self, client: TestClient) -> None:
        """OpenMetrics endpoint returns text/plain content type."""
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]

    def test_contains_metric_names(self, client: TestClient, recorder: MetricsRecorder) -> None:
        """OpenMetrics output includes expected metric families."""
        recorder.record(MetricType.LLM_DURATION, 100.0, labels={"model": "gpt-4"})
        recorder.record(MetricType.CACHE_HIT, 1.0)

        resp = client.get("/metrics")
        content = resp.text
        assert "orchestrator_llm_duration_seconds" in content
        assert "orchestrator_cache_hits_total" in content

    def test_returns_valid_prometheus_openmetrics_format(self, client: TestClient, recorder: MetricsRecorder) -> None:
        """OpenMetrics endpoint returns valid Prometheus/OpenMetrics exposition format."""
        recorder.record(MetricType.LLM_DURATION, 100.0, labels={"model": "gpt-4"})
        recorder.record(MetricType.CACHE_HIT, 1.0)

        resp = client.get("/metrics")
        assert resp.status_code == 200
        content = resp.text

        assert "# HELP" in content
        assert "# TYPE" in content
        assert "orchestrator_llm_duration_seconds" in content
        assert "orchestrator_cache_hits_total" in content
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        for line in lines:
            if not line.startswith("#"):
                assert " " in line or "{" in line, f"Metric line should contain space or labels: {line!r}"

    def test_tool_metrics_appear_in_openmetrics(self, client: TestClient, recorder: MetricsRecorder) -> None:
        """OpenMetrics output includes tool counter and histogram after recording."""
        recorder.record(
            MetricType.TOOL_EXECUTION_DURATION,
            value=1500.0,
            unit="ms",
            labels={
                "namespaced_name": "github::search_code",
                "status": "success",
            },
        )
        resp = client.get("/metrics")
        content = resp.text
        assert "orchestrator_tool_executions_total" in content
        assert "orchestrator_tool_execution_duration_seconds" in content
        assert 'namespaced_name="github::search_code"' in content
        assert 'status="success"' in content

    def test_tool_error_status_in_openmetrics(self, client: TestClient, recorder: MetricsRecorder) -> None:
        """OpenMetrics output reflects error and timeout status labels."""
        recorder.record(
            MetricType.TOOL_EXECUTION_STATUS,
            value=1.0,
            labels={
                "namespaced_name": "github::search_code",
                "status": "error",
                "error_code": "RuntimeError",
            },
        )
        recorder.record(
            MetricType.TOOL_EXECUTION_STATUS,
            value=1.0,
            labels={
                "namespaced_name": "github::search_code",
                "status": "timeout",
                "error_code": "TimeoutError",
            },
        )
        resp = client.get("/metrics")
        content = resp.text
        assert 'status="error"' in content
        assert 'status="timeout"' in content

    def test_counter_values_appear(self, client: TestClient, recorder: MetricsRecorder) -> None:
        """OpenMetrics output reflects recorded counter values."""
        recorder.record(MetricType.CACHE_HIT, 1.0)
        recorder.record(MetricType.CACHE_HIT, 1.0)
        recorder.record(MetricType.CACHE_HIT, 1.0)

        resp = client.get("/metrics")
        content = resp.text
        assert "orchestrator_cache_hits_total 3.0" in content
