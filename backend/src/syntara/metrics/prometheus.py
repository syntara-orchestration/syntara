"""Prometheus metric definitions for the Syntara metrics subsystem.

All Prometheus counters, histograms, and gauges required by FR-026 through
FR-029 are encapsulated in :class:`OrchestratorPrometheusMetrics` so that each test
(or service instance) can operate on an isolated registry.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, disable_created_metrics

disable_created_metrics()  # type: ignore[no-untyped-call]

# Histogram bucket boundaries tuned to different latency profiles.
LATENCY_BUCKETS_FAST: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    0.5,
    0.75,
    1.0,
)
LATENCY_BUCKETS_MEDIUM: tuple[float, ...] = (
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    7.5,
    10.0,
)
LATENCY_BUCKETS_SLOW: tuple[float, ...] = (
    1.0,
    5.0,
    10.0,
    30.0,
    60.0,
    120.0,
    300.0,
)


class OrchestratorPrometheusMetrics:
    """Container for all Syntara Prometheus metrics bound to a single registry.

    Using an explicit registry (rather than the global default) makes tests
    deterministic and avoids metric-name collisions across test runs.

    Args:
        registry: A ``CollectorRegistry`` to register metrics against.
            When *None*, a fresh private registry is created.

    """

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        """Initialise metrics and bind them to *registry*."""
        self.registry = registry or CollectorRegistry()

        # ---- Counters (FR-027) ----
        self.requests_total = Counter(
            "orchestrator_requests_total",
            "Total number of requests processed",
            ["status", "endpoint", "interface"],
            registry=self.registry,
        )

        self.errors_total = Counter(
            "orchestrator_errors_total",
            "Total number of errors by type",
            ["error_type", "interface"],
            registry=self.registry,
        )

        self.auth_failures_total = Counter(
            "orchestrator_auth_failures_total",
            "Total authentication failures by type and interface",
            ["failure_type", "interface"],
            registry=self.registry,
        )

        self.cache_hits_total = Counter(
            "orchestrator_cache_hits_total",
            "Total cache hits",
            registry=self.registry,
        )

        self.cache_misses_total = Counter(
            "orchestrator_cache_misses_total",
            "Total cache misses",
            registry=self.registry,
        )

        self.llm_calls_total = Counter(
            "orchestrator_llm_calls_total",
            "Total LLM API calls",
            ["model", "status"],
            registry=self.registry,
        )

        self.workflows_total = Counter(
            "orchestrator_workflows_total",
            "Total workflow executions started",
            ["workflow_type"],
            registry=self.registry,
        )

        # ---- Histograms (FR-028) ----
        self.request_duration_seconds = Histogram(
            "orchestrator_request_duration_seconds",
            "Request duration in seconds",
            ["endpoint", "method", "interface"],
            buckets=LATENCY_BUCKETS_MEDIUM,
            registry=self.registry,
        )

        self.llm_duration_seconds = Histogram(
            "orchestrator_llm_duration_seconds",
            "LLM API call duration in seconds",
            ["model"],
            buckets=LATENCY_BUCKETS_MEDIUM,
            registry=self.registry,
        )

        self.ttft_seconds = Histogram(
            "orchestrator_ttft_seconds",
            "Time To First Token in seconds",
            ["model"],
            buckets=LATENCY_BUCKETS_FAST,
            registry=self.registry,
        )

        self.cache_lookup_duration_seconds = Histogram(
            "orchestrator_cache_lookup_duration_seconds",
            "Cache lookup duration in seconds",
            buckets=LATENCY_BUCKETS_FAST,
            registry=self.registry,
        )

        self.workflow_duration_seconds = Histogram(
            "orchestrator_workflow_duration_seconds",
            "Workflow execution duration in seconds",
            buckets=LATENCY_BUCKETS_SLOW,
            registry=self.registry,
        )

        self.activity_duration_seconds = Histogram(
            "orchestrator_activity_duration_seconds",
            "Activity execution duration in seconds",
            ["activity_name", "status", "workflow_type"],
            buckets=LATENCY_BUCKETS_MEDIUM,
            registry=self.registry,
        )

        # ---- Gauges (FR-029) ----
        self.cache_utilization_ratio = Gauge(
            "orchestrator_cache_utilization_ratio",
            "Current cache utilization (0.0 to 1.0)",
            registry=self.registry,
        )

        self.active_workflows = Gauge(
            "orchestrator_active_workflows",
            "Number of currently active workflows",
            registry=self.registry,
        )

        self.active_llm_requests = Gauge(
            "orchestrator_active_llm_requests",
            "Number of in-flight LLM requests",
            registry=self.registry,
        )

        # ---- LLM Token Counters (FR-006 to FR-008) ----
        self.llm_tokens_input_total = Counter(
            "orchestrator_llm_tokens_input_total",
            "Total input tokens sent to LLM",
            ["model"],
            registry=self.registry,
        )

        self.llm_tokens_output_total = Counter(
            "orchestrator_llm_tokens_output_total",
            "Total output tokens received from LLM",
            ["model"],
            registry=self.registry,
        )

        # ---- Component Histograms ----
        self.api_response_time_seconds = Histogram(
            "orchestrator_api_response_time_seconds",
            "API response time in seconds",
            ["component", "endpoint", "method"],
            buckets=LATENCY_BUCKETS_MEDIUM,
            registry=self.registry,
        )

        self.workflow_serialization_duration_seconds = Histogram(
            "orchestrator_workflow_serialization_duration_seconds",
            "Workflow serialization duration in seconds",
            ["component"],
            buckets=LATENCY_BUCKETS_MEDIUM,
            registry=self.registry,
        )

        self.workflow_validation_duration_seconds = Histogram(
            "orchestrator_workflow_validation_duration_seconds",
            "Workflow validation duration in seconds",
            ["component"],
            buckets=LATENCY_BUCKETS_MEDIUM,
            registry=self.registry,
        )

        self.workflow_start_latency_seconds = Histogram(
            "orchestrator_workflow_start_latency_seconds",
            "Workflow start latency in seconds",
            ["component"],
            buckets=LATENCY_BUCKETS_MEDIUM,
            registry=self.registry,
        )

        self.temporal_execution_service_duration_seconds = Histogram(
            "orchestrator_temporal_execution_service_duration_seconds",
            "Temporal client start_workflow RPC duration including network and server startup",
            ["component"],
            buckets=LATENCY_BUCKETS_MEDIUM,
            registry=self.registry,
        )

        self.tool_execution_duration_seconds = Histogram(
            "orchestrator_tool_execution_duration_seconds",
            "Tool execution duration in seconds",
            ["namespaced_name"],
            buckets=LATENCY_BUCKETS_MEDIUM,
            registry=self.registry,
        )

        self.database_query_response_time_seconds = Histogram(
            "orchestrator_database_query_response_time_seconds",
            "Database query response time in seconds",
            ["component", "statement_type"],
            buckets=LATENCY_BUCKETS_MEDIUM,
            registry=self.registry,
        )

        self.system_e2e_latency_seconds = Histogram(
            "orchestrator_system_e2e_latency_seconds",
            "System end-to-end latency in seconds",
            ["component"],
            buckets=LATENCY_BUCKETS_SLOW,
            registry=self.registry,
        )

        self.context_duration_seconds = Histogram(
            "orchestrator_context_duration_seconds",
            "Context preparation overhead duration in seconds",
            buckets=LATENCY_BUCKETS_FAST,
            registry=self.registry,
        )

        # ---- Authorization Histograms ----
        self.authz_duration_seconds = Histogram(
            "orchestrator_authz_duration_seconds",
            "Authorization check duration including OPA evaluation in seconds",
            ["resource_type", "action"],
            buckets=LATENCY_BUCKETS_FAST,
            registry=self.registry,
        )

        self.opa_request_duration_seconds = Histogram(
            "orchestrator_opa_request_duration_seconds",
            "OPA policy evaluation HTTP round trip duration in seconds",
            ["resource_type", "action"],
            buckets=LATENCY_BUCKETS_FAST,
            registry=self.registry,
        )

        # ---- Scheduled Trigger ----
        self.scheduled_trigger_fires_total = Counter(
            "orchestrator_scheduled_trigger_fires_total",
            "Total scheduled trigger executions",
            ["status"],
            registry=self.registry,
        )

        self.scheduled_trigger_latency_seconds = Histogram(
            "orchestrator_scheduled_trigger_latency_seconds",
            "Latency between scheduled fire time and actual execution start",
            [],
            buckets=LATENCY_BUCKETS_MEDIUM,
            registry=self.registry,
        )

        # ---- Component Counters ----
        self.tool_executions_total = Counter(
            "orchestrator_tool_executions_total",
            "Total tool executions",
            ["namespaced_name", "status", "error_code"],
            registry=self.registry,
        )

        # ---- Component Gauges ----
        self.api_error_rate = Gauge(
            "orchestrator_api_error_rate",
            "API error rate",
            ["component"],
            registry=self.registry,
        )

        self.api_throughput_rps = Gauge(
            "orchestrator_api_throughput_rps",
            "API throughput in requests per second",
            ["component"],
            registry=self.registry,
        )

        self.workflow_creation_success_rate = Gauge(
            "orchestrator_workflow_creation_success_rate",
            "Workflow creation success rate",
            ["component"],
            registry=self.registry,
        )

        self.workflow_completion_rate = Gauge(
            "orchestrator_workflow_completion_rate",
            "Workflow completion rate",
            ["component"],
            registry=self.registry,
        )

        self.temporal_queue_depth = Gauge(
            "orchestrator_temporal_queue_depth",
            "Temporal task queue depth",
            ["component", "task_queue"],
            registry=self.registry,
        )

        self.activity_execution_success_rate = Gauge(
            "orchestrator_activity_execution_success_rate",
            "Activity execution success rate",
            ["component"],
            registry=self.registry,
        )

        self.database_connection_pool_utilization = Gauge(
            "orchestrator_database_connection_pool_utilization",
            "Database connection pool utilization ratio",
            ["component"],
            registry=self.registry,
        )

        self.database_transaction_rate_tps = Gauge(
            "orchestrator_database_transaction_rate_tps",
            "Database transaction rate in transactions per second",
            ["component"],
            registry=self.registry,
        )

        self.system_uptime = Gauge(
            "orchestrator_system_uptime",
            "System uptime in seconds",
            ["component"],
            registry=self.registry,
        )

        self.system_error_rate = Gauge(
            "orchestrator_system_error_rate",
            "System-wide error rate",
            ["component"],
            registry=self.registry,
        )
