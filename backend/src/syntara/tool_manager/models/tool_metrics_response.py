"""Response and query models for tool metrics endpoints."""

from datetime import datetime
from typing import ClassVar

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel

from syntara.core.models.base.query_params import BaseListParams
from syntara.core.models.pagination import ResourcesResponse
from syntara.tool_manager.models.tool_execution import ToolExecution, ToolExecutionStatus


class ToolMetricsToolSummary(SQLModel):
    """Per-tool aggregated metrics summary for the metrics/tools endpoint."""

    namespaced_name: str = Field(description="Tool identifier (e.g., 'provider::tool')")
    total_executions: int = Field(description="Total execution count")
    success_count: int = Field(description="Successful executions")
    error_count: int = Field(description="Error executions")
    timeout_count: int = Field(description="Timeout executions")
    success_rate: float = Field(description="Success rate (0.0 to 1.0)")
    avg_duration_ms: float = Field(description="Average execution duration in milliseconds")
    last_execution_at: datetime | None = Field(default=None, description="Timestamp of most recent execution")

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
    )  # type: ignore[assignment]


class ToolMetricsQuery(SQLModel):
    """Query parameters for the tool metrics summary endpoint."""

    namespaced_name: str | None = Field(default=None, description="Filter by tool namespaced name")
    start_time: datetime | None = Field(default=None, description="Start of time range (ISO 8601)")
    end_time: datetime | None = Field(default=None, description="End of time range (ISO 8601)")


class ToolExecutionListParams(BaseListParams):
    """Query parameters for the tool execution history endpoint."""

    namespaced_name: str | None = Field(default=None, description="Filter by tool namespaced name")
    status: ToolExecutionStatus | None = Field(default=None, description="Filter by execution status")
    start_time: datetime | None = Field(default=None, description="Start of time range (ISO 8601)")
    end_time: datetime | None = Field(default=None, description="End of time range (ISO 8601)")


class ToolMetricsToolSummaryListResponse(ResourcesResponse[ToolMetricsToolSummary]):
    """Paginated list response for tool metrics summaries."""


class ToolExecutionListResponse(ResourcesResponse[ToolExecution]):
    """Paginated list response for tool executions."""
