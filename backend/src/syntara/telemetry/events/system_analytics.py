"""Periodic system analytics event and query result models.

All models are stateless snapshots of current database state.
Sent to Segment at fixed intervals by the PeriodicCollector.
"""

from pydantic import Field, computed_field
from sqlmodel import SQLModel

from syntara.telemetry.events.base import BaseTelemetryEvent


class WorkflowCounts(SQLModel):
    """Current workflow counts from database."""

    total: int = Field(default=0, description="Total workflows")
    enabled: int = Field(default=0, description="Enabled workflows")
    disabled: int = Field(default=0, description="Disabled workflows")


class ExecutionCounts(SQLModel):
    """Current execution counts from database."""

    total: int = Field(default=0, description="Total executions")
    completed: int = Field(default=0, description="Completed executions")
    failed: int = Field(default=0, description="Failed executions")
    cancelled: int = Field(default=0, description="Cancelled executions")
    running: int = Field(default=0, description="Currently running executions")
    pending: int = Field(default=0, description="Pending executions")
    paused: int = Field(default=0, description="Paused executions")
    avg_duration_seconds: float = Field(
        default=0.0,
        description="Average execution duration in seconds",
    )
    by_trigger_type: dict[str, int] = Field(
        default_factory=dict,
        description="Execution count per trigger type",
    )
    by_interface: dict[str, int] = Field(
        default_factory=dict,
        description="Execution count per originating interface (ui, api)",
    )


class CredentialCounts(SQLModel):
    """Aggregated credential counts from database."""

    total: int = Field(default=0, description="Total credentials configured")
    type: dict[str, int] = Field(
        default_factory=dict,
        description="Credential count per credential type name",
    )
    used_in_nodes: int = Field(
        default=0,
        description="Distinct credentials actively referenced in workflow nodes",
    )


class ModelUsage(SQLModel):
    """Aggregated token usage for a single LLM model."""

    model: str = Field(description="LLM model name")
    total_prompt_tokens: int = Field(default=0, description="Total prompt tokens")
    total_completion_tokens: int = Field(default=0, description="Total completion tokens")
    total_tokens: int = Field(default=0, description="Total tokens (prompt + completion)")
    invocation_count: int = Field(default=0, description="Number of invocations")


class ConfigInfo(SQLModel):
    """Configuration information for analytics."""

    feature_flags_enabled: list[str] = Field(
        default_factory=list,
        description="List of enabled feature flags",
    )


class ToolCounts(SQLModel):
    """All-time cumulative tool execution counts (terminal states only)."""

    success_count: int = Field(default=0, description="All-time successful executions")
    error_count: int = Field(default=0, description="All-time failed executions")
    timeout_count: int = Field(default=0, description="All-time timed-out executions")
    distinct_tools: int = Field(default=0, description="Number of distinct tools ever used")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_executions(self) -> int:
        """All-time total tool executions (success + error + timeout)."""
        return self.success_count + self.error_count + self.timeout_count


class UniqueCallerCounts(SQLModel):
    """Unique API caller counts for the current collection period."""

    total: int = Field(
        default=0,
        description=(
            "Total unique callers this period (deduplicated across all dimensions). "
            "May be less than sum(by_interface.values()) when a caller uses both interfaces."
        ),
    )
    by_principal_type: dict[str, int] = Field(
        default_factory=dict,
        description="Unique callers per principal type",
    )
    by_interface: dict[str, int] = Field(
        default_factory=dict,
        description="Unique callers per interface (api, ui)",
    )


class FeatureUsageEntry(SQLModel):
    """Per-endpoint usage count for the current collection period."""

    endpoint_group: str = Field(description="Route template (e.g. /api/v1/workflows)")
    http_method: str = Field(description="HTTP method")
    interface: str = Field(description="Originating interface (api or ui)")
    request_count: int = Field(description="Number of requests this period")


class SystemAnalyticsEvent(BaseTelemetryEvent):
    """Stateless system analytics event sent to Segment.

    Extends BaseTelemetryEvent for consistency with all other telemetry events.

    Each event is a self-contained snapshot of current DB state.
    No delta tracking or "since last report" logic.
    Timestamp is set automatically by the Segment SDK.
    """

    workflows: WorkflowCounts = Field(..., description="Workflow aggregates")
    credentials: CredentialCounts = Field(..., description="Credential aggregates")
    executions: ExecutionCounts = Field(..., description="Execution aggregates")
    config: ConfigInfo = Field(..., description="Configuration info")
    tools: ToolCounts = Field(..., description="Tool usage aggregates")
    model_usage: list[ModelUsage] = Field(
        default_factory=list,
        description="Aggregated token usage per LLM model",
    )
    unique_callers: UniqueCallerCounts = Field(
        default_factory=UniqueCallerCounts,
        description="Unique API caller counts for the current collection period",
    )
    feature_usage: list[FeatureUsageEntry] = Field(
        default_factory=list,
        description="Per-endpoint usage counts for the current collection period",
    )
