"""Metric types, models, and query parameters for the metrics subsystem.

This module defines:
- MetricType: Enum categorizing all metric types recorded by Syntara
- MetricRecord: Lightweight in-memory metric data point (dataclass with slots)
- MetricsQuery: Query parameters for the metrics REST API
- MetricsSummary: Summary response model for quick health checks
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlmodel import Field as SQLField
from sqlmodel import SQLModel

from syntara.core.constants import ValidationMessages
from syntara.core.exceptions import SafeValueError
from syntara.core.models.base.query_params import BaseListParams


class MetricType(StrEnum):
    """Categories of metrics recorded by Syntara.

    Each value corresponds to a specific measurable quantity exposed via the
    metrics REST API and (where applicable) Prometheus endpoint.
    """

    # LLM Metrics (FR-005 to FR-010)
    LLM_DURATION = "llm_duration_ms"
    LLM_TOKENS_INPUT = "llm_tokens_input"
    LLM_TOKENS_OUTPUT = "llm_tokens_output"
    LLM_TTFT = "llm_ttft_ms"
    LLM_STATUS = "llm_status"

    # Cache Metrics (FR-011 to FR-013)
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    CACHE_LOOKUP_DURATION = "cache_lookup_ms"
    CACHE_UTILIZATION = "cache_utilization_ratio"

    # Workflow Metrics (FR-014 to FR-017)
    WORKFLOW_DURATION = "workflow_duration_ms"
    WORKFLOW_STATUS = "workflow_status"
    ACTIVITY_DURATION = "activity_duration_ms"

    # Agent Metrics (FR-018 to FR-020)
    AGENT_ROUTING_DURATION = "agent_routing_ms"
    AGENT_INVOCATION_DURATION = "agent_invocation_ms"
    AGENT_STATUS = "agent_status"

    # System Overhead Metrics (FR-021 to FR-023)
    REQUEST_DURATION = "request_duration_ms"
    CONTEXT_DURATION = "context_duration_ms"

    # Error Metrics (FR-024 to FR-025)
    ERROR = "error"

    # API Service Metrics
    API_RESPONSE_TIME = "api_response_time_ms"
    API_ERROR_RATE = "api_error_rate"
    API_THROUGHPUT = "api_throughput_rps"

    # Workflow Engine Metrics
    WORKFLOW_CREATION_SUCCESS_RATE = "workflow_creation_success_rate"
    WORKFLOW_SERIALIZATION_DURATION = "workflow_serialization_duration_ms"
    WORKFLOW_VALIDATION_DURATION = "workflow_validation_duration_ms"

    # Temporal Worker Metrics
    TEMPORAL_QUEUE_DEPTH = "temporal_queue_depth"
    ACTIVITY_EXECUTION_SUCCESS_RATE = "activity_execution_success_rate"

    # Execution Service Metrics
    WORKFLOW_START_LATENCY = "workflow_start_latency_ms"
    WORKFLOW_COMPLETION_RATE = "workflow_completion_rate"
    TEMPORAL_EXECUTION_SERVICE_DURATION = "temporal_execution_service_duration_ms"

    # Scheduled Trigger Metrics
    SCHEDULED_TRIGGER_FIRES = "scheduled_trigger_fires_total"
    SCHEDULED_TRIGGER_LATENCY = "scheduled_trigger_latency_ms"

    # Tool Metrics
    TOOL_EXECUTION_DURATION = "tool_execution_duration_ms"
    TOOL_EXECUTION_STATUS = "tool_execution_status"

    # Database Metrics
    DATABASE_QUERY_RESPONSE_TIME = "database_query_response_time_ms"
    DATABASE_CONNECTION_POOL_UTILIZATION = "database_connection_pool_utilization_ratio"
    DATABASE_TRANSACTION_RATE = "database_transaction_rate_tps"

    # System-Wide Metrics
    SYSTEM_UPTIME = "system_uptime_seconds"
    SYSTEM_E2E_LATENCY = "system_e2e_latency_ms"
    SYSTEM_ERROR_RATE = "system_error_rate"

    # Authentication Metrics
    AUTH_FAILURE = "auth_failure"

    # Authorization Metrics
    AUTHZ_DURATION = "authz_duration_ms"
    OPA_REQUEST_DURATION = "opa_request_duration_ms"


class MetricsCategoryType(StrEnum):
    """Metric category names used to group :class:`MetricType` members."""

    LLM = "llm"
    CACHE = "cache"
    WORKFLOW = "workflow"
    AGENT = "agent"
    ERROR = "error"
    SYSTEM_OVERHEAD = "system_overhead"
    API = "api"
    WORKFLOW_ENGINE = "workflow_engine"
    TEMPORAL_WORKER = "temporal_worker"
    EXECUTION_SERVICE = "execution_service"

    DATABASE = "database"
    TOOL = "tool"
    SYSTEM_WIDE = "system_wide"
    AUTHORIZATION = "authorization"


METRIC_CATEGORIES: dict[MetricsCategoryType, list[MetricType]] = {
    MetricsCategoryType.LLM: [
        MetricType.LLM_DURATION,
        MetricType.LLM_TOKENS_INPUT,
        MetricType.LLM_TOKENS_OUTPUT,
        MetricType.LLM_TTFT,
        MetricType.LLM_STATUS,
    ],
    MetricsCategoryType.CACHE: [
        MetricType.CACHE_HIT,
        MetricType.CACHE_MISS,
        MetricType.CACHE_LOOKUP_DURATION,
        MetricType.CACHE_UTILIZATION,
    ],
    MetricsCategoryType.WORKFLOW: [
        MetricType.WORKFLOW_DURATION,
        MetricType.WORKFLOW_STATUS,
        MetricType.ACTIVITY_DURATION,
    ],
    MetricsCategoryType.AGENT: [
        MetricType.AGENT_ROUTING_DURATION,
        MetricType.AGENT_INVOCATION_DURATION,
        MetricType.AGENT_STATUS,
    ],
    MetricsCategoryType.ERROR: [
        MetricType.ERROR,
        MetricType.AUTH_FAILURE,
    ],
    MetricsCategoryType.SYSTEM_OVERHEAD: [
        MetricType.REQUEST_DURATION,
        MetricType.CONTEXT_DURATION,
    ],
    MetricsCategoryType.API: [
        MetricType.API_RESPONSE_TIME,
        MetricType.API_ERROR_RATE,
        MetricType.API_THROUGHPUT,
    ],
    MetricsCategoryType.WORKFLOW_ENGINE: [
        MetricType.WORKFLOW_CREATION_SUCCESS_RATE,
        MetricType.WORKFLOW_SERIALIZATION_DURATION,
        MetricType.WORKFLOW_VALIDATION_DURATION,
        MetricType.WORKFLOW_DURATION,
        MetricType.WORKFLOW_STATUS,
    ],
    MetricsCategoryType.TEMPORAL_WORKER: [
        MetricType.TEMPORAL_QUEUE_DEPTH,
        MetricType.ACTIVITY_EXECUTION_SUCCESS_RATE,
        MetricType.ACTIVITY_DURATION,
    ],
    MetricsCategoryType.EXECUTION_SERVICE: [
        MetricType.WORKFLOW_START_LATENCY,
        MetricType.WORKFLOW_COMPLETION_RATE,
        MetricType.TEMPORAL_EXECUTION_SERVICE_DURATION,
        MetricType.SCHEDULED_TRIGGER_FIRES,
        MetricType.SCHEDULED_TRIGGER_LATENCY,
    ],
    MetricsCategoryType.TOOL: [
        MetricType.TOOL_EXECUTION_DURATION,
        MetricType.TOOL_EXECUTION_STATUS,
    ],
    MetricsCategoryType.DATABASE: [
        MetricType.DATABASE_QUERY_RESPONSE_TIME,
        MetricType.DATABASE_CONNECTION_POOL_UTILIZATION,
        MetricType.DATABASE_TRANSACTION_RATE,
    ],
    MetricsCategoryType.SYSTEM_WIDE: [
        MetricType.SYSTEM_UPTIME,
        MetricType.SYSTEM_E2E_LATENCY,
        MetricType.SYSTEM_ERROR_RATE,
    ],
    MetricsCategoryType.AUTHORIZATION: [
        MetricType.AUTHZ_DURATION,
        MetricType.OPA_REQUEST_DURATION,
    ],
}


class ComponentLabel(StrEnum):
    """Valid component identifiers used in the ``component`` metric label."""

    API_SERVICE = "api_service"
    WORKFLOW_ENGINE = "workflow_engine"
    TEMPORAL_WORKER = "temporal_worker"
    EXECUTION_SERVICE = "execution_service"
    INVOCATION_SERVICE = "invocation_service"
    ROUTING_SERVICE = "routing_service"
    TOOL_MANAGER = "tool_manager"
    DATABASE = "database"
    SYSTEM_WIDE = "system_wide"


class AuthFailureType(StrEnum):
    """Authentication failure categories for the ``auth_failures_total`` counter."""

    INVALID_TOKEN = "invalid_token"  # noqa: S105
    EXPIRED_TOKEN = "expired_token"  # noqa: S105
    MISSING_CREDENTIALS = "missing_credentials"
    GLOBALLY_REVOKED = "globally_revoked"
    REFRESH_REVOKED = "refresh_revoked"
    CSRF_FAILED = "csrf_failed"
    DISABLED_USER = "disabled_user"
    STALE_TOKEN = "stale_token"  # noqa: S105
    DISABLED_SA = "disabled_sa"
    REVOKED_SA_TOKEN = "revoked_sa_token"  # noqa: S105


def _validate_labels(labels: dict[str, str] | None) -> dict[str, str]:
    """Validate that labels dictionary contains only string key-value pairs."""
    if labels is None:
        return {}

    if not isinstance(labels, dict):
        raise SafeValueError(ValidationMessages.LABELS_MUST_BE_DICT)

    for key, value in labels.items():
        if not isinstance(key, str):
            msg = ValidationMessages.LABELS_KEY_MUST_BE_STRING.format(key=key, type_name=type(key).__name__)  # type: ignore[unreachable]
            raise SafeValueError(msg)
        if not isinstance(value, str):
            msg = ValidationMessages.LABELS_VALUE_MUST_BE_STRING.format(key=key, type_name=type(value).__name__)  # type: ignore[unreachable]
            raise SafeValueError(msg)

    return labels


@dataclass(slots=True)
class MetricRecord:
    """Lightweight in-memory metric data point.

    Uses a slotted dataclass instead of SQLModel to reduce per-instance
    memory from ~4.1KB to ~72 bytes.  This record never touches a database.
    """

    metric_type: MetricType
    value: float
    unit: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Validate labels after dataclass initialisation."""
        self.labels = _validate_labels(self.labels)


class MetricsQuery(BaseListParams):
    """Query parameters for the metrics REST API with cursor-based pagination.

    Extends BaseListParams to inherit standard pagination parameters
    (limit, cursor, sort, include_total) and adds metrics-specific filters.
    """

    category: MetricsCategoryType | None = SQLField(
        default=None,
        description="Filter by metric category",
    )

    metric_type: str | None = SQLField(
        default=None,
        description="Filter by specific metric type value (e.g. api_response_time_ms)",
    )

    start_time: datetime | None = SQLField(
        default=None,
        description="Start of time range (ISO 8601)",
    )

    end_time: datetime | None = SQLField(
        default=None,
        description="End of time range (ISO 8601)",
    )

    labels: str | None = SQLField(
        default=None,
        description='Label filter as JSON string (e.g. {"component": "api_service"})',
    )


class MetricsSummary(SQLModel):
    """Quick summary of metric counts for the /api/v1/metrics/summary endpoint."""

    total_requests: int = SQLField(default=0, description="Total requests recorded")
    total_errors: int = SQLField(default=0, description="Total errors recorded")
    cache_hits: int = SQLField(default=0, description="Cache hit count")
    cache_misses: int = SQLField(default=0, description="Cache miss count")
    llm_calls: int = SQLField(default=0, description="Total LLM API calls")
    total_workflows: int = SQLField(default=0, description="Total workflow executions started")
    active_workflows: int = SQLField(default=0, description="Currently active workflows")
    active_llm_requests: int = SQLField(default=0, description="Currently in-flight LLM requests")
    db_transactions: int = SQLField(default=0, description="Total database transactions committed")
    period_start: datetime = SQLField(..., description="Start of metrics retention period")
    period_end: datetime = SQLField(..., description="End of metrics period (now)")

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate (0.0 to 1.0)."""
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0

    @property
    def error_rate(self) -> float:
        """Calculate error rate (0.0 to 1.0)."""
        return self.total_errors / self.total_requests if self.total_requests > 0 else 0.0
