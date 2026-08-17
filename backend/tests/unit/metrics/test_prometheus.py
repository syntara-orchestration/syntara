"""Unit tests for Prometheus metric definitions."""

import pytest
from prometheus_client import CollectorRegistry, generate_latest

from syntara.metrics.prometheus import (
    LATENCY_BUCKETS_FAST,
    LATENCY_BUCKETS_MEDIUM,
    LATENCY_BUCKETS_SLOW,
    OrchestratorPrometheusMetrics,
)


@pytest.fixture
def prom() -> OrchestratorPrometheusMetrics:
    """Fresh OrchestratorPrometheusMetrics with an isolated registry."""
    return OrchestratorPrometheusMetrics(registry=CollectorRegistry())


# =============================================================================
# Metric existence
# =============================================================================


class TestMetricDefinitions:
    """Verify all expected metrics are defined."""

    def test_counters_defined(self, prom: OrchestratorPrometheusMetrics) -> None:
        """All required counters are present."""
        assert prom.requests_total is not None
        assert prom.errors_total is not None
        assert prom.auth_failures_total is not None
        assert prom.cache_hits_total is not None
        assert prom.cache_misses_total is not None
        assert prom.llm_calls_total is not None
        assert prom.workflows_total is not None
        assert prom.tool_executions_total is not None
        assert prom.cache_pool_retry_total is not None

    def test_histograms_defined(self, prom: OrchestratorPrometheusMetrics) -> None:
        """All required histograms are present."""
        assert prom.request_duration_seconds is not None
        assert prom.llm_duration_seconds is not None
        assert prom.ttft_seconds is not None
        assert prom.cache_lookup_duration_seconds is not None
        assert prom.workflow_duration_seconds is not None
        assert prom.api_response_time_seconds is not None
        assert prom.workflow_serialization_duration_seconds is not None
        assert prom.workflow_validation_duration_seconds is not None
        assert prom.workflow_start_latency_seconds is not None
        assert prom.tool_execution_duration_seconds is not None
        assert prom.database_query_response_time_seconds is not None
        assert prom.system_e2e_latency_seconds is not None
        assert prom.authz_duration_seconds is not None
        assert prom.opa_request_duration_seconds is not None
        assert prom.cache_pool_retry_backoff_duration_seconds is not None

    def test_gauges_defined(self, prom: OrchestratorPrometheusMetrics) -> None:
        """All required gauges are present."""
        assert prom.cache_utilization_ratio is not None
        assert prom.active_workflows is not None
        assert prom.active_llm_requests is not None
        assert prom.api_error_rate is not None
        assert prom.api_throughput_rps is not None
        assert prom.workflow_creation_success_rate is not None
        assert prom.workflow_completion_rate is not None
        assert prom.temporal_queue_depth is not None
        assert prom.activity_execution_success_rate is not None

        assert prom.database_connection_pool_utilization is not None
        assert prom.database_transaction_rate_tps is not None
        assert prom.system_uptime is not None
        assert prom.system_error_rate is not None


# =============================================================================
# Metric operations
# =============================================================================


class TestMetricOperations:
    """Verify metrics can be mutated."""

    def test_counter_increment(self, prom: OrchestratorPrometheusMetrics) -> None:
        """Counters can be incremented."""
        prom.requests_total.labels(status="success", endpoint="/api", interface="api").inc()
        prom.requests_total.labels(status="success", endpoint="/api", interface="api").inc()
        value = prom.requests_total.labels(status="success", endpoint="/api", interface="api")._value.get()
        assert value == pytest.approx(2.0)

    def test_histogram_observe(self, prom: OrchestratorPrometheusMetrics) -> None:
        """Histograms accept observed values."""
        prom.llm_duration_seconds.labels(model="gpt-4").observe(0.5)
        prom.llm_duration_seconds.labels(model="gpt-4").observe(1.0)
        total = prom.llm_duration_seconds.labels(model="gpt-4")._sum.get()
        assert total == pytest.approx(1.5)

    def test_gauge_set(self, prom: OrchestratorPrometheusMetrics) -> None:
        """Gauges can be set to a value."""
        prom.active_workflows.set(5)
        assert prom.active_workflows._value.get() == pytest.approx(5.0)

    def test_gauge_inc_dec(self, prom: OrchestratorPrometheusMetrics) -> None:
        """Gauges can be incremented and decremented."""
        prom.active_workflows.inc()
        prom.active_workflows.inc()
        prom.active_workflows.dec()
        assert prom.active_workflows._value.get() == pytest.approx(1.0)


# =============================================================================
# Output format
# =============================================================================


class TestPrometheusOutput:
    """Verify Prometheus text format generation."""

    def test_generate_metrics_output(self, prom: OrchestratorPrometheusMetrics) -> None:
        """generate_latest produces valid Prometheus text format."""
        prom.requests_total.labels(status="success", endpoint="/api", interface="api").inc(10)
        prom.cache_hits_total.inc(5)
        prom.active_workflows.set(3)

        output = generate_latest(prom.registry).decode("utf-8")

        assert "orchestrator_requests_total" in output
        assert "orchestrator_cache_hits_total" in output
        assert "orchestrator_active_workflows" in output
        assert "# HELP" in output
        assert "# TYPE" in output

    def test_isolated_registry(self) -> None:
        """Each OrchestratorPrometheusMetrics instance uses its own registry."""
        prom1 = OrchestratorPrometheusMetrics(registry=CollectorRegistry())
        prom2 = OrchestratorPrometheusMetrics(registry=CollectorRegistry())

        prom1.cache_hits_total.inc(100)
        assert prom2.cache_hits_total._value.get() == pytest.approx(0.0)


# =============================================================================
# Bucket constants
# =============================================================================


class TestBucketConstants:
    """Verify histogram bucket boundaries are sensible."""

    def test_fast_buckets_sorted(self) -> None:
        """Fast buckets are in ascending order."""
        assert list(LATENCY_BUCKETS_FAST) == sorted(LATENCY_BUCKETS_FAST)

    def test_medium_buckets_sorted(self) -> None:
        """Medium buckets are in ascending order."""
        assert list(LATENCY_BUCKETS_MEDIUM) == sorted(LATENCY_BUCKETS_MEDIUM)

    def test_slow_buckets_sorted(self) -> None:
        """Slow buckets are in ascending order."""
        assert list(LATENCY_BUCKETS_SLOW) == sorted(LATENCY_BUCKETS_SLOW)


# =============================================================================
# Tool instrument label tests
# =============================================================================


class TestToolInstruments:
    """Verify tool counter and histogram have correct label sets."""

    def test_tool_executions_total_labels(self, prom: OrchestratorPrometheusMetrics) -> None:
        """tool_executions_total counter has [namespaced_name, status, error_code] labels."""
        prom.tool_executions_total.labels(
            namespaced_name="github::search_code",
            status="success",
            error_code="none",
        ).inc()
        value = prom.tool_executions_total.labels(
            namespaced_name="github::search_code",
            status="success",
            error_code="none",
        )._value.get()
        assert value == pytest.approx(1.0)

    def test_tool_execution_duration_seconds_labels(self, prom: OrchestratorPrometheusMetrics) -> None:
        """tool_execution_duration_seconds histogram has [namespaced_name] labels."""
        prom.tool_execution_duration_seconds.labels(
            namespaced_name="github::search_code",
        ).observe(1.5)
        total = prom.tool_execution_duration_seconds.labels(
            namespaced_name="github::search_code",
        )._sum.get()
        assert total == pytest.approx(1.5)

    def test_tool_counter_increments_correctly(self, prom: OrchestratorPrometheusMetrics) -> None:
        """Counter increments are tracked per label combination."""
        prom.tool_executions_total.labels(
            namespaced_name="github::search_code",
            status="success",
            error_code="none",
        ).inc()
        prom.tool_executions_total.labels(
            namespaced_name="github::search_code",
            status="error",
            error_code="TimeoutError",
        ).inc()
        success = prom.tool_executions_total.labels(
            namespaced_name="github::search_code",
            status="success",
            error_code="none",
        )._value.get()
        error = prom.tool_executions_total.labels(
            namespaced_name="github::search_code",
            status="error",
            error_code="TimeoutError",
        )._value.get()
        assert success == pytest.approx(1.0)
        assert error == pytest.approx(1.0)


# =============================================================================
# Interface label in Prometheus output (AAP-77419)
# =============================================================================


class TestInterfaceLabelInPrometheusOutput:
    """Verify the interface label appears in scraped Prometheus output."""

    def test_request_duration_includes_interface(self, prom: OrchestratorPrometheusMetrics) -> None:
        """orchestrator_request_duration_seconds samples include interface label."""
        prom.request_duration_seconds.labels(endpoint="/api/v1/test", method="GET", interface="ui").observe(0.1)

        output = generate_latest(prom.registry).decode("utf-8")

        assert 'interface="ui"' in output
        assert "orchestrator_request_duration_seconds" in output

    def test_requests_total_includes_interface(self, prom: OrchestratorPrometheusMetrics) -> None:
        """orchestrator_requests_total samples include interface label."""
        prom.requests_total.labels(status="200", endpoint="/api/v1/test", interface="ui").inc()

        output = generate_latest(prom.registry).decode("utf-8")

        assert 'orchestrator_requests_total{endpoint="/api/v1/test",interface="ui",status="200"}' in output

    def test_errors_total_includes_interface(self, prom: OrchestratorPrometheusMetrics) -> None:
        """orchestrator_errors_total samples include interface label."""
        prom.errors_total.labels(error_type="internal", interface="ui").inc()

        output = generate_latest(prom.registry).decode("utf-8")

        assert 'orchestrator_errors_total{error_type="internal",interface="ui"}' in output

    def test_interface_defaults_to_api(self, prom: OrchestratorPrometheusMetrics) -> None:
        """Metrics with interface=api appear correctly in output."""
        prom.requests_total.labels(status="200", endpoint="/health", interface="api").inc()

        output = generate_latest(prom.registry).decode("utf-8")

        assert 'interface="api"' in output


# =============================================================================
# Auth failure counter
# =============================================================================


class TestAuthFailuresInstrument:
    """Verify auth_failures_total counter has correct label sets."""

    def test_auth_failures_labels(self, prom: OrchestratorPrometheusMetrics) -> None:
        """auth_failures_total counter has [failure_type, interface] labels."""
        prom.auth_failures_total.labels(failure_type="expired_token", interface="ui").inc()
        value = prom.auth_failures_total.labels(failure_type="expired_token", interface="ui")._value.get()
        assert value == pytest.approx(1.0)

    def test_auth_failures_per_interface(self, prom: OrchestratorPrometheusMetrics) -> None:
        """Auth failure counts are tracked independently per interface."""
        prom.auth_failures_total.labels(failure_type="invalid_token", interface="api").inc(3)
        prom.auth_failures_total.labels(failure_type="invalid_token", interface="ui").inc(1)
        api_val = prom.auth_failures_total.labels(failure_type="invalid_token", interface="api")._value.get()
        ui_val = prom.auth_failures_total.labels(failure_type="invalid_token", interface="ui")._value.get()
        assert api_val == pytest.approx(3.0)
        assert ui_val == pytest.approx(1.0)
