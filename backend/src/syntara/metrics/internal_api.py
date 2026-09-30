"""Internal metrics store API for performance testing.

These endpoints expose raw in-memory metrics from the MetricsStore for use
by external performance-test harnesses.

Security model:
    * ``include_in_schema=False`` keeps them out of ``/api_docs/v1/docs`` and
      ``/api_docs/v1/openapi.json``.
    * Each handler checks the ``metrics.perf_test_mode`` runtime setting
      and returns 404 when disabled.  Toggling the setting enables the
      endpoints (and the backing in-memory store) without a restart.
"""

import json
import statistics
from datetime import UTC, datetime
from typing import Annotated, Any, ClassVar

import structlog
from fastapi import Depends, HTTPException, Query, status
from pydantic import ConfigDict
from sqlmodel import Field, SQLModel

from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.emission import reset_emission_trackers
from syntara.metrics.recorder import MetricsRecorder
from syntara.metrics.types import (
    METRIC_CATEGORIES,
    MetricRecord,
    MetricsCategoryType,
    MetricsSummary,
    MetricType,
)
from syntara.settings.cache.settings_cache import get_runtime_settings

logger = structlog.stdlib.get_logger(__name__)

_SETTING_KEY = "metrics.perf_test_mode"


async def _guard(recorder: MetricsRecorder) -> None:
    """Check runtime setting and sync the recorder's in-memory store flag.

    When the setting transitions from enabled to disabled the in-memory
    store is flushed so stale data doesn't linger after a debugging session.

    Raises 404 when perf-test mode is disabled.
    """
    cache = get_runtime_settings()
    enabled = await cache.get_bool(_SETTING_KEY, default=False)

    was_enabled = recorder.store_enabled
    recorder.store_enabled = enabled

    if not enabled:
        if was_enabled:
            recorder.store.clear()
            with recorder._counters_lock:  # noqa: SLF001
                recorder._counters.clear()  # noqa: SLF001
            reset_emission_trackers()
            logger.info("perf_test_mode disabled — in-memory metrics store flushed")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not Found",
        )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class PercentileStats(SQLModel):
    """Percentile breakdown for a collection of values."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]

    count: int = Field(description="Number of observations")
    min: float = Field(description="Minimum value")
    max: float = Field(description="Maximum value")
    mean: float = Field(description="Arithmetic mean")
    median: float = Field(description="50th percentile (p50)")
    p90: float = Field(description="90th percentile")
    p95: float = Field(description="95th percentile")
    p99: float = Field(description="99th percentile")
    sum: float = Field(description="Sum of all values")


class ComponentKPISummary(SQLModel):
    """KPI summary for a single Syntara component."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]

    component: str = Field(description="Component identifier")
    metrics: dict[str, PercentileStats | dict[str, int] | float | int] = Field(
        default_factory=dict,
        description="Metric name → stats, scalar value, or distribution map",
    )


class MetricsStoreSummary(SQLModel):
    """High-level summary of the in-memory metrics store."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]

    total_records: int = Field(description="Total records currently stored")
    retention_seconds: int = Field(description="Configured retention in seconds")
    max_records: int = Field(description="Configured capacity limit")
    counters: dict[str, int] = Field(
        default_factory=dict,
        description="Internal named counters (requests, errors, cache_hits, …)",
    )
    metric_type_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Record count per MetricType",
    )
    oldest_record_at: datetime | None = Field(
        default=None,
        description="Timestamp of the oldest stored record",
    )
    newest_record_at: datetime | None = Field(
        default=None,
        description="Timestamp of the newest stored record",
    )


class MetricsRecordPage(SQLModel):
    """Paginated list of raw metric records."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]

    records: list[MetricRecord] = Field(default_factory=list)
    total: int = Field(description="Total matching records (before pagination)")
    limit: int = Field(description="Page size used")
    offset: int = Field(description="Offset used")


class KPIDashboard(SQLModel):
    """Full KPI dashboard covering all Syntara components."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]

    generated_at: datetime = Field(description="Timestamp of generation")
    components: list[ComponentKPISummary] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _percentile_stats(values: list[float]) -> PercentileStats:
    """Compute percentile statistics for a list of numeric values."""
    if not values:
        return PercentileStats(
            count=0,
            min=0,
            max=0,
            mean=0,
            median=0,
            p90=0,
            p95=0,
            p99=0,
            sum=0,
        )
    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def _pct(p: float) -> float:
        k = (n - 1) * (p / 100)
        f = int(k)
        c = f + 1
        if c >= n:
            return sorted_vals[-1]
        return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])

    return PercentileStats(
        count=n,
        min=sorted_vals[0],
        max=sorted_vals[-1],
        mean=statistics.mean(sorted_vals),
        median=statistics.median(sorted_vals),
        p90=_pct(90),
        p95=_pct(95),
        p99=_pct(99),
        sum=sum(sorted_vals),
    )


def _collect_values(
    recorder: MetricsRecorder,
    metric_types: set[MetricType],
    *,
    labels: dict[str, str] | None = None,
) -> list[float]:
    return [r.value for r in recorder.query(metric_types=metric_types, labels=labels)]


def _rate_from_status(
    recorder: MetricsRecorder,
    metric_type: MetricType,
    success_statuses: set[str],
    *,
    dedup_key: str | None = None,
) -> float:
    """Compute success-rate (0.0-1.0) from status labels on records.

    When *dedup_key* is provided, records are grouped by that label and
    only the latest record per group is considered.  This prevents
    multi-phase metric types (e.g. ``WORKFLOW_STATUS`` which emits both
    a "started" and a terminal record per execution) from inflating the
    denominator.
    """
    records = list(recorder.query(metric_types={metric_type}))
    if not records:
        return 0.0

    if dedup_key:
        latest: dict[str, MetricRecord] = {}
        for r in records:
            key = r.labels.get(dedup_key, "")
            if key not in latest or r.created_at > latest[key].created_at:
                latest[key] = r
        records = list(latest.values())

    successes = sum(1 for r in records if r.labels.get("status") in success_statuses)
    return successes / len(records)


# ---------------------------------------------------------------------------
# KPI builder — maps the two KPI PDFs to MetricType queries
# ---------------------------------------------------------------------------

_MetricsDict = dict[str, PercentileStats | dict[str, int] | float | int]


def _label_distribution(
    recorder: MetricsRecorder,
    metric_type: MetricType,
    label_key: str,
) -> dict[str, int]:
    """Count occurrences of each distinct value for *label_key*."""
    dist: dict[str, int] = {}
    for r in recorder.query(metric_types={metric_type}):
        val = r.labels.get(label_key, "unknown")
        dist[val] = dist.get(val, 0) + 1
    return dist


def _build_api_service(recorder: MetricsRecorder, summary: MetricsSummary) -> ComponentKPISummary:
    m: _MetricsDict = {}
    m["response_time_ms"] = _percentile_stats(_collect_values(recorder, {MetricType.REQUEST_DURATION}))
    m["error_rate"] = summary.error_rate
    m["total_requests"] = summary.total_requests
    m["total_errors"] = summary.total_errors
    return ComponentKPISummary(component="api_service", metrics=m)


def _build_workflow_engine(recorder: MetricsRecorder) -> ComponentKPISummary:
    m: _MetricsDict = {}
    m["creation_success_rate"] = _rate_from_status(
        recorder,
        MetricType.WORKFLOW_STATUS,
        {"completed", "running"},
        dedup_key="execution_id",
    )
    m["serialization_duration_ms"] = _percentile_stats(
        _collect_values(recorder, {MetricType.WORKFLOW_SERIALIZATION_DURATION}),
    )
    m["validation_duration_ms"] = _percentile_stats(
        _collect_values(recorder, {MetricType.WORKFLOW_VALIDATION_DURATION}),
    )
    m["workflow_duration_ms"] = _percentile_stats(_collect_values(recorder, {MetricType.WORKFLOW_DURATION}))
    return ComponentKPISummary(component="workflow_engine", metrics=m)


def _build_temporal_worker(recorder: MetricsRecorder) -> ComponentKPISummary:
    m: _MetricsDict = {}
    m["queue_depth"] = _percentile_stats(_collect_values(recorder, {MetricType.TEMPORAL_QUEUE_DEPTH}))
    m["activity_success_rate"] = _rate_from_status(recorder, MetricType.ACTIVITY_DURATION, {"completed"})
    m["activity_duration_ms"] = _percentile_stats(_collect_values(recorder, {MetricType.ACTIVITY_DURATION}))
    return ComponentKPISummary(component="temporal_worker", metrics=m)


def _build_execution_service(recorder: MetricsRecorder, summary: MetricsSummary) -> ComponentKPISummary:
    m: _MetricsDict = {}
    m["start_latency_ms"] = _percentile_stats(_collect_values(recorder, {MetricType.WORKFLOW_START_LATENCY}))
    m["temporal_rpc_duration_ms"] = _percentile_stats(
        _collect_values(recorder, {MetricType.TEMPORAL_EXECUTION_SERVICE_DURATION}),
    )
    m["completion_rate"] = _rate_from_status(
        recorder,
        MetricType.WORKFLOW_STATUS,
        {"completed"},
        dedup_key="execution_id",
    )
    m["active_workflows"] = summary.active_workflows
    m["total_workflows"] = summary.total_workflows
    return ComponentKPISummary(component="execution_service", metrics=m)


def _build_invocation_service(recorder: MetricsRecorder) -> ComponentKPISummary:
    m: _MetricsDict = {}
    m["e2e_duration_ms"] = _percentile_stats(_collect_values(recorder, {MetricType.AGENT_INVOCATION_DURATION}))
    m["invocation_success_rate"] = _rate_from_status(recorder, MetricType.AGENT_STATUS, {"completed", "success"})
    m["status_distribution"] = _label_distribution(recorder, MetricType.AGENT_STATUS, "status")
    return ComponentKPISummary(component="invocation_service", metrics=m)


def _build_routing_service(recorder: MetricsRecorder) -> ComponentKPISummary:
    m: _MetricsDict = {}
    m["decision_time_ms"] = _percentile_stats(_collect_values(recorder, {MetricType.AGENT_ROUTING_DURATION}))
    m["agent_utilization"] = _label_distribution(recorder, MetricType.AGENT_STATUS, "agent_name")
    return ComponentKPISummary(component="routing_service", metrics=m)


def _build_tool_manager(recorder: MetricsRecorder) -> ComponentKPISummary:
    m: _MetricsDict = {}
    m["execution_duration_ms"] = _percentile_stats(_collect_values(recorder, {MetricType.TOOL_EXECUTION_DURATION}))
    m["execution_success_rate"] = _rate_from_status(recorder, MetricType.TOOL_EXECUTION_STATUS, {"success"})
    return ComponentKPISummary(component="tool_manager", metrics=m)


def _build_database(recorder: MetricsRecorder, summary: MetricsSummary) -> ComponentKPISummary:
    m: _MetricsDict = {}
    m["query_response_time_ms"] = _percentile_stats(
        _collect_values(recorder, {MetricType.DATABASE_QUERY_RESPONSE_TIME}),
    )
    m["pool_utilization"] = _percentile_stats(
        _collect_values(recorder, {MetricType.DATABASE_CONNECTION_POOL_UTILIZATION}),
    )
    m["query_by_statement_type"] = _label_distribution(
        recorder,
        MetricType.DATABASE_QUERY_RESPONSE_TIME,
        "statement_type",
    )
    m["total_transactions"] = summary.db_transactions
    return ComponentKPISummary(component="database", metrics=m)


def _build_llm(recorder: MetricsRecorder, summary: MetricsSummary) -> ComponentKPISummary:
    m: _MetricsDict = {}
    m["response_time_ms"] = _percentile_stats(_collect_values(recorder, {MetricType.LLM_DURATION}))
    m["ttft_ms"] = _percentile_stats(_collect_values(recorder, {MetricType.LLM_TTFT}))
    m["tokens_input"] = _percentile_stats(_collect_values(recorder, {MetricType.LLM_TOKENS_INPUT}))
    m["tokens_output"] = _percentile_stats(_collect_values(recorder, {MetricType.LLM_TOKENS_OUTPUT}))
    m["total_calls"] = summary.llm_calls
    m["active_requests"] = summary.active_llm_requests
    return ComponentKPISummary(component="llm", metrics=m)


def _build_cache(recorder: MetricsRecorder, summary: MetricsSummary) -> ComponentKPISummary:
    m: _MetricsDict = {}
    m["hit_rate"] = summary.cache_hit_rate
    m["total_hits"] = summary.cache_hits
    m["total_misses"] = summary.cache_misses
    m["lookup_duration_ms"] = _percentile_stats(_collect_values(recorder, {MetricType.CACHE_LOOKUP_DURATION}))
    m["utilization"] = _percentile_stats(_collect_values(recorder, {MetricType.CACHE_UTILIZATION}))
    return ComponentKPISummary(component="cache", metrics=m)


def _build_system_wide(recorder: MetricsRecorder, summary: MetricsSummary) -> ComponentKPISummary:
    m: _MetricsDict = {}
    m["e2e_latency_ms"] = _percentile_stats(_collect_values(recorder, {MetricType.SYSTEM_E2E_LATENCY}))
    m["error_rate"] = summary.error_rate
    return ComponentKPISummary(component="system_wide", metrics=m)


def _build_kpi_dashboard(recorder: MetricsRecorder) -> KPIDashboard:
    """Build the full KPI dashboard from the in-memory store."""
    summary = recorder.get_summary()
    return KPIDashboard(
        generated_at=datetime.now(UTC),
        components=[
            _build_api_service(recorder, summary),
            _build_workflow_engine(recorder),
            _build_temporal_worker(recorder),
            _build_execution_service(recorder, summary),
            _build_invocation_service(recorder),
            _build_routing_service(recorder),
            _build_tool_manager(recorder),
            _build_database(recorder, summary),
            _build_llm(recorder, summary),
            _build_cache(recorder, summary),
            _build_system_wide(recorder, summary),
        ],
    )


# ---------------------------------------------------------------------------
# Endpoint handlers
# ---------------------------------------------------------------------------


async def metrics_store_summary(
    recorder: Annotated[MetricsRecorder, Depends(get_metrics_recorder)],
) -> MetricsStoreSummary:
    """Return a lightweight summary of the in-memory metrics store."""
    await _guard(recorder)

    store = recorder.store
    records = list(store.query())
    type_counts: dict[str, int] = {}
    oldest: datetime | None = None
    newest: datetime | None = None
    for r in records:
        type_counts[r.metric_type.value] = type_counts.get(r.metric_type.value, 0) + 1
        if oldest is None or r.created_at < oldest:
            oldest = r.created_at
        if newest is None or r.created_at > newest:
            newest = r.created_at

    with recorder._counters_lock:  # noqa: SLF001
        counters = dict(recorder._counters)  # noqa: SLF001

    return MetricsStoreSummary(
        total_records=store.count(),
        retention_seconds=int(store.retention.total_seconds()),
        max_records=store.max_records,
        counters=counters,
        metric_type_counts=type_counts,
        oldest_record_at=oldest,
        newest_record_at=newest,
    )


async def metrics_store_records(
    recorder: Annotated[MetricsRecorder, Depends(get_metrics_recorder)],
    metric_type: Annotated[str | None, Query(description="Filter by metric type value")] = None,
    category: Annotated[MetricsCategoryType | None, Query(description="Filter by category")] = None,
    labels_json: Annotated[
        str | None,
        Query(alias="labels", description='Label filter as JSON, e.g. {"component":"api_service"}'),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=10000, description="Page size")] = 1000,
    offset: Annotated[int, Query(ge=0, description="Offset")] = 0,
) -> MetricsRecordPage:
    """Return raw metric records with optional filtering and pagination."""
    await _guard(recorder)

    metric_types: set[MetricType] | None = None
    if metric_type:
        try:
            metric_types = {MetricType(metric_type)}
        except ValueError:
            raise HTTPException(  # noqa: B904
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown metric_type: {metric_type}",
            )
    elif category:
        cat_types = METRIC_CATEGORIES.get(category)
        if cat_types:
            metric_types = set(cat_types)

    parsed_labels: dict[str, str] | None = None
    if labels_json:
        try:
            raw = json.loads(labels_json)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(  # noqa: B904
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON in labels parameter",
            )
        if not isinstance(raw, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in raw.items()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="labels must be a flat JSON object with string keys and values",
            )
        parsed_labels = raw

    all_records = list(
        recorder.query(metric_types=metric_types, labels=parsed_labels),
    )
    total = len(all_records)
    page = all_records[offset : offset + limit]

    return MetricsRecordPage(records=page, total=total, limit=limit, offset=offset)


async def metrics_store_kpis(
    recorder: Annotated[MetricsRecorder, Depends(get_metrics_recorder)],
) -> KPIDashboard:
    """Return a computed KPI dashboard covering all Syntara components.

    Maps metrics to the KPIs defined in the Syntara KPI documents:
    - Syntara Key Performance Indicators (KPIs)
    - Syntara LLM/Agent Performance KPIs
    """
    await _guard(recorder)
    return _build_kpi_dashboard(recorder)


async def metrics_store_component_kpis(
    component: str,
    recorder: Annotated[MetricsRecorder, Depends(get_metrics_recorder)],
) -> ComponentKPISummary:
    """Return KPIs for a single component."""
    await _guard(recorder)
    dashboard = _build_kpi_dashboard(recorder)
    for comp in dashboard.components:
        if comp.component == component:
            return comp
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Unknown component: {component}",
    )


async def metrics_store_reset(
    recorder: Annotated[MetricsRecorder, Depends(get_metrics_recorder)],
) -> dict[str, Any]:
    """Clear all in-memory metrics (useful between test runs).

    Also clears the emission deduplication tracker and running counters to
    prevent the completion poller from re-emitting metrics for old executions
    that fall back into its lookback window.
    """
    await _guard(recorder)
    count = recorder.store.count()
    recorder.store.clear()
    with recorder._counters_lock:  # noqa: SLF001
        recorder._counters.clear()  # noqa: SLF001
    reset_emission_trackers()
    return {"cleared_records": count, "status": "ok"}
