"""Tool metrics service for recording tool execution metrics."""

from datetime import UTC, datetime, timedelta

import structlog
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.core.services.base import BaseService
from syntara.tool_manager.models.tool import Tool
from syntara.tool_manager.models.tool_execution import ToolExecution, ToolExecutionStatus
from syntara.tool_manager.models.usage_counter import CounterType, UsageCounter, WindowDuration

logger = structlog.stdlib.get_logger(__name__)


class ToolMetricsService(BaseService):
    """Service for recording tool execution metrics.

    Provides:
    - Recording tool executions to DB (ToolExecution + UsageCounter)

    Note: MetricsRecorder emission is handled by the tool execution wrappers
    in execution_failure_handler.py, not by this service.
    """

    def __init__(
        self,
        session: AsyncSession,
        user: User,
    ) -> None:
        """Initialize ToolMetricsService."""
        super().__init__(session, user)

    async def _resolve_tool(self, namespaced_name: str) -> Tool:
        """Resolve a namespaced_name to a Tool record.

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
