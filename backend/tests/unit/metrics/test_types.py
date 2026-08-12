"""Unit tests for metric types, MetricRecord dataclass, and MetricsSummary."""

from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

import pytest

from syntara.core.exceptions import SafeValueError
from syntara.metrics.types import (
    METRIC_CATEGORIES,
    AuthFailureType,
    ComponentLabel,
    MetricRecord,
    MetricsCategoryType,
    MetricsQuery,
    MetricsSummary,
    MetricType,
)

# =============================================================================
# MetricType enum tests
# =============================================================================


class TestMetricType:
    """Tests for the MetricType enum."""

    def test_metric_type_values_exist(self) -> None:
        """All expected metric types are defined."""
        expected = {
            # LLM
            "LLM_DURATION",
            "LLM_TOKENS_INPUT",
            "LLM_TOKENS_OUTPUT",
            "LLM_TTFT",
            "LLM_STATUS",
            # Cache
            "CACHE_HIT",
            "CACHE_MISS",
            "CACHE_LOOKUP_DURATION",
            "CACHE_UTILIZATION",
            # Workflow
            "WORKFLOW_DURATION",
            "WORKFLOW_STATUS",
            "ACTIVITY_DURATION",
            # Agent
            "AGENT_ROUTING_DURATION",
            "AGENT_INVOCATION_DURATION",
            "AGENT_STATUS",
            # System Overhead
            "REQUEST_DURATION",
            "CONTEXT_DURATION",
            # Error
            "ERROR",
            "AUTH_FAILURE",
            # API Service
            "API_RESPONSE_TIME",
            "API_ERROR_RATE",
            "API_THROUGHPUT",
            # Workflow Engine
            "WORKFLOW_CREATION_SUCCESS_RATE",
            "WORKFLOW_SERIALIZATION_DURATION",
            "WORKFLOW_VALIDATION_DURATION",
            # Temporal Worker
            "TEMPORAL_QUEUE_DEPTH",
            "ACTIVITY_EXECUTION_SUCCESS_RATE",
            # Execution Service
            "WORKFLOW_START_LATENCY",
            "WORKFLOW_COMPLETION_RATE",
            "TEMPORAL_EXECUTION_SERVICE_DURATION",
            # Scheduled Trigger
            "SCHEDULED_TRIGGER_FIRES",
            "SCHEDULED_TRIGGER_LATENCY",
            # Tool Metrics
            "TOOL_EXECUTION_DURATION",
            "TOOL_EXECUTION_STATUS",
            # Database
            "DATABASE_QUERY_RESPONSE_TIME",
            "DATABASE_CONNECTION_POOL_UTILIZATION",
            "DATABASE_TRANSACTION_RATE",
            # System-Wide
            "SYSTEM_UPTIME",
            "SYSTEM_E2E_LATENCY",
            "SYSTEM_ERROR_RATE",
            # Authorization
            "AUTHZ_DURATION",
            "OPA_REQUEST_DURATION",
        }
        actual = {m.name for m in MetricType}
        assert actual == expected

    def test_metric_type_is_string_enum(self) -> None:
        """MetricType values are usable as plain strings."""
        assert MetricType.LLM_DURATION.value == "llm_duration_ms"
        assert isinstance(MetricType.LLM_DURATION, str)

    def test_metric_type_from_value(self) -> None:
        """MetricType can be constructed from its string value."""
        assert MetricType("llm_duration_ms") is MetricType.LLM_DURATION
        assert MetricType("api_response_time_ms") is MetricType.API_RESPONSE_TIME
        assert MetricType("system_uptime_seconds") is MetricType.SYSTEM_UPTIME

    def test_tool_execution_status_exists(self) -> None:
        """TOOL_EXECUTION_STATUS enum member exists with correct value."""
        assert MetricType.TOOL_EXECUTION_STATUS.value == "tool_execution_status"

    def test_tool_category_type_exists(self) -> None:
        """MetricsCategoryType.TOOL exists with correct value."""
        assert MetricsCategoryType.TOOL.value == "tool"

    def test_tool_category_contains_both_metric_types(self) -> None:
        """METRIC_CATEGORIES[TOOL] contains both TOOL_EXECUTION_DURATION and TOOL_EXECUTION_STATUS."""
        tool_types = METRIC_CATEGORIES[MetricsCategoryType.TOOL]
        assert MetricType.TOOL_EXECUTION_DURATION in tool_types
        assert MetricType.TOOL_EXECUTION_STATUS in tool_types

    def test_metric_categories_keys(self) -> None:
        """All expected categories are present."""
        expected_categories = {
            "llm",
            "cache",
            "workflow",
            "agent",
            "error",
            "system_overhead",
            "api",
            "workflow_engine",
            "temporal_worker",
            "execution_service",
            "tool",
            "database",
            "system_wide",
            "authorization",
        }
        assert set(METRIC_CATEGORIES.keys()) == expected_categories

    def test_metric_categories_contain_correct_types(self) -> None:
        """Each category contains the right MetricType members including cross-refs."""
        assert MetricType.LLM_DURATION in METRIC_CATEGORIES[MetricsCategoryType.LLM]
        assert MetricType.CACHE_HIT in METRIC_CATEGORIES[MetricsCategoryType.CACHE]
        assert MetricType.WORKFLOW_DURATION in METRIC_CATEGORIES[MetricsCategoryType.WORKFLOW]
        assert MetricType.AGENT_ROUTING_DURATION in METRIC_CATEGORIES[MetricsCategoryType.AGENT]
        assert MetricType.ERROR in METRIC_CATEGORIES[MetricsCategoryType.ERROR]
        assert MetricType.API_RESPONSE_TIME in METRIC_CATEGORIES[MetricsCategoryType.API]
        assert MetricType.TOOL_EXECUTION_DURATION in METRIC_CATEGORIES[MetricsCategoryType.TOOL]
        assert MetricType.DATABASE_QUERY_RESPONSE_TIME in METRIC_CATEGORIES[MetricsCategoryType.DATABASE]
        assert MetricType.SYSTEM_UPTIME in METRIC_CATEGORIES[MetricsCategoryType.SYSTEM_WIDE]
        assert MetricType.WORKFLOW_DURATION in METRIC_CATEGORIES[MetricsCategoryType.WORKFLOW_ENGINE]
        assert MetricType.ACTIVITY_DURATION in METRIC_CATEGORIES[MetricsCategoryType.TEMPORAL_WORKER]
        assert MetricType.REQUEST_DURATION in METRIC_CATEGORIES[MetricsCategoryType.SYSTEM_OVERHEAD]
        assert MetricType.CONTEXT_DURATION in METRIC_CATEGORIES[MetricsCategoryType.SYSTEM_OVERHEAD]

    def test_all_metric_types_belong_to_a_category(self) -> None:
        """Every MetricType is listed in at least one category."""
        categorized = {mt for types in METRIC_CATEGORIES.values() for mt in types}
        uncategorized = set(MetricType) - categorized
        assert uncategorized == set()


# =============================================================================
# AuthFailureType enum tests
# =============================================================================


class TestAuthFailureType:
    """Tests for the AuthFailureType enum."""

    def test_auth_failure_type_values_exist(self) -> None:
        """All expected auth failure types are defined with correct string values."""
        expected = {
            "invalid_token",
            "expired_token",
            "missing_credentials",
            "globally_revoked",
            "refresh_revoked",
            "csrf_failed",
            "disabled_user",
            "stale_token",
            "disabled_sa",
            "revoked_sa_token",
        }
        assert {m.value for m in AuthFailureType} == expected

    def test_auth_failure_type_is_string_enum(self) -> None:
        """AuthFailureType values are usable as plain strings."""
        assert AuthFailureType.INVALID_TOKEN.value == "invalid_token"
        assert isinstance(AuthFailureType.INVALID_TOKEN, str)


# =============================================================================
# ComponentLabel tests
# =============================================================================


class TestComponentLabel:
    """Tests for the ComponentLabel enum."""

    def test_component_label_is_string_enum(self) -> None:
        """ComponentLabel values are usable as plain strings."""
        assert ComponentLabel.API_SERVICE.value == "api_service"
        assert isinstance(ComponentLabel.API_SERVICE, str)


# =============================================================================
# MetricRecord model tests
# =============================================================================


class TestMetricRecord:
    """Tests for the MetricRecord slotted dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """MetricRecord can be created with just metric_type and value."""
        record = MetricRecord(metric_type=MetricType.LLM_DURATION, value=123.45)
        assert record.metric_type == MetricType.LLM_DURATION
        assert record.value == pytest.approx(123.45)
        assert record.unit == ""
        assert record.labels == {}

    def test_auto_generated_id(self) -> None:
        """Each record gets a unique UUID."""
        r1 = MetricRecord(metric_type=MetricType.LLM_DURATION, value=1.0)
        r2 = MetricRecord(metric_type=MetricType.LLM_DURATION, value=2.0)
        assert isinstance(r1.id, UUID)
        assert r1.id != r2.id

    def test_auto_generated_created_at(self) -> None:
        """created_at is auto-populated with a recent UTC timestamp."""
        record = MetricRecord(metric_type=MetricType.LLM_DURATION, value=1.0)
        assert record.created_at is not None
        assert record.created_at.tzinfo is not None
        delta = datetime.now(UTC) - record.created_at
        assert delta.total_seconds() < 2

    def test_labels_stored_correctly(self) -> None:
        """Labels dict is preserved through construction."""
        labels = {"model": "gpt-4", "status": "success"}
        record = MetricRecord(
            metric_type=MetricType.LLM_DURATION,
            value=100.0,
            labels=labels,
        )
        assert record.labels == labels

    def test_unit_field(self) -> None:
        """Unit field is stored correctly."""
        record = MetricRecord(
            metric_type=MetricType.LLM_TOKENS_INPUT,
            value=1500,
            unit="tokens",
        )
        assert record.unit == "tokens"

    def test_serialization_roundtrip(self) -> None:
        """Asdict produces a dict that can recreate the record."""
        original = MetricRecord(
            metric_type=MetricType.LLM_DURATION,
            value=245.5,
            unit="ms",
            labels={"model": "gpt-4"},
        )
        data = asdict(original)
        restored = MetricRecord(**data)
        assert restored.metric_type == original.metric_type
        assert restored.value == original.value
        assert restored.unit == original.unit
        assert restored.labels == original.labels

    def test_labels_none_defaults_to_empty_dict(self) -> None:
        """Passing None for labels yields an empty dict."""
        record = MetricRecord(
            metric_type=MetricType.LLM_DURATION,
            value=1.0,
            labels=None,  # type: ignore[arg-type]
        )
        assert record.labels == {}

    def test_labels_rejects_non_string_keys(self) -> None:
        """Labels with non-string keys are rejected."""
        with pytest.raises(SafeValueError, match="labels key '1' must be a string, got int"):
            MetricRecord(
                metric_type=MetricType.LLM_DURATION,
                value=1.0,
                labels={1: 123},  # type: ignore[dict-item]
            )

    def test_labels_rejects_non_string_values(self) -> None:
        """Labels with non-string values are rejected."""
        with pytest.raises(SafeValueError, match="labels value for key 'key' must be a string, got int"):
            MetricRecord(
                metric_type=MetricType.LLM_DURATION,
                value=1.0,
                labels={"key": 123},  # type: ignore[dict-item]
            )

    def test_extra_fields_rejected(self) -> None:
        """Unknown keyword arguments are rejected by the slotted dataclass."""
        with pytest.raises(TypeError):
            MetricRecord(
                metric_type=MetricType.LLM_DURATION,
                value=1.0,
                unknown_field="bad",  # type: ignore[call-arg]
            )

    def test_slots_are_defined(self) -> None:
        """MetricRecord uses __slots__ for memory efficiency."""
        assert hasattr(MetricRecord, "__slots__")


# =============================================================================
# MetricsQuery tests
# =============================================================================


class TestMetricsQuery:
    """Tests for the MetricsQuery parameter model."""

    def test_defaults(self) -> None:
        """Default values match spec expectations."""
        query = MetricsQuery()
        assert query.category is None
        assert query.metric_type is None
        assert query.start_time is None
        assert query.end_time is None
        assert query.labels is None
        assert query.limit == 20
        assert query.cursor is None
        assert query.sort is None
        assert query.include_total is False

    def test_custom_values(self) -> None:
        """Custom filter values are accepted."""
        now = datetime.now(UTC)
        query = MetricsQuery(category="llm", start_time=now, limit=50)
        assert query.category == "llm"
        assert query.start_time == now
        assert query.limit == 50

    def test_custom_values_with_component_filters(self) -> None:
        """Fields work together with a component category."""
        now = datetime.now(UTC)
        query = MetricsQuery(
            category="api",
            metric_type="api_response_time_ms",
            start_time=now,
            labels='{"component": "api_service"}',
            limit=50,
        )
        assert query.category == "api"
        assert query.metric_type == "api_response_time_ms"
        assert query.start_time == now
        assert query.labels == '{"component": "api_service"}'
        assert query.limit == 50

    def test_component_category_accepted(self) -> None:
        """Component categories are valid category values."""
        for cat in (
            "api",
            "workflow_engine",
            "temporal_worker",
            "execution_service",
            "database",
            "system_wide",
        ):
            query = MetricsQuery(category=cat)
            assert query.category == cat

    def test_metric_type_takes_precedence_over_category(self) -> None:
        """When both metric_type and category are given, metric_type wins."""
        query = MetricsQuery(
            category="api",
            metric_type="api_error_rate",
        )
        assert query.metric_type == "api_error_rate"
        assert query.category == "api"


# =============================================================================
# MetricsSummary tests
# =============================================================================


class TestMetricsSummary:
    """Tests for the MetricsSummary response model."""

    def test_cache_hit_rate_with_data(self) -> None:
        """Cache hit rate is computed correctly."""
        now = datetime.now(UTC)
        summary = MetricsSummary(
            cache_hits=7,
            cache_misses=3,
            period_start=now,
            period_end=now,
        )
        assert summary.cache_hit_rate == pytest.approx(0.7)

    def test_cache_hit_rate_no_data(self) -> None:
        """Cache hit rate is 0.0 when no cache operations recorded."""
        now = datetime.now(UTC)
        summary = MetricsSummary(period_start=now, period_end=now)
        assert summary.cache_hit_rate == pytest.approx(0.0)

    def test_error_rate_with_data(self) -> None:
        """Error rate is computed correctly."""
        now = datetime.now(UTC)
        summary = MetricsSummary(
            total_requests=100,
            total_errors=5,
            period_start=now,
            period_end=now,
        )
        assert summary.error_rate == pytest.approx(0.05)

    def test_error_rate_no_data(self) -> None:
        """Error rate is 0.0 when no requests recorded."""
        now = datetime.now(UTC)
        summary = MetricsSummary(period_start=now, period_end=now)
        assert summary.error_rate == pytest.approx(0.0)
