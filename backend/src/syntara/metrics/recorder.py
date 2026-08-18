"""High-level metrics recording API for Syntara components.

:class:`MetricsRecorder` is the primary entry-point that application code
uses to record metrics.  It delegates storage to :class:`MetricsStore` and
keeps Prometheus counters / histograms in sync via
:class:`OrchestratorPrometheusMetrics`.

Usage::

    recorder = MetricsRecorder()
    recorder.record(MetricType.LLM_DURATION, 245.5, unit="ms",
                    labels={"model": "gpt-4"})

    with recorder.time(MetricType.LLM_DURATION, labels={"model": "gpt-4"}):
        result = await call_llm(...)
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from syntara.core.exceptions import SafeValueError
from syntara.metrics.prometheus import OrchestratorPrometheusMetrics
from syntara.metrics.store import MetricsStore
from syntara.metrics.types import ComponentLabel, MetricRecord, MetricsSummary, MetricType

if TYPE_CHECKING:
    from collections.abc import Iterator

    from prometheus_client import CollectorRegistry

logger = structlog.stdlib.get_logger(__name__)

# Table-driven dispatch for component-level Prometheus metrics.
# Each entry: (prometheus_attr, action, extra_label_keys)
#   action: "gauge" -> .set(value)
#           "histogram" -> .observe(value / 1000)
#           "counter" -> .inc()
_COMPONENT_METRIC_MAP: dict[MetricType, tuple[str, str, tuple[str, ...]]] = {
    # API Service
    MetricType.API_RESPONSE_TIME: ("api_response_time_seconds", "histogram", ("endpoint", "method")),
    MetricType.API_ERROR_RATE: ("api_error_rate", "gauge", ()),
    MetricType.API_THROUGHPUT: ("api_throughput_rps", "gauge", ()),
    # Workflow Engine
    MetricType.WORKFLOW_CREATION_SUCCESS_RATE: ("workflow_creation_success_rate", "gauge", ()),
    MetricType.WORKFLOW_SERIALIZATION_DURATION: ("workflow_serialization_duration_seconds", "histogram", ()),
    MetricType.WORKFLOW_VALIDATION_DURATION: ("workflow_validation_duration_seconds", "histogram", ()),
    # Temporal Worker
    MetricType.TEMPORAL_QUEUE_DEPTH: ("temporal_queue_depth", "gauge", ("task_queue",)),
    MetricType.ACTIVE_WORKFLOWS: ("active_workflows", "gauge", ()),
    MetricType.ACTIVITY_EXECUTION_SUCCESS_RATE: ("activity_execution_success_rate", "gauge", ()),
    # Execution Service
    MetricType.WORKFLOW_START_LATENCY: ("workflow_start_latency_seconds", "histogram", ()),
    MetricType.WORKFLOW_COMPLETION_RATE: ("workflow_completion_rate", "gauge", ()),
    MetricType.TEMPORAL_EXECUTION_SERVICE_DURATION: ("temporal_execution_service_duration_seconds", "histogram", ()),
    # Database
    MetricType.DATABASE_QUERY_RESPONSE_TIME: ("database_query_response_time_seconds", "histogram", ("table_name",)),
    MetricType.DATABASE_CONNECTION_POOL_UTILIZATION: ("database_connection_pool_utilization", "gauge", ()),
    MetricType.DATABASE_TRANSACTION_RATE: ("database_transaction_rate_tps", "gauge", ()),
    # Cache (Redis) pool retry/backoff
    MetricType.CACHE_POOL_RETRY: ("cache_pool_retry_total", "counter", ("operation", "outcome")),
    MetricType.CACHE_POOL_RETRY_BACKOFF_DURATION: (
        "cache_pool_retry_backoff_duration_seconds",
        "histogram",
        ("operation",),
    ),
    # System-Wide
    MetricType.SYSTEM_UPTIME: ("system_uptime", "gauge", ()),
    MetricType.SYSTEM_E2E_LATENCY: ("system_e2e_latency_seconds", "histogram", ()),
    MetricType.SYSTEM_ERROR_RATE: ("system_error_rate", "gauge", ()),
}


class MetricsRecorder:
    """Central metrics recording service.

    Thread-safe, non-blocking metrics recording with configurable retention.

    In distributed deployments each service instance owns its own recorder.
    Prometheus handles cross-instance aggregation at scrape time.

    Args:
        retention_seconds: How long to keep raw metrics (default 24 h).
        max_records: Upper bound on stored records.
        prometheus_registry: Optional Prometheus ``CollectorRegistry``.
            Pass *None* to create an isolated private registry (recommended
            for tests).
        enabled: When *False* all recording is silently skipped.
        store_enabled: When *False* the in-memory :class:`MetricsStore` is
            not populated (saving RAM), but Prometheus counters/histograms
            are still updated so ``GET /metrics`` keeps working.

    """

    def __init__(
        self,
        retention_seconds: int = 3600,
        max_records: int = 100_000,
        prometheus_registry: CollectorRegistry | None = None,
        *,
        enabled: bool = True,
        store_enabled: bool = True,
    ) -> None:
        """Initialise the recorder, its backing store, and Prometheus metrics."""
        self._enabled = enabled
        self._store_enabled = store_enabled
        self._store = MetricsStore(
            retention_seconds=retention_seconds,
            max_records=max_records,
        )
        self._prometheus = OrchestratorPrometheusMetrics(registry=prometheus_registry)
        self._counters: dict[str, int] = {}
        self._counters_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def store(self) -> MetricsStore:
        """Underlying metrics store (useful for direct queries)."""
        return self._store

    @property
    def prometheus(self) -> OrchestratorPrometheusMetrics:
        """Prometheus metric objects."""
        return self._prometheus

    @property
    def enabled(self) -> bool:
        """Whether recording is active."""
        return self._enabled

    @property
    def store_enabled(self) -> bool:
        """Whether the in-memory store is populated."""
        return self._store_enabled

    @store_enabled.setter
    def store_enabled(self, value: bool) -> None:
        """Toggle the in-memory store at runtime."""
        self._store_enabled = value

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        metric_type: MetricType,
        value: float,
        unit: str = "",
        labels: dict[str, str] | None = None,
        component: ComponentLabel | None = None,
    ) -> None:
        """Record a single metric (non-blocking).

        The record is appended to the in-memory store *and* the matching
        Prometheus metric is updated.

        Args:
            metric_type: The kind of metric being recorded.
            value: Numeric observation value.
            unit: Optional unit string (e.g. ``"ms"``, ``"tokens"``).
            labels: Free-form string labels attached to the record.
            component: Optional component identifier for component-level
                metrics dispatched via :data:`_COMPONENT_METRIC_MAP`.

        """
        if not self._enabled:
            return

        metric_labels = labels or {}
        if component is not None:
            metric_labels = {**metric_labels, "component": component.value}

        if self._store_enabled:
            record = MetricRecord(
                metric_type=metric_type,
                value=value,
                unit=unit,
                labels=metric_labels,
            )
            self._store.add(record)
        self._update_prometheus(metric_type, value, metric_labels)

    def increment(self, counter_name: str, value: int = 1) -> None:
        """Increment an internal named counter."""
        if not self._enabled:
            return
        with self._counters_lock:
            self._counters[counter_name] = self._counters.get(counter_name, 0) + value

    def increment_gauge(self, gauge_name: str) -> None:
        """Increment the named internal counter and the matching Prometheus gauge."""
        if not self._enabled:
            return

        with self._counters_lock:
            self._counters[gauge_name] = self._counters.get(gauge_name, 0) + 1

        prom_gauge = getattr(self._prometheus, gauge_name, None)
        if prom_gauge is not None:
            prom_gauge.inc()

    def decrement_gauge(self, gauge_name: str) -> None:
        """Decrement the named internal counter and the matching Prometheus gauge, floored at zero.

        After a server restart the in-memory counter resets to 0 while the
        completion poller may still emit metrics for workflows that started
        before the restart.  A naive decrement would push the value below
        zero, producing nonsensical metrics.  This method prevents that.
        """
        if not self._enabled:
            return

        with self._counters_lock:
            current = self._counters.get(gauge_name, 0)
            self._counters[gauge_name] = max(0, current - 1)

        prom_gauge = getattr(self._prometheus, gauge_name, None)
        if prom_gauge is not None:
            prom_value = prom_gauge._value.get()  # noqa: SLF001
            if prom_value > 0:
                prom_gauge.dec()
            else:
                prom_gauge.set(0)

    @contextmanager
    def time(
        self,
        metric_type: MetricType,
        labels: dict[str, str] | None = None,
    ) -> Iterator[None]:
        """Context manager that records the elapsed wall-clock time as a metric.

        Example::

            with recorder.time(MetricType.LLM_DURATION, labels={"model": "gpt-4"}):
                response = await llm.invoke(prompt)

        """
        start = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            self.record(metric_type, duration_ms, unit="ms", labels=labels)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def query(
        self,
        metric_types: set[MetricType] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        labels: dict[str, str] | None = None,
    ) -> Iterator[MetricRecord]:
        """Query metrics with optional filters.

        Delegates to :meth:`MetricsStore.query`.
        """
        return self._store.query(
            metric_types=metric_types,
            start_time=start_time,
            end_time=end_time,
            labels=labels,
        )

    def _get_active_workflows_from_gauge(self) -> int:
        """Read the current active_workflows value from the Prometheus gauge.

        The poller sets this via ``record(MetricType.ACTIVE_WORKFLOWS, ...)``
        which routes through ``_dispatch_component`` → ``.labels(...).set()``.
        Before the first poll the gauge has no samples, so we return 0.
        """
        try:
            gauge = self._prometheus.active_workflows.labels(component=ComponentLabel.TEMPORAL_WORKER.value)
            # prometheus_client has no public API for reading a gauge value;
            # _value is a private ValueClass. The except guard handles library changes.
            return int(gauge._value.get())  # noqa: SLF001
        except Exception:  # noqa: BLE001
            logger.debug("active_workflows_gauge_read_failed", exc_info=True)
            return 0

    def get_summary(self) -> MetricsSummary:
        """Build a point-in-time summary of internal counters."""
        now = datetime.now(UTC)
        with self._counters_lock:
            counters_snapshot = dict(self._counters)
        return MetricsSummary(
            total_requests=counters_snapshot.get("requests", 0),
            total_errors=counters_snapshot.get("errors", 0),
            cache_hits=counters_snapshot.get("cache_hits", 0),
            cache_misses=counters_snapshot.get("cache_misses", 0),
            llm_calls=counters_snapshot.get("llm_calls", 0),
            total_workflows=counters_snapshot.get("total_workflows", 0),
            active_workflows=self._get_active_workflows_from_gauge(),
            active_llm_requests=counters_snapshot.get("active_llm_requests", 0),
            db_transactions=counters_snapshot.get("db_transactions", 0),
            period_start=now - self._store.retention,
            period_end=now,
        )

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def cleanup(self) -> int:
        """Evict expired records from the store.

        Returns:
            Number of records removed.

        """
        return self._store.cleanup()

    # ------------------------------------------------------------------
    # Prometheus bridge
    # ------------------------------------------------------------------

    def _update_prometheus(
        self,
        metric_type: MetricType,
        value: float,
        labels: dict[str, str],
    ) -> None:
        """Map a MetricType recording to its Prometheus counterpart."""
        try:
            self._dispatch_prometheus(metric_type, value, labels)
        except Exception:  # noqa: BLE001
            logger.debug("Failed to update Prometheus metric", metric_type=metric_type, exc_info=True)

    def _dispatch_prometheus(  # noqa: C901, PLR0912
        self,
        metric_type: MetricType,
        value: float,
        labels: dict[str, str],
    ) -> None:
        """Dispatch metric to the appropriate Prometheus instrument."""
        p = self._prometheus

        if metric_type in {
            MetricType.REQUEST_DURATION,
            MetricType.LLM_DURATION,
            MetricType.LLM_TTFT,
        }:
            MetricsRecorder._dispatch_latency(metric_type, value, labels, p)

        elif metric_type in {
            MetricType.LLM_STATUS,
            MetricType.LLM_TOKENS_INPUT,
            MetricType.LLM_TOKENS_OUTPUT,
        }:
            MetricsRecorder._dispatch_llm_event(metric_type, value, labels, p)

        elif metric_type in {
            MetricType.CACHE_HIT,
            MetricType.CACHE_MISS,
            MetricType.CACHE_LOOKUP_DURATION,
            MetricType.CACHE_UTILIZATION,
        }:
            MetricsRecorder._dispatch_cache(metric_type, value, p)

        elif metric_type == MetricType.WORKFLOW_DURATION:
            p.workflow_duration_seconds.observe(value / 1000)
            p.workflows_total.labels(
                workflow_type=labels.get("workflow_type", "unknown"),
            ).inc()

        elif metric_type == MetricType.ACTIVITY_DURATION:
            p.activity_duration_seconds.labels(
                activity_name=labels.get("activity_name", "unknown"),
                status=labels.get("status", "unknown"),
                workflow_type=labels.get("workflow_type", "unknown"),
            ).observe(value / 1000)

        elif metric_type == MetricType.ERROR:
            p.errors_total.labels(
                error_type=labels.get("error_type", "unknown"),
                interface=labels.get("interface", "api"),
            ).inc()

        elif metric_type == MetricType.AUTH_FAILURE:
            p.auth_failures_total.labels(
                failure_type=labels.get("failure_type", "unknown"),
                interface=labels.get("interface", "api"),
            ).inc()

        elif metric_type in {
            MetricType.TOOL_EXECUTION_DURATION,
            MetricType.TOOL_EXECUTION_STATUS,
        }:
            MetricsRecorder._dispatch_tool_execution(metric_type, value, labels, p)

        elif metric_type in {
            MetricType.DATABASE_QUERY_RESPONSE_TIME,
            MetricType.DATABASE_CONNECTION_POOL_UTILIZATION,
            MetricType.DATABASE_TRANSACTION_RATE,
        }:
            MetricsRecorder._dispatch_database(metric_type, value, labels, p)

        elif metric_type == MetricType.CONTEXT_DURATION:
            p.context_duration_seconds.observe(value / 1000)

        elif metric_type in {
            MetricType.AUTHZ_DURATION,
            MetricType.OPA_REQUEST_DURATION,
        }:
            MetricsRecorder._dispatch_authz(metric_type, value, labels, p)

        elif metric_type in {
            MetricType.SCHEDULED_TRIGGER_FIRES,
            MetricType.SCHEDULED_TRIGGER_LATENCY,
        }:
            MetricsRecorder._dispatch_scheduled_trigger(metric_type, value, labels, p)

        else:
            MetricsRecorder._dispatch_component(metric_type, value, labels, p)

    @staticmethod
    def _dispatch_latency(
        metric_type: MetricType,
        value: float,
        labels: dict[str, str],
        p: OrchestratorPrometheusMetrics,
    ) -> None:
        """Handle request, LLM, and TTFT latency metrics."""
        if metric_type == MetricType.REQUEST_DURATION:
            endpoint = labels.get("endpoint", "unknown")
            method = labels.get("method", "unknown")
            status_label = labels.get("status", "unknown")
            interface = labels.get("interface", "api")
            p.request_duration_seconds.labels(endpoint=endpoint, method=method, interface=interface).observe(
                value / 1000
            )
            p.requests_total.labels(status=status_label, endpoint=endpoint, interface=interface).inc()

        elif metric_type == MetricType.LLM_DURATION:
            p.llm_duration_seconds.labels(
                model=labels.get("model", "unknown"),
            ).observe(value / 1000)

        elif metric_type == MetricType.LLM_TTFT:
            p.ttft_seconds.labels(
                model=labels.get("model", "unknown"),
            ).observe(value / 1000)

    @staticmethod
    def _dispatch_llm_event(
        metric_type: MetricType,
        value: float,
        labels: dict[str, str],
        p: OrchestratorPrometheusMetrics,
    ) -> None:
        """Handle LLM status and token metrics."""
        model = labels.get("model", "unknown")

        if metric_type == MetricType.LLM_STATUS:
            p.llm_calls_total.labels(model=model, status=labels.get("status", "unknown")).inc()
        elif metric_type == MetricType.LLM_TOKENS_INPUT:
            p.llm_tokens_input_total.labels(model=model).inc(value)
        elif metric_type == MetricType.LLM_TOKENS_OUTPUT:
            p.llm_tokens_output_total.labels(model=model).inc(value)

    @staticmethod
    def _dispatch_cache(
        metric_type: MetricType,
        value: float,
        p: OrchestratorPrometheusMetrics,
    ) -> None:
        """Handle cache metrics (hits, misses, lookup duration, utilization)."""
        if metric_type == MetricType.CACHE_HIT:
            p.cache_hits_total.inc()
        elif metric_type == MetricType.CACHE_MISS:
            p.cache_misses_total.inc()
        elif metric_type == MetricType.CACHE_LOOKUP_DURATION:
            p.cache_lookup_duration_seconds.observe(value / 1000)
        elif metric_type == MetricType.CACHE_UTILIZATION:
            p.cache_utilization_ratio.set(value)

    @staticmethod
    def _dispatch_tool_execution(
        metric_type: MetricType,
        value: float,
        labels: dict[str, str],
        p: OrchestratorPrometheusMetrics,
    ) -> None:
        """Handle tool execution metrics (duration and status)."""
        namespaced_name = labels.get("namespaced_name")
        if not namespaced_name:
            msg = "Tool metrics require a 'namespaced_name' label"
            raise SafeValueError(msg)
        status = labels.get("status", "unknown")
        error_code = labels.get("error_code", "none")

        if metric_type == MetricType.TOOL_EXECUTION_DURATION:
            p.tool_execution_duration_seconds.labels(
                namespaced_name=namespaced_name,
            ).observe(value / 1000)
            p.tool_executions_total.labels(
                namespaced_name=namespaced_name,
                status=status,
                error_code=error_code,
            ).inc()
        elif metric_type == MetricType.TOOL_EXECUTION_STATUS:
            p.tool_executions_total.labels(
                namespaced_name=namespaced_name,
                status=status,
                error_code=error_code,
            ).inc()

    @staticmethod
    def _dispatch_database(
        metric_type: MetricType,
        value: float,
        labels: dict[str, str],
        p: OrchestratorPrometheusMetrics,
    ) -> None:
        """Handle database metrics (query time, pool utilization, transactions)."""
        component = labels.get("component", "database")

        if metric_type == MetricType.DATABASE_QUERY_RESPONSE_TIME:
            statement_type = labels.get("statement_type", "unknown")
            p.database_query_response_time_seconds.labels(
                component=component,
                statement_type=statement_type,
            ).observe(value / 1000)

        elif metric_type == MetricType.DATABASE_CONNECTION_POOL_UTILIZATION:
            p.database_connection_pool_utilization.labels(component=component).set(value)

        elif metric_type == MetricType.DATABASE_TRANSACTION_RATE:
            p.database_transaction_rate_tps.labels(component=component).inc()

    @staticmethod
    def _dispatch_scheduled_trigger(
        metric_type: MetricType,
        value: float,
        labels: dict[str, str],
        p: OrchestratorPrometheusMetrics,
    ) -> None:
        """Handle scheduled trigger metrics (fire count, latency)."""
        if metric_type == MetricType.SCHEDULED_TRIGGER_FIRES:
            p.scheduled_trigger_fires_total.labels(
                status=labels.get("status", "success"),
            ).inc()
        elif metric_type == MetricType.SCHEDULED_TRIGGER_LATENCY:
            p.scheduled_trigger_latency_seconds.observe(value / 1000)

    @staticmethod
    def _dispatch_authz(
        metric_type: MetricType,
        value: float,
        labels: dict[str, str],
        p: OrchestratorPrometheusMetrics,
    ) -> None:
        """Handle authorization metrics (authz duration, OPA request duration)."""
        resource_type = labels.get("resource_type", "unknown")
        action = labels.get("action", "unknown")

        if metric_type == MetricType.AUTHZ_DURATION:
            p.authz_duration_seconds.labels(
                resource_type=resource_type,
                action=action,
            ).observe(value / 1000)

        elif metric_type == MetricType.OPA_REQUEST_DURATION:
            p.opa_request_duration_seconds.labels(
                resource_type=resource_type,
                action=action,
            ).observe(value / 1000)

    @staticmethod
    def _dispatch_component(
        metric_type: MetricType,
        value: float,
        labels: dict[str, str],
        p: OrchestratorPrometheusMetrics,
    ) -> None:
        """Handle component-level metrics (API, workflow engine, tools, etc.)."""
        entry = _COMPONENT_METRIC_MAP.get(metric_type)
        if entry is None:
            return

        attr_name, action, extra_keys = entry
        component = labels.get("component", "unknown")
        extra_labels = {k: labels.get(k, "unknown") for k in extra_keys}
        instrument = getattr(p, attr_name).labels(component=component, **extra_labels)

        if action == "gauge":
            instrument.set(value)
        elif action == "histogram":
            instrument.observe(value / 1000)
        elif action == "counter":
            instrument.inc()
