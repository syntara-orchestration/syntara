"""Unit tests for authorization latency metrics.

Tests cover:
- AUTHZ_DURATION metric type and Prometheus histogram
- OPA_REQUEST_DURATION metric type and Prometheus histogram
- Method label on request_duration_seconds histogram
- Recorder dispatch for authz metrics
- Fire-and-forget safety of instrumentation helpers
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from prometheus_client import CollectorRegistry, generate_latest

from syntara.metrics.prometheus import OrchestratorPrometheusMetrics
from syntara.metrics.recorder import MetricsRecorder
from syntara.metrics.types import MetricType


@pytest.fixture
def recorder() -> MetricsRecorder:
    """Fresh MetricsRecorder with an isolated Prometheus registry."""
    return MetricsRecorder(
        retention_seconds=3600,
        max_records=10_000,
        prometheus_registry=CollectorRegistry(),
    )


@pytest.fixture
def prom() -> OrchestratorPrometheusMetrics:
    """Fresh OrchestratorPrometheusMetrics with an isolated registry."""
    return OrchestratorPrometheusMetrics(registry=CollectorRegistry())


# =============================================================================
# Prometheus histogram definitions
# =============================================================================


class TestAuthzHistogramDefinitions:
    """Verify authz histograms are defined with correct labels."""

    def test_authz_duration_seconds_defined(self, prom: OrchestratorPrometheusMetrics) -> None:
        """orchestrator_authz_duration_seconds histogram exists."""
        assert prom.authz_duration_seconds is not None

    def test_opa_request_duration_seconds_defined(self, prom: OrchestratorPrometheusMetrics) -> None:
        """orchestrator_opa_request_duration_seconds histogram exists."""
        assert prom.opa_request_duration_seconds is not None

    def test_authz_duration_labels(self, prom: OrchestratorPrometheusMetrics) -> None:
        """authz_duration_seconds accepts resource_type and action labels."""
        prom.authz_duration_seconds.labels(resource_type="workflow", action="create").observe(0.05)
        total = prom.authz_duration_seconds.labels(resource_type="workflow", action="create")._sum.get()
        assert total == pytest.approx(0.05)

    def test_opa_request_duration_labels(self, prom: OrchestratorPrometheusMetrics) -> None:
        """opa_request_duration_seconds accepts resource_type and action labels."""
        prom.opa_request_duration_seconds.labels(resource_type="credential", action="read").observe(0.01)
        total = prom.opa_request_duration_seconds.labels(resource_type="credential", action="read")._sum.get()
        assert total == pytest.approx(0.01)

    def test_authz_histograms_in_prometheus_output(self, prom: OrchestratorPrometheusMetrics) -> None:
        """Authz histograms appear in Prometheus text format output."""
        prom.authz_duration_seconds.labels(resource_type="project", action="read").observe(0.1)
        prom.opa_request_duration_seconds.labels(resource_type="project", action="read").observe(0.02)

        output = generate_latest(prom.registry).decode("utf-8")
        assert "orchestrator_authz_duration_seconds" in output
        assert "orchestrator_opa_request_duration_seconds" in output
        assert 'resource_type="project"' in output
        assert 'action="read"' in output


# =============================================================================
# Recorder dispatch
# =============================================================================


class TestAuthzRecorderDispatch:
    """Verify MetricsRecorder dispatches authz metrics to Prometheus."""

    def test_authz_duration_dispatched(self, recorder: MetricsRecorder) -> None:
        """AUTHZ_DURATION recording updates the Prometheus histogram."""
        recorder.record(
            MetricType.AUTHZ_DURATION,
            50.0,
            unit="ms",
            labels={"resource_type": "workflow", "action": "create"},
        )
        sample_sum = recorder.prometheus.authz_duration_seconds.labels(
            resource_type="workflow", action="create"
        )._sum.get()
        assert sample_sum == pytest.approx(0.05, rel=0.01)

    def test_opa_request_duration_dispatched(self, recorder: MetricsRecorder) -> None:
        """OPA_REQUEST_DURATION recording updates the Prometheus histogram."""
        recorder.record(
            MetricType.OPA_REQUEST_DURATION,
            10.0,
            unit="ms",
            labels={"resource_type": "credential", "action": "read"},
        )
        sample_sum = recorder.prometheus.opa_request_duration_seconds.labels(
            resource_type="credential", action="read"
        )._sum.get()
        assert sample_sum == pytest.approx(0.01, rel=0.01)

    def test_authz_duration_stored_in_memory(self, recorder: MetricsRecorder) -> None:
        """AUTHZ_DURATION metric is stored in the in-memory metrics store."""
        recorder.record(
            MetricType.AUTHZ_DURATION,
            25.0,
            unit="ms",
            labels={"resource_type": "project", "action": "update"},
        )
        results = list(recorder.query(metric_types={MetricType.AUTHZ_DURATION}))
        assert len(results) == 1
        assert results[0].value == 25.0
        assert results[0].labels["resource_type"] == "project"
        assert results[0].labels["action"] == "update"

    def test_opa_request_duration_stored_in_memory(self, recorder: MetricsRecorder) -> None:
        """OPA_REQUEST_DURATION metric is stored in the in-memory metrics store."""
        recorder.record(
            MetricType.OPA_REQUEST_DURATION,
            8.0,
            unit="ms",
            labels={"resource_type": "workflow", "action": "read"},
        )
        results = list(recorder.query(metric_types={MetricType.OPA_REQUEST_DURATION}))
        assert len(results) == 1
        assert results[0].value == 8.0

    def test_default_labels_when_missing(self, recorder: MetricsRecorder) -> None:
        """Missing resource_type/action labels default to 'unknown'."""
        recorder.record(MetricType.AUTHZ_DURATION, 10.0, unit="ms", labels={})
        sample_sum = recorder.prometheus.authz_duration_seconds.labels(
            resource_type="unknown", action="unknown"
        )._sum.get()
        assert sample_sum == pytest.approx(0.01, rel=0.01)


# =============================================================================
# Request duration method label (AC1)
# =============================================================================


class TestRequestDurationMethodLabel:
    """Verify request_duration_seconds includes the method label."""

    def test_method_label_passed_to_histogram(self, recorder: MetricsRecorder) -> None:
        """REQUEST_DURATION with method label updates the correct histogram series."""
        recorder.record(
            MetricType.REQUEST_DURATION,
            100.0,
            unit="ms",
            labels={"endpoint": "/api/v1/workflows", "method": "POST", "status": "201", "interface": "api"},
        )
        sample_sum = recorder.prometheus.request_duration_seconds.labels(
            endpoint="/api/v1/workflows", method="POST", interface="api"
        )._sum.get()
        assert sample_sum == pytest.approx(0.1, rel=0.01)

    def test_different_methods_tracked_separately(self, recorder: MetricsRecorder) -> None:
        """GET and POST to the same endpoint produce separate histogram series."""
        recorder.record(
            MetricType.REQUEST_DURATION,
            50.0,
            unit="ms",
            labels={"endpoint": "/api/v1/projects", "method": "GET", "status": "200", "interface": "api"},
        )
        recorder.record(
            MetricType.REQUEST_DURATION,
            200.0,
            unit="ms",
            labels={"endpoint": "/api/v1/projects", "method": "POST", "status": "201", "interface": "api"},
        )
        get_sum = recorder.prometheus.request_duration_seconds.labels(
            endpoint="/api/v1/projects", method="GET", interface="api"
        )._sum.get()
        post_sum = recorder.prometheus.request_duration_seconds.labels(
            endpoint="/api/v1/projects", method="POST", interface="api"
        )._sum.get()
        assert get_sum == pytest.approx(0.05, rel=0.01)
        assert post_sum == pytest.approx(0.2, rel=0.01)


# =============================================================================
# Authz engine instrumentation
# =============================================================================


class TestAuthzEngineInstrumentation:
    """Verify _evaluate_authz_policy records OPA_REQUEST_DURATION."""

    @pytest.mark.asyncio
    async def test_evaluate_authz_policy_records_duration(self) -> None:
        """_evaluate_authz_policy records OPA_REQUEST_DURATION with resource_type and action."""
        from syntara.authz.engine import _evaluate_authz_policy

        mock_evaluator = MagicMock()
        mock_evaluator.evaluate = MagicMock(return_value={"allow": True})

        mock_recorder = MagicMock()
        with patch("syntara.metrics.dependencies.get_metrics_recorder", return_value=mock_recorder):
            await _evaluate_authz_policy(
                mock_evaluator,
                {"action": "create", "resource": {"type": "workflow"}},
                resource_type="workflow",
                action="create",
            )

        mock_recorder.record.assert_called_once()
        call_args = mock_recorder.record.call_args
        assert call_args[0][0] == MetricType.OPA_REQUEST_DURATION
        assert call_args[1]["labels"]["resource_type"] == "workflow"
        assert call_args[1]["labels"]["action"] == "create"

    @pytest.mark.asyncio
    async def test_evaluate_authz_policy_records_on_cache_miss_only(self) -> None:
        """Eval duration is only recorded on cache miss (actual evaluation), not cache hit."""
        from syntara.authz.engine import _evaluate_authz_policy, init_authz_cache

        init_authz_cache(enabled=True, ttl_seconds=300, maxsize=100)

        mock_evaluator = MagicMock()
        mock_evaluator.evaluate = MagicMock(return_value={"allow": True})

        mock_recorder = MagicMock()
        with patch("syntara.metrics.dependencies.get_metrics_recorder", return_value=mock_recorder):
            await _evaluate_authz_policy(
                mock_evaluator,
                {"action": "read", "resource": {"type": "project"}},
                resource_type="project",
                action="read",
            )
            first_call_count = mock_recorder.record.call_count

            await _evaluate_authz_policy(
                mock_evaluator,
                {"action": "read", "resource": {"type": "project"}},
                resource_type="project",
                action="read",
            )
            second_call_count = mock_recorder.record.call_count

        assert first_call_count == 1
        assert second_call_count == 1
        mock_evaluator.evaluate.assert_called_once()

        init_authz_cache(enabled=False)

    @pytest.mark.asyncio
    async def test_evaluate_authz_policy_metrics_failure_is_silent(self) -> None:
        """Metrics recording failure does not propagate to the caller."""
        from syntara.authz.engine import _evaluate_authz_policy

        mock_evaluator = MagicMock()
        mock_evaluator.evaluate = MagicMock(return_value={"allow": False})

        with patch("syntara.metrics.dependencies.get_metrics_recorder", side_effect=RuntimeError("broken")):
            result = await _evaluate_authz_policy(
                mock_evaluator,
                {"action": "delete", "resource": {"type": "workflow"}},
                resource_type="workflow",
                action="delete",
            )

        assert result == {"allow": False}


# =============================================================================
# Authz dependency instrumentation
# =============================================================================


class TestAuthzDependencyInstrumentation:
    """Verify _record_authz_duration helper records AUTHZ_DURATION."""

    def test_record_authz_duration_records_metric(self) -> None:
        """_record_authz_duration records AUTHZ_DURATION with correct labels."""
        import time

        from syntara.authz.dependencies import _record_authz_duration

        mock_recorder = MagicMock()
        start = time.perf_counter() - 0.05

        with patch("syntara.metrics.dependencies.get_metrics_recorder", return_value=mock_recorder):
            _record_authz_duration(start, "credential", "create")

        mock_recorder.record.assert_called_once()
        call_args = mock_recorder.record.call_args
        assert call_args[0][0] == MetricType.AUTHZ_DURATION
        assert call_args[0][1] >= 40.0
        assert call_args[1]["labels"]["resource_type"] == "credential"
        assert call_args[1]["labels"]["action"] == "create"

    def test_record_authz_duration_failure_is_silent(self) -> None:
        """Metrics recording failure does not propagate."""
        import time

        from syntara.authz.dependencies import _record_authz_duration

        start = time.perf_counter()
        with patch("syntara.metrics.dependencies.get_metrics_recorder", side_effect=RuntimeError("broken")):
            _record_authz_duration(start, "workflow", "read")


# =============================================================================
# Existing metrics not regressed
# =============================================================================


class TestExistingMetricsNotRegressed:
    """Verify existing metrics still work after authz metrics addition."""

    def test_request_duration_still_records(self, recorder: MetricsRecorder) -> None:
        """REQUEST_DURATION metric continues to work."""
        recorder.record(
            MetricType.REQUEST_DURATION,
            100.0,
            unit="ms",
            labels={"endpoint": "/api/v1/test", "method": "GET", "status": "200", "interface": "api"},
        )
        results = list(recorder.query(metric_types={MetricType.REQUEST_DURATION}))
        assert len(results) == 1

    def test_error_metric_still_records(self, recorder: MetricsRecorder) -> None:
        """ERROR metric continues to work."""
        recorder.record(MetricType.ERROR, 1.0, labels={"error_type": "internal", "interface": "api"})
        results = list(recorder.query(metric_types={MetricType.ERROR}))
        assert len(results) == 1

    def test_database_query_metric_still_records(self, recorder: MetricsRecorder) -> None:
        """DATABASE_QUERY_RESPONSE_TIME metric continues to work."""
        recorder.record(
            MetricType.DATABASE_QUERY_RESPONSE_TIME,
            5.0,
            unit="ms",
            labels={"statement_type": "SELECT"},
        )
        results = list(recorder.query(metric_types={MetricType.DATABASE_QUERY_RESPONSE_TIME}))
        assert len(results) == 1
