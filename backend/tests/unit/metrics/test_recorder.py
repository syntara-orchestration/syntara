"""Unit tests for the MetricsRecorder high-level recording API."""

import time
from datetime import UTC, datetime, timedelta

import pytest
from prometheus_client import CollectorRegistry

from syntara.metrics.recorder import MetricsRecorder
from syntara.metrics.types import ComponentLabel, MetricType


@pytest.fixture
def recorder() -> MetricsRecorder:
    """Fresh MetricsRecorder with an isolated Prometheus registry."""
    return MetricsRecorder(
        retention_seconds=3600,
        max_records=10_000,
        prometheus_registry=CollectorRegistry(),
    )


@pytest.fixture
def disabled_recorder() -> MetricsRecorder:
    """MetricsRecorder with collection disabled."""
    return MetricsRecorder(
        prometheus_registry=CollectorRegistry(),
        enabled=False,
    )


# =============================================================================
# Basic recording
# =============================================================================


class TestRecorderRecord:
    """Tests for the record() method."""

    def test_record_stores_metric(self, recorder: MetricsRecorder) -> None:
        """A recorded metric appears in the store."""
        recorder.record(MetricType.LLM_DURATION, 245.5, unit="ms", labels={"model": "gpt-4"})
        results = list(recorder.query(metric_types={MetricType.LLM_DURATION}))
        assert len(results) == 1
        assert results[0].value == pytest.approx(245.5)
        assert results[0].labels["model"] == "gpt-4"

    def test_record_multiple(self, recorder: MetricsRecorder) -> None:
        """Multiple records are stored independently."""
        recorder.record(MetricType.LLM_DURATION, 100.0)
        recorder.record(MetricType.LLM_TOKENS_INPUT, 1500, unit="tokens")
        recorder.record(MetricType.LLM_TOKENS_OUTPUT, 350, unit="tokens")

        all_results = list(recorder.query())
        assert len(all_results) == 3

    def test_record_disabled_is_noop(self, disabled_recorder: MetricsRecorder) -> None:
        """When disabled, record() silently does nothing."""
        disabled_recorder.record(MetricType.LLM_DURATION, 100.0)
        assert disabled_recorder.store.count() == 0


# =============================================================================
# Increment counters
# =============================================================================


class TestRecorderIncrement:
    """Tests for the increment() method."""

    def test_increment_counter(self, recorder: MetricsRecorder) -> None:
        """Incrementing a counter is reflected in the summary."""
        recorder.increment("requests", 1)
        recorder.increment("requests", 1)
        summary = recorder.get_summary()
        assert summary.total_requests == 2

    def test_increment_by_custom_value(self, recorder: MetricsRecorder) -> None:
        """Counter can be incremented by values other than 1."""
        recorder.increment("errors", 5)
        summary = recorder.get_summary()
        assert summary.total_errors == 5

    def test_increment_disabled_is_noop(self, disabled_recorder: MetricsRecorder) -> None:
        """When disabled, increment() silently does nothing."""
        disabled_recorder.increment("requests", 10)
        summary = disabled_recorder.get_summary()
        assert summary.total_requests == 0


# =============================================================================
# Gauge helpers (increment_gauge / decrement_gauge)
# =============================================================================


class TestRecorderGaugeHelpers:
    """Tests for increment_gauge() and decrement_gauge()."""

    def test_increment_gauge_updates_counter_and_prometheus(self, recorder: MetricsRecorder) -> None:
        recorder.increment_gauge("active_workflows")
        recorder.increment_gauge("active_workflows")

        assert recorder.get_summary().active_workflows == 2
        assert recorder.prometheus.active_workflows._value.get() == pytest.approx(2.0)

    def test_decrement_gauge_updates_counter_and_prometheus(self, recorder: MetricsRecorder) -> None:
        for _ in range(3):
            recorder.increment_gauge("active_workflows")

        recorder.decrement_gauge("active_workflows")

        assert recorder.get_summary().active_workflows == 2
        assert recorder.prometheus.active_workflows._value.get() == pytest.approx(2.0)

    def test_decrement_gauge_floors_at_zero(self, recorder: MetricsRecorder) -> None:
        """Decrementing a gauge that is already at 0 must not go negative."""
        assert recorder.get_summary().active_workflows == 0

        recorder.decrement_gauge("active_workflows")

        assert recorder.get_summary().active_workflows == 0
        assert recorder.prometheus.active_workflows._value.get() == pytest.approx(0.0)

    def test_decrement_gauge_floors_after_multiple(self, recorder: MetricsRecorder) -> None:
        """Several decrements below zero all stay at 0."""
        recorder.increment_gauge("active_workflows")

        recorder.decrement_gauge("active_workflows")
        recorder.decrement_gauge("active_workflows")
        recorder.decrement_gauge("active_workflows")

        assert recorder.get_summary().active_workflows == 0
        assert recorder.prometheus.active_workflows._value.get() == pytest.approx(0.0)

    def test_gauge_helpers_disabled_is_noop(self, disabled_recorder: MetricsRecorder) -> None:
        disabled_recorder.increment_gauge("active_workflows")
        assert disabled_recorder.get_summary().active_workflows == 0

        disabled_recorder.decrement_gauge("active_workflows")
        assert disabled_recorder.get_summary().active_workflows == 0


# =============================================================================
# Time context manager
# =============================================================================


class TestRecorderTime:
    """Tests for the time() context manager."""

    def test_time_records_duration(self, recorder: MetricsRecorder) -> None:
        """time() records elapsed time in milliseconds."""
        with recorder.time(MetricType.LLM_DURATION, labels={"model": "gpt-4"}):
            time.sleep(0.05)

        results = list(recorder.query(metric_types={MetricType.LLM_DURATION}))
        assert len(results) == 1
        assert results[0].value >= 40
        assert results[0].unit == "ms"

    def test_time_records_on_exception(self, recorder: MetricsRecorder) -> None:
        """Duration is still recorded when the body raises."""
        msg = "boom"
        with pytest.raises(ValueError, match=msg), recorder.time(MetricType.LLM_DURATION):
            raise ValueError(msg)

        results = list(recorder.query(metric_types={MetricType.LLM_DURATION}))
        assert len(results) == 1


# =============================================================================
# Query delegation
# =============================================================================


class TestRecorderQuery:
    """Tests for the query() passthrough."""

    def test_query_with_type_filter(self, recorder: MetricsRecorder) -> None:
        """query() delegates type filtering to the store."""
        recorder.record(MetricType.LLM_DURATION, 100.0)
        recorder.record(MetricType.CACHE_HIT, 1.0)

        results = list(recorder.query(metric_types={MetricType.CACHE_HIT}))
        assert len(results) == 1

    def test_query_with_label_filter(self, recorder: MetricsRecorder) -> None:
        """query() delegates label filtering to the store."""
        recorder.record(MetricType.LLM_DURATION, 100.0, labels={"model": "gpt-4"})
        recorder.record(MetricType.LLM_DURATION, 200.0, labels={"model": "claude"})

        results = list(recorder.query(labels={"model": "gpt-4"}))
        assert len(results) == 1
        assert results[0].value == pytest.approx(100.0)


# =============================================================================
# Summary
# =============================================================================


class TestRecorderSummary:
    """Tests for get_summary()."""

    def test_summary_defaults(self, recorder: MetricsRecorder) -> None:
        """A fresh recorder returns zero-valued summary."""
        summary = recorder.get_summary()
        assert summary.total_requests == 0
        assert summary.total_errors == 0
        assert summary.cache_hits == 0
        assert summary.cache_misses == 0
        assert summary.llm_calls == 0
        assert summary.total_workflows == 0

    def test_summary_reflects_increments(self, recorder: MetricsRecorder) -> None:
        """Summary counters reflect what was incremented."""
        recorder.increment("requests", 10)
        recorder.increment("errors", 2)
        recorder.increment("cache_hits", 7)
        recorder.increment("cache_misses", 3)
        recorder.increment("llm_calls", 8)
        recorder.increment("total_workflows", 15)
        for _ in range(2):
            recorder.increment_gauge("active_workflows")

        summary = recorder.get_summary()
        assert summary.total_requests == 10
        assert summary.total_errors == 2
        assert summary.cache_hits == 7
        assert summary.cache_misses == 3
        assert summary.llm_calls == 8
        assert summary.total_workflows == 15
        assert summary.active_workflows == 2

    def test_summary_period(self, recorder: MetricsRecorder) -> None:
        """Summary period_start is retention seconds before period_end."""
        summary = recorder.get_summary()
        delta = summary.period_end - summary.period_start
        assert abs(delta.total_seconds() - 3600) < 2


# =============================================================================
# Cleanup
# =============================================================================


class TestRecorderCleanup:
    """Tests for cleanup() delegation."""

    def test_cleanup_removes_expired(self) -> None:
        """cleanup() evicts records outside the retention window."""
        recorder = MetricsRecorder(
            retention_seconds=60,
            prometheus_registry=CollectorRegistry(),
        )

        old = MetricType.LLM_DURATION
        recorder.record(old, 1.0)
        # Back-date the record so it's expired
        record = next(iter(recorder.query()))
        record.created_at = datetime.now(UTC) - timedelta(hours=1)

        removed = recorder.cleanup()
        assert removed == 1


# =============================================================================
# Prometheus integration
# =============================================================================


class TestRecorderPrometheus:
    """Tests that recording updates Prometheus metrics."""

    def test_llm_duration_updates_histogram(self, recorder: MetricsRecorder) -> None:
        """Recording LLM_DURATION updates the Prometheus histogram."""
        recorder.record(
            MetricType.LLM_DURATION,
            500.0,
            unit="ms",
            labels={"model": "gpt-4"},
        )
        sample_value = recorder.prometheus.llm_duration_seconds.labels(model="gpt-4")._sum.get()
        assert sample_value == pytest.approx(0.5, rel=0.01)

    def test_cache_hit_updates_counter(self, recorder: MetricsRecorder) -> None:
        """Recording CACHE_HIT increments the Prometheus counter."""
        recorder.record(MetricType.CACHE_HIT, 1.0)
        recorder.record(MetricType.CACHE_HIT, 1.0)
        sample_value = recorder.prometheus.cache_hits_total._value.get()
        assert sample_value == pytest.approx(2.0)

    def test_cache_miss_updates_counter(self, recorder: MetricsRecorder) -> None:
        """Recording CACHE_MISS increments the Prometheus counter."""
        recorder.record(MetricType.CACHE_MISS, 1.0)
        sample_value = recorder.prometheus.cache_misses_total._value.get()
        assert sample_value == pytest.approx(1.0)

    def test_error_updates_counter(self, recorder: MetricsRecorder) -> None:
        """Recording ERROR increments the Prometheus errors counter."""
        recorder.record(
            MetricType.ERROR,
            1.0,
            labels={"error_type": "timeout", "interface": "api"},
        )
        sample_value = recorder.prometheus.errors_total.labels(error_type="timeout", interface="api")._value.get()
        assert sample_value == pytest.approx(1.0)

    def test_request_duration_updates_histogram(self, recorder: MetricsRecorder) -> None:
        """Recording REQUEST_DURATION updates the Prometheus histogram."""
        recorder.record(
            MetricType.REQUEST_DURATION,
            250.0,
            unit="ms",
            labels={"endpoint": "/api/v1/chat", "interface": "api"},
        )
        sample_value = recorder.prometheus.request_duration_seconds.labels(
            endpoint="/api/v1/chat", method="unknown", interface="api"
        )._sum.get()
        assert sample_value == pytest.approx(0.25, rel=0.01)

    def test_request_duration_increments_requests_total(self, recorder: MetricsRecorder) -> None:
        """Recording REQUEST_DURATION also increments requests_total."""
        recorder.record(
            MetricType.REQUEST_DURATION,
            100.0,
            unit="ms",
            labels={"endpoint": "/api/v1/health", "status": "200", "interface": "ui"},
        )
        value = recorder.prometheus.requests_total.labels(
            status="200",
            endpoint="/api/v1/health",
            interface="ui",
        )._value.get()
        assert value == pytest.approx(1.0)

    def test_auth_failure_dispatches_to_counter(self, recorder: MetricsRecorder) -> None:
        """Recording AUTH_FAILURE increments the auth_failures_total counter."""
        recorder.record(
            MetricType.AUTH_FAILURE,
            1.0,
            labels={"failure_type": "expired_token", "interface": "ui"},
        )
        value = recorder.prometheus.auth_failures_total.labels(
            failure_type="expired_token", interface="ui"
        )._value.get()
        assert value == pytest.approx(1.0)

    def test_auth_failure_defaults_interface_to_api(self, recorder: MetricsRecorder) -> None:
        """AUTH_FAILURE without explicit interface defaults to 'api'."""
        recorder.record(
            MetricType.AUTH_FAILURE,
            1.0,
            labels={"failure_type": "invalid_token"},
        )
        value = recorder.prometheus.auth_failures_total.labels(
            failure_type="invalid_token", interface="api"
        )._value.get()
        assert value == pytest.approx(1.0)

    def test_llm_duration_does_not_increment_calls_total(self, recorder: MetricsRecorder) -> None:
        """LLM_DURATION only updates the histogram; llm_calls_total is owned by LLM_STATUS.

        This separation avoids double-counting because _record_llm_metrics
        emits both LLM_DURATION and LLM_STATUS for every call. If both
        branches incremented llm_calls_total the counter would be 2x.
        """
        recorder.record(
            MetricType.LLM_DURATION,
            200.0,
            unit="ms",
            labels={"model": "gpt-4", "status": "success"},
        )
        value = recorder.prometheus.llm_calls_total.labels(
            model="gpt-4",
            status="success",
        )._value.get()
        assert value == pytest.approx(0.0)

    def test_llm_status_increments_calls_total(self, recorder: MetricsRecorder) -> None:
        """LLM_STATUS is the sole owner of llm_calls_total in Prometheus."""
        recorder.record(
            MetricType.LLM_STATUS,
            1.0,
            labels={"model": "gpt-4", "status": "success"},
        )
        recorder.record(
            MetricType.LLM_STATUS,
            1.0,
            labels={"model": "gpt-4", "status": "error"},
        )
        success = recorder.prometheus.llm_calls_total.labels(
            model="gpt-4",
            status="success",
        )._value.get()
        error = recorder.prometheus.llm_calls_total.labels(
            model="gpt-4",
            status="error",
        )._value.get()
        assert success == pytest.approx(1.0)
        assert error == pytest.approx(1.0)

    def test_llm_ttft_updates_histogram(self, recorder: MetricsRecorder) -> None:
        """LLM_TTFT populates the Prometheus TTFT histogram."""
        recorder.record(
            MetricType.LLM_TTFT,
            120.0,
            unit="ms",
            labels={"model": "gpt-4"},
        )
        sample_value = recorder.prometheus.ttft_seconds.labels(model="gpt-4")._sum.get()
        assert sample_value == pytest.approx(0.12)

    def test_workflow_duration_updates_counter(self, recorder: MetricsRecorder) -> None:
        """Recording WORKFLOW_DURATION also increments workflows_total counter."""
        recorder.record(
            MetricType.WORKFLOW_DURATION,
            5000.0,
            unit="ms",
            labels={"workflow_type": "deploy"},
        )
        recorder.record(
            MetricType.WORKFLOW_DURATION,
            3000.0,
            unit="ms",
            labels={"workflow_type": "deploy"},
        )
        sample_value = recorder.prometheus.workflows_total.labels(workflow_type="deploy")._value.get()
        assert sample_value == pytest.approx(2.0)

    def test_api_response_time_updates_histogram(self, recorder: MetricsRecorder) -> None:
        """Recording API_RESPONSE_TIME updates the component histogram."""
        recorder.record(
            MetricType.API_RESPONSE_TIME,
            150.0,
            unit="ms",
            labels={"endpoint": "/chat", "method": "POST"},
            component=ComponentLabel.API_SERVICE,
        )
        sample_value = recorder.prometheus.api_response_time_seconds.labels(
            component="api_service",
            endpoint="/chat",
            method="POST",
        )._sum.get()
        assert sample_value == pytest.approx(0.15, rel=0.01)

    def test_temporal_queue_depth_updates_gauge(self, recorder: MetricsRecorder) -> None:
        """Recording TEMPORAL_QUEUE_DEPTH sets the gauge with component and task_queue labels."""
        recorder.record(
            MetricType.TEMPORAL_QUEUE_DEPTH,
            42.0,
            component=ComponentLabel.TEMPORAL_WORKER,
            labels={"task_queue": "orchestrator-workflow-queue"},
        )
        sample_value = recorder.prometheus.temporal_queue_depth.labels(
            component="temporal_worker",
            task_queue="orchestrator-workflow-queue",
        )._value.get()
        assert sample_value == pytest.approx(42.0)

    def test_temporal_queue_depth_distinguishes_queues(self, recorder: MetricsRecorder) -> None:
        """Each task_queue label value produces an independent Prometheus time series."""
        recorder.record(
            MetricType.TEMPORAL_QUEUE_DEPTH,
            10.0,
            component=ComponentLabel.TEMPORAL_WORKER,
            labels={"task_queue": "orchestrator-workflow-queue"},
        )
        recorder.record(
            MetricType.TEMPORAL_QUEUE_DEPTH,
            5.0,
            component=ComponentLabel.TEMPORAL_WORKER,
            labels={"task_queue": "orchestrator-background-queue"},
        )
        wf_value = recorder.prometheus.temporal_queue_depth.labels(
            component="temporal_worker",
            task_queue="orchestrator-workflow-queue",
        )._value.get()
        bg_value = recorder.prometheus.temporal_queue_depth.labels(
            component="temporal_worker",
            task_queue="orchestrator-background-queue",
        )._value.get()
        assert wf_value == pytest.approx(10.0)
        assert bg_value == pytest.approx(5.0)

    def test_tool_execution_duration_dispatches_to_histogram_and_counter(self, recorder: MetricsRecorder) -> None:
        """TOOL_EXECUTION_DURATION updates histogram (observe) and counter (inc)."""
        recorder.record(
            MetricType.TOOL_EXECUTION_DURATION,
            1500.0,
            unit="ms",
            labels={
                "namespaced_name": "github::search_code",
                "status": "success",
            },
        )
        hist_sum = recorder.prometheus.tool_execution_duration_seconds.labels(
            namespaced_name="github::search_code",
        )._sum.get()
        assert hist_sum == pytest.approx(1.5)
        counter_val = recorder.prometheus.tool_executions_total.labels(
            namespaced_name="github::search_code",
            status="success",
            error_code="none",
        )._value.get()
        assert counter_val == pytest.approx(1.0)

    def test_tool_execution_status_dispatches_to_counter_only(self, recorder: MetricsRecorder) -> None:
        """TOOL_EXECUTION_STATUS increments counter only (no histogram)."""
        recorder.record(
            MetricType.TOOL_EXECUTION_STATUS,
            1.0,
            labels={
                "namespaced_name": "github::search_code",
                "status": "error",
                "error_code": "TimeoutError",
            },
        )
        counter_val = recorder.prometheus.tool_executions_total.labels(
            namespaced_name="github::search_code",
            status="error",
            error_code="TimeoutError",
        )._value.get()
        assert counter_val == pytest.approx(1.0)

    def test_tool_execution_missing_namespaced_name_raises(self, recorder: MetricsRecorder) -> None:
        """Missing namespaced_name label raises ValueError in dispatch."""
        from syntara.core.exceptions import SafeValueError

        with pytest.raises(SafeValueError, match="namespaced_name"):
            recorder._dispatch_tool_execution(
                MetricType.TOOL_EXECUTION_DURATION,
                500.0,
                {"status": "success"},
                recorder.prometheus,
            )

    def test_tool_execution_missing_status_defaults_to_unknown(self, recorder: MetricsRecorder) -> None:
        """Missing status label defaults to 'unknown'."""
        recorder.record(
            MetricType.TOOL_EXECUTION_DURATION,
            500.0,
            unit="ms",
            labels={"namespaced_name": "github::search_code"},
        )
        counter_val = recorder.prometheus.tool_executions_total.labels(
            namespaced_name="github::search_code",
            status="unknown",
            error_code="none",
        )._value.get()
        assert counter_val == pytest.approx(1.0)

    def test_workflow_serialization_duration_updates_histogram(self, recorder: MetricsRecorder) -> None:
        """Recording WORKFLOW_SERIALIZATION_DURATION observes the histogram."""
        recorder.record(
            MetricType.WORKFLOW_SERIALIZATION_DURATION,
            150.0,
            unit="ms",
            labels={"component": "workflow_engine"},
        )
        sample = recorder.prometheus.workflow_serialization_duration_seconds.labels(
            component="workflow_engine",
        )
        assert sample._sum.get() == pytest.approx(0.15)

    def test_workflow_validation_duration_updates_histogram(self, recorder: MetricsRecorder) -> None:
        """Recording WORKFLOW_VALIDATION_DURATION observes the histogram."""
        recorder.record(
            MetricType.WORKFLOW_VALIDATION_DURATION,
            80.0,
            unit="ms",
            labels={"component": "workflow_engine"},
        )
        sample = recorder.prometheus.workflow_validation_duration_seconds.labels(
            component="workflow_engine",
        )
        assert sample._sum.get() == pytest.approx(0.08)

    def test_temporal_execution_service_duration_updates_histogram(self, recorder: MetricsRecorder) -> None:
        """Recording TEMPORAL_EXECUTION_SERVICE_DURATION observes the histogram."""
        recorder.record(
            MetricType.TEMPORAL_EXECUTION_SERVICE_DURATION,
            250.0,
            unit="ms",
            labels={"component": "execution_service"},
        )
        sample = recorder.prometheus.temporal_execution_service_duration_seconds.labels(
            component="execution_service",
        )
        assert sample._sum.get() == pytest.approx(0.25)

    def test_workflow_creation_success_rate_updates_gauge(self, recorder: MetricsRecorder) -> None:
        """Recording WORKFLOW_CREATION_SUCCESS_RATE sets the gauge."""
        recorder.record(
            MetricType.WORKFLOW_CREATION_SUCCESS_RATE,
            1.0,
            component=ComponentLabel.WORKFLOW_ENGINE,
        )
        sample_value = recorder.prometheus.workflow_creation_success_rate.labels(
            component="workflow_engine",
        )._value.get()
        assert sample_value == pytest.approx(1.0)

    def test_activity_duration_updates_labeled_histogram(self, recorder: MetricsRecorder) -> None:
        """Recording ACTIVITY_DURATION observes the histogram with labels."""
        recorder.record(
            MetricType.ACTIVITY_DURATION,
            1500.0,
            unit="ms",
            labels={
                "activity_name": "send_email",
                "status": "completed",
                "workflow_type": "onboarding",
            },
        )
        sample = recorder.prometheus.activity_duration_seconds.labels(
            activity_name="send_email",
            status="completed",
            workflow_type="onboarding",
        )
        assert sample._sum.get() == pytest.approx(1.5)

    def test_activity_execution_success_rate_updates_gauge(self, recorder: MetricsRecorder) -> None:
        """Recording ACTIVITY_EXECUTION_SUCCESS_RATE sets the gauge."""
        recorder.record(
            MetricType.ACTIVITY_EXECUTION_SUCCESS_RATE,
            0.75,
            component=ComponentLabel.TEMPORAL_WORKER,
        )
        sample_value = recorder.prometheus.activity_execution_success_rate.labels(
            component="temporal_worker",
        )._value.get()
        assert sample_value == pytest.approx(0.75)

    def test_workflow_start_latency_updates_histogram(self, recorder: MetricsRecorder) -> None:
        """Recording WORKFLOW_START_LATENCY observes the histogram."""
        recorder.record(
            MetricType.WORKFLOW_START_LATENCY,
            250.0,
            unit="ms",
            labels={"component": "execution_service"},
        )
        sample = recorder.prometheus.workflow_start_latency_seconds.labels(
            component="execution_service",
        )
        assert sample._sum.get() == pytest.approx(0.25)

    def test_workflow_completion_rate_updates_gauge(self, recorder: MetricsRecorder) -> None:
        """Recording WORKFLOW_COMPLETION_RATE sets the gauge."""
        recorder.record(
            MetricType.WORKFLOW_COMPLETION_RATE,
            1.0,
            component=ComponentLabel.EXECUTION_SERVICE,
        )
        sample_value = recorder.prometheus.workflow_completion_rate.labels(
            component="execution_service",
        )._value.get()
        assert sample_value == pytest.approx(1.0)

    def test_system_uptime_updates_gauge(self, recorder: MetricsRecorder) -> None:
        """Recording SYSTEM_UPTIME sets the system-wide gauge."""
        recorder.record(
            MetricType.SYSTEM_UPTIME,
            3600.5,
            component=ComponentLabel.SYSTEM_WIDE,
        )
        sample_value = recorder.prometheus.system_uptime.labels(
            component="system_wide",
        )._value.get()
        assert sample_value == pytest.approx(3600.5)

    def test_enabled_property(self, recorder: MetricsRecorder) -> None:
        """Enabled property reflects constructor argument."""
        assert recorder.enabled is True

    def test_disabled_property(self, disabled_recorder: MetricsRecorder) -> None:
        """Enabled property is False when recording is disabled."""
        assert disabled_recorder.enabled is False


# =============================================================================
# Store-disabled mode (Prometheus still works, in-memory store skipped)
# =============================================================================


class TestStoreDisabledMode:
    """When store_enabled=False, Prometheus is updated but the store stays empty."""

    @pytest.fixture
    def store_disabled_recorder(self) -> MetricsRecorder:
        """Recorder with the in-memory store disabled."""
        return MetricsRecorder(
            prometheus_registry=CollectorRegistry(),
            store_enabled=False,
        )

    def test_store_enabled_property(self, recorder: MetricsRecorder) -> None:
        """Default recorder has store_enabled=True."""
        assert recorder.store_enabled is True

    def test_store_disabled_property(self, store_disabled_recorder: MetricsRecorder) -> None:
        """Store-disabled recorder exposes the flag."""
        assert store_disabled_recorder.store_enabled is False

    def test_record_skips_store(self, store_disabled_recorder: MetricsRecorder) -> None:
        """Records are not added to the in-memory store."""
        store_disabled_recorder.record(MetricType.LLM_DURATION, 100.0, labels={"model": "gpt-4"})
        assert store_disabled_recorder.store.count() == 0

    def test_record_updates_prometheus(self, store_disabled_recorder: MetricsRecorder) -> None:
        """Prometheus metrics are still updated even when the store is disabled."""
        store_disabled_recorder.record(MetricType.LLM_DURATION, 100.0, labels={"model": "gpt-4"})
        sample = store_disabled_recorder.prometheus.llm_duration_seconds.labels(model="gpt-4")
        assert sample._sum.get() > 0

    def test_query_returns_empty(self, store_disabled_recorder: MetricsRecorder) -> None:
        """Queries against a store-disabled recorder return nothing."""
        store_disabled_recorder.record(MetricType.CACHE_HIT, 1.0)
        results = list(store_disabled_recorder.query(metric_types={MetricType.CACHE_HIT}))
        assert results == []

    def test_store_enabled_setter_toggles_at_runtime(self, recorder: MetricsRecorder) -> None:
        """store_enabled can be flipped after construction."""
        assert recorder.store_enabled is True
        recorder.store_enabled = False
        assert recorder.store_enabled is False
        recorder.record(MetricType.CACHE_HIT, 1.0)
        assert recorder.store.count() == 0

        recorder.store_enabled = True
        recorder.record(MetricType.CACHE_HIT, 1.0)
        assert recorder.store.count() == 1


# =============================================================================
# Component label parameter
# =============================================================================


class TestComponentLabelParameter:
    """Tests for the typed component parameter in record()."""

    def test_component_added_to_labels(self, recorder: MetricsRecorder) -> None:
        """Component parameter is stored as a label on the record."""
        recorder.record(
            MetricType.API_RESPONSE_TIME,
            120.0,
            unit="ms",
            labels={"endpoint": "/health"},
            component=ComponentLabel.API_SERVICE,
        )
        records = list(recorder.query())
        assert len(records) == 1
        assert records[0].labels["component"] == "api_service"

    def test_missing_component_still_records(self, recorder: MetricsRecorder) -> None:
        """Metric is recorded even without a component."""
        recorder.record(MetricType.LLM_DURATION, 50.0, unit="ms")
        records = list(recorder.query())
        assert len(records) == 1
        assert "component" not in records[0].labels

    def test_all_component_labels_accepted(self, recorder: MetricsRecorder) -> None:
        """Every ComponentLabel value is accepted."""
        for component in ComponentLabel:
            recorder.record(
                MetricType.SYSTEM_UPTIME,
                1.0,
                component=component,
            )
