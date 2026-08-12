"""Tool metrics service for recording and querying tool execution metrics."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

import structlog
from fastapi import Depends
from sqlalchemy import case
from sqlalchemy import func as sa_func
from sqlalchemy import select as sa_select
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth import get_current_user
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.services.base import BaseService
from syntara.tool_manager.models.tool import Tool
from syntara.tool_manager.models.tool_execution import ToolExecution, ToolExecutionStatus
from syntara.tool_manager.models.tool_metrics_response import (
    ToolExecutionListParams,
    ToolExecutionListResponse,
    ToolMetricsQuery,
    ToolMetricsToolSummary,
)
from syntara.tool_manager.models.usage_counter import CounterType, UsageCounter, WindowDuration

logger = structlog.stdlib.get_logger(__name__)


class ToolMetricsService(BaseService):
    """Service for recording and querying tool execution metrics.

    Provides:
    - Recording tool executions to DB (ToolExecution + UsageCounter)
    - Aggregated per-tool metrics summaries (fast path via UsageCounter, flexible path via SQL)
    - Paginated execution history with filtering

    Note: MetricsRecorder emission is handled by the tool execution wrappers
    in execution_failure_handler.py, not by this service.
    """

    def __init__(
        self,
        session: AsyncSession,
        user: User,
    ) -> None:
        """Initialize ToolMetricsService.

        Args:
            session: Async database session.
            user: Current authenticated user.

        """
        super().__init__(session, user)

    async def _resolve_tool(self, namespaced_name: str) -> Tool:
        """Resolve a namespaced_name to a Tool record.

        Results are cached for the lifetime of the service instance since
        the namespaced_name → tool mapping is stable.

        Args:
            namespaced_name: Tool identifier (e.g., "provider::tool").

        Returns:
            The matching Tool record.

        Raises:
            ValueError: If no tool matches the namespaced_name.

        """
        result = await self.session.exec(
            select(Tool).where(
                Tool.namespaced_name == namespaced_name,
            )
        )
        tool = result.one_or_none()
        if tool is None:
            msg = f"Tool with namespaced_name '{namespaced_name}' not found"
            raise ValueError(msg)
        return tool

    async def record_tool_execution(
        self,
        namespaced_name: str,
        duration_ms: int,
        status: ToolExecutionStatus,
        error_message: str | None = None,
        error_code: str | None = None,
    ) -> ToolExecution:
        """Record a tool execution to DB.

        Creates a ToolExecution record and upserts the UsageCounter.

        Args:
            namespaced_name: Tool identifier.
            duration_ms: Execution duration in milliseconds.
            status: Execution outcome.
            error_message: Error description (for failed executions).
            error_code: Structured error code (for failed executions).

        Returns:
            The persisted ToolExecution record.

        """
        now = datetime.now(UTC)
        execution_start = now - timedelta(milliseconds=duration_ms)
        try:
            tool = await self._resolve_tool(namespaced_name)

            tool_execution = ToolExecution(
                tool_id=tool.id,
                integration_id=tool.integration_id,
                user_id=self.user.id,
                execution_start=execution_start,
                execution_end=now,
                duration_ms=duration_ms,
                status=status,
                input_parameters={},
                output_data=None,
                error_message=error_message,
                error_code=error_code,
                created_by=self.user.id,
            )
            self.session.add(tool_execution)

            await self._upsert_usage_counter(tool, duration_ms, status, now)

            await self.session.flush()
        except Exception:
            logger.exception(
                "Failed to record tool execution to DB",
                namespaced_name=namespaced_name,
            )
            raise

        return tool_execution

    def _create_usage_counter(self, tool: Tool, now: datetime) -> UsageCounter:
        """Create a new UsageCounter for the current hour window."""
        window_start = now.replace(minute=0, second=0, microsecond=0)
        counter = UsageCounter(
            counter_type=CounterType.TOOL,
            tool_id=tool.id,
            integration_id=tool.integration_id,
            time_window=now.strftime("%Y-%m-%d-%H"),
            window_duration=WindowDuration.HOUR,
            window_start=window_start,
            window_end=window_start + timedelta(hours=1),
            request_count=0,
            success_count=0,
            error_count=0,
            timeout_count=0,
            total_duration_ms=0,
            created_by=self.user.id,
        )
        self.session.add(counter)
        return counter

    async def _upsert_usage_counter(
        self,
        tool: Tool,
        duration_ms: int,
        status: ToolExecutionStatus,
        now: datetime,
    ) -> None:
        """Upsert a UsageCounter row for the current hour window."""
        window_key = now.strftime("%Y-%m-%d-%H")

        result = await self.session.exec(
            select(UsageCounter).where(
                UsageCounter.counter_type == CounterType.TOOL,
                UsageCounter.tool_id == tool.id,
                UsageCounter.time_window == window_key,
            )
        )
        counter = result.one_or_none() or self._create_usage_counter(tool, now)

        counter.request_count += 1
        counter.total_duration_ms += duration_ms
        if status == ToolExecutionStatus.SUCCESS:
            counter.success_count += 1
        elif status == ToolExecutionStatus.ERROR:
            counter.error_count += 1
        elif status == ToolExecutionStatus.TIMEOUT:
            counter.timeout_count += 1

    async def get_tool_metrics_summary(
        self,
        query: ToolMetricsQuery,
    ) -> list[ToolMetricsToolSummary]:
        """Return aggregated per-tool metrics summaries.

        Uses UsageCounter aggregation when no time filter is provided (fast path).
        Uses SQL aggregation over ToolExecution records when time filter is provided (flexible path).

        Args:
            query: Query parameters with optional namespaced_name and time range filters.

        Returns:
            List of per-tool metric summaries.

        """
        has_time_filter = query.start_time is not None or query.end_time is not None

        if has_time_filter:
            return await self._summary_from_executions(query)
        return await self._summary_from_counters(query)

    async def _summary_from_counters(
        self,
        query: ToolMetricsQuery,
    ) -> list[ToolMetricsToolSummary]:
        """Fast path: aggregate UsageCounter rows grouped by tool_id."""
        # Subquery to get last_execution_at per tool in a single round-trip
        last_exec_subq = (
            sa_select(  # type: ignore[call-overload]
                ToolExecution.tool_id,
                sa_func.max(ToolExecution.execution_start).label("last_execution_at"),
            )
            .group_by(ToolExecution.tool_id)
            .subquery("last_exec")
        )

        stmt = (
            sa_select(  # type: ignore[call-overload]
                Tool.namespaced_name,
                sa_func.sum(UsageCounter.request_count).label("total_executions"),
                sa_func.sum(UsageCounter.success_count).label("success_count"),
                sa_func.sum(UsageCounter.error_count).label("error_count"),
                sa_func.sum(UsageCounter.timeout_count).label("timeout_count"),
                sa_func.sum(UsageCounter.total_duration_ms).label("total_duration_ms"),
                last_exec_subq.c.last_execution_at,
            )
            .join(Tool, UsageCounter.tool_id == Tool.id)
            .outerjoin(last_exec_subq, Tool.id == last_exec_subq.c.tool_id)
            .where(
                UsageCounter.counter_type == CounterType.TOOL,
            )
            .group_by(Tool.namespaced_name, last_exec_subq.c.last_execution_at)
        )

        if query.namespaced_name is not None:
            stmt = stmt.where(Tool.namespaced_name == query.namespaced_name)

        raw_result = await self.session.exec(stmt)
        rows = raw_result.all()

        summaries = []
        for row in rows:
            total = int(row.total_executions or 0)
            success = int(row.success_count or 0)
            error = int(row.error_count or 0)
            timeout = int(row.timeout_count or 0)
            total_dur = int(row.total_duration_ms or 0)

            summaries.append(
                ToolMetricsToolSummary(
                    namespaced_name=row.namespaced_name,
                    total_executions=total,
                    success_count=success,
                    error_count=error,
                    timeout_count=timeout,
                    success_rate=success / total if total > 0 else 0.0,
                    avg_duration_ms=total_dur / total if total > 0 else 0.0,
                    last_execution_at=row.last_execution_at,
                )
            )

        return summaries

    async def _summary_from_executions(
        self,
        query: ToolMetricsQuery,
    ) -> list[ToolMetricsToolSummary]:
        """Flexible path: aggregate ToolExecution records via SQL."""
        status_col = ToolExecution.__table__.c.status  # type: ignore[attr-defined]
        stmt = (
            sa_select(  # type: ignore[call-overload]
                Tool.namespaced_name,
                sa_func.count().label("total_executions"),
                sa_func.sum(case((status_col == ToolExecutionStatus.SUCCESS.value, 1), else_=0)).label("success_count"),
                sa_func.sum(case((status_col == ToolExecutionStatus.ERROR.value, 1), else_=0)).label("error_count"),
                sa_func.sum(case((status_col == ToolExecutionStatus.TIMEOUT.value, 1), else_=0)).label("timeout_count"),
                sa_func.avg(ToolExecution.duration_ms).label("avg_duration_ms"),
                sa_func.max(ToolExecution.execution_start).label("last_execution_at"),
            )
            .join(Tool, ToolExecution.tool_id == Tool.id)
            .group_by(Tool.namespaced_name)
        )

        if query.namespaced_name is not None:
            stmt = stmt.where(Tool.namespaced_name == query.namespaced_name)
        if query.start_time is not None:
            stmt = stmt.where(ToolExecution.execution_start >= query.start_time)
        if query.end_time is not None:
            stmt = stmt.where(ToolExecution.execution_start <= query.end_time)

        raw_result = await self.session.exec(stmt)
        rows = raw_result.all()

        summaries = []
        for row in rows:
            total = int(row.total_executions)
            success = int(row.success_count or 0)
            error = int(row.error_count or 0)
            timeout = int(row.timeout_count or 0)
            avg_dur = float(row.avg_duration_ms or 0)

            summaries.append(
                ToolMetricsToolSummary(
                    namespaced_name=row.namespaced_name,
                    total_executions=total,
                    success_count=success,
                    error_count=error,
                    timeout_count=timeout,
                    success_rate=success / total if total > 0 else 0.0,
                    avg_duration_ms=avg_dur,
                    last_execution_at=row.last_execution_at,
                )
            )

        return summaries

    async def list_executions(
        self,
        params: ToolExecutionListParams,
    ) -> ToolExecutionListResponse:
        """Return paginated tool execution history with filtering.

        Args:
            params: Query parameters including pagination, status, namespaced_name, and time range.

        Returns:
            Paginated response of ToolExecution records.

        """
        query_items: list[tuple[str, str]] = []

        if params.status is not None:
            query_items.append(("status", params.status.value))
        if params.start_time is not None:
            query_items.append(("created_at[gte]", params.start_time.isoformat()))
        if params.end_time is not None:
            query_items.append(("created_at[lte]", params.end_time.isoformat()))

        if params.namespaced_name is not None:
            tool = await self._resolve_tool(params.namespaced_name)
            query_items.append(("tool_id", str(tool.id)))

        return await self.list_resources(
            model=ToolExecution,
            response_type=ToolExecutionListResponse,
            limit=params.limit,
            cursor=params.cursor,
            sort=params.sort or "-created_at",
            include_total=params.include_total,
            query_params_items=query_items or None,
        )


def get_tool_metrics_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ToolMetricsService:
    """Dependency provider for ToolMetricsService."""
    return ToolMetricsService(db, current_user)
