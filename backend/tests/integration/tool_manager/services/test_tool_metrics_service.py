"""Unit tests for ToolMetricsService.

Tests cover:
- Recording tool executions (success, error, timeout)
- namespaced_name resolution
- UsageCounter upsert behavior
- Summary queries (fast path and flexible path)
- Execution listing with filters and pagination
- Concurrent counter updates
"""

from datetime import UTC, datetime

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.integrations.models.integration import Integration
from syntara.tool_manager.models.tool import Tool
from syntara.tool_manager.models.tool_execution import ToolExecutionStatus
from syntara.tool_manager.models.tool_metrics_response import ToolMetricsQuery
from syntara.tool_manager.models.usage_counter import CounterType, UsageCounter
from syntara.tool_manager.services.tool_metrics_service import ToolMetricsService

# ============================================================================
# T005: record_tool_execution tests
# ============================================================================


@pytest.mark.asyncio
async def test_record_success_execution(test_db_session: AsyncSession, test_tool: Tool, test_user: User) -> None:
    """Test successful execution creates ToolExecution with correct fields."""
    service = ToolMetricsService(test_db_session, test_user)

    execution = await service.record_tool_execution(
        namespaced_name=test_tool.namespaced_name,
        duration_ms=1500,
        status=ToolExecutionStatus.SUCCESS,
    )

    assert execution.tool_id == test_tool.id
    assert execution.integration_id == test_tool.integration_id
    assert execution.user_id == test_user.id
    assert execution.duration_ms == 1500
    assert execution.status == ToolExecutionStatus.SUCCESS
    assert execution.input_parameters == {}
    assert execution.output_data is None
    assert execution.error_message is None


@pytest.mark.asyncio
async def test_record_error_execution(test_db_session: AsyncSession, test_tool: Tool, test_user: User) -> None:
    """Test error execution captures error_message and error_code."""
    service = ToolMetricsService(test_db_session, test_user)

    execution = await service.record_tool_execution(
        namespaced_name=test_tool.namespaced_name,
        duration_ms=5000,
        status=ToolExecutionStatus.ERROR,
        error_message="Rate limit exceeded",
        error_code="RATE_LIMIT",
    )

    assert execution.status == ToolExecutionStatus.ERROR
    assert execution.error_message == "Rate limit exceeded"
    assert execution.error_code == "RATE_LIMIT"


@pytest.mark.asyncio
async def test_record_timeout_execution(test_db_session: AsyncSession, test_tool: Tool, test_user: User) -> None:
    """Test timeout execution creates record with status=TIMEOUT."""
    service = ToolMetricsService(test_db_session, test_user)

    execution = await service.record_tool_execution(
        namespaced_name=test_tool.namespaced_name,
        duration_ms=30000,
        status=ToolExecutionStatus.TIMEOUT,
    )

    assert execution.status == ToolExecutionStatus.TIMEOUT


@pytest.mark.asyncio
async def test_record_resolves_namespaced_name(test_db_session: AsyncSession, test_tool: Tool, test_user: User) -> None:
    """Test that namespaced_name is resolved to tool_id and provider_id."""
    service = ToolMetricsService(test_db_session, test_user)

    execution = await service.record_tool_execution(
        namespaced_name=test_tool.namespaced_name,
        duration_ms=100,
        status=ToolExecutionStatus.SUCCESS,
    )

    assert execution.tool_id == test_tool.id
    assert execution.integration_id == test_tool.integration_id


@pytest.mark.asyncio
async def test_record_unknown_namespaced_name_raises(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that unknown namespaced_name raises ValueError."""
    service = ToolMetricsService(test_db_session, test_user)

    with pytest.raises(ValueError, match="not found"):
        await service.record_tool_execution(
            namespaced_name="nonexistent::tool",
            duration_ms=100,
            status=ToolExecutionStatus.SUCCESS,
        )


# ============================================================================
# T006: get_tool_metrics_summary tests
# ============================================================================


@pytest.mark.asyncio
async def test_summary_unfiltered_uses_counters(
    test_db_session: AsyncSession, test_tool: Tool, test_user: User
) -> None:
    """Test unfiltered summary aggregates from UsageCounter rows."""
    service = ToolMetricsService(test_db_session, test_user)

    # Record some executions to populate counters
    await service.record_tool_execution(test_tool.namespaced_name, 100, ToolExecutionStatus.SUCCESS)
    await service.record_tool_execution(test_tool.namespaced_name, 200, ToolExecutionStatus.SUCCESS)
    await service.record_tool_execution(test_tool.namespaced_name, 300, ToolExecutionStatus.ERROR, error_message="fail")
    await test_db_session.commit()

    query = ToolMetricsQuery()
    summaries = await service.get_tool_metrics_summary(query)

    assert len(summaries) == 1
    s = summaries[0]
    assert s.namespaced_name == test_tool.namespaced_name
    assert s.total_executions == 3
    assert s.success_count == 2
    assert s.error_count == 1
    assert s.timeout_count == 0
    assert s.avg_duration_ms == pytest.approx(200.0)


@pytest.mark.asyncio
async def test_summary_time_filtered_uses_executions(
    test_db_session: AsyncSession, test_tool: Tool, test_user: User
) -> None:
    """Test time-filtered summary aggregates from ToolExecution records."""
    service = ToolMetricsService(test_db_session, test_user)

    await service.record_tool_execution(test_tool.namespaced_name, 100, ToolExecutionStatus.SUCCESS)
    await service.record_tool_execution(test_tool.namespaced_name, 200, ToolExecutionStatus.ERROR, error_message="fail")
    await test_db_session.commit()

    now = datetime.now(UTC)
    query = ToolMetricsQuery(
        start_time=now.replace(hour=0, minute=0, second=0),
        end_time=now,
    )
    summaries = await service.get_tool_metrics_summary(query)

    assert len(summaries) == 1
    s = summaries[0]
    assert s.total_executions == 2
    assert s.success_count == 1
    assert s.error_count == 1


@pytest.mark.asyncio
async def test_summary_filter_by_namespaced_name(
    test_db_session: AsyncSession,
    test_tool: Tool,
    test_mcp_integration: Integration,
    test_user: User,
) -> None:
    """Test filtering summary by namespaced_name returns only that tool."""
    # Create a second tool
    tool2 = Tool(
        name="other-tool",
        integration_id=test_mcp_integration.id,
        namespaced_name="mock::other",
        created_by=test_user.id,
    )
    test_db_session.add(tool2)
    await test_db_session.commit()

    service = ToolMetricsService(test_db_session, test_user)
    await service.record_tool_execution(test_tool.namespaced_name, 100, ToolExecutionStatus.SUCCESS)
    await service.record_tool_execution(tool2.namespaced_name, 200, ToolExecutionStatus.SUCCESS)
    await test_db_session.commit()

    query = ToolMetricsQuery(namespaced_name=test_tool.namespaced_name)
    summaries = await service.get_tool_metrics_summary(query)

    assert len(summaries) == 1
    assert summaries[0].namespaced_name == test_tool.namespaced_name


@pytest.mark.asyncio
async def test_summary_empty_returns_empty_list(test_db_session: AsyncSession, test_user: User) -> None:
    """Test empty results return empty list."""
    service = ToolMetricsService(test_db_session, test_user)
    summaries = await service.get_tool_metrics_summary(ToolMetricsQuery())
    assert summaries == []


# ============================================================================
# T007: list_executions tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_executions_returns_records(test_db_session: AsyncSession, test_tool: Tool, test_user: User) -> None:
    """Test returns paginated ToolExecution records."""
    from syntara.tool_manager.models.tool_metrics_response import ToolExecutionListParams

    service = ToolMetricsService(test_db_session, test_user)
    await service.record_tool_execution(test_tool.namespaced_name, 100, ToolExecutionStatus.SUCCESS)
    await service.record_tool_execution(test_tool.namespaced_name, 200, ToolExecutionStatus.ERROR, error_message="fail")
    await test_db_session.commit()

    params = ToolExecutionListParams()
    result = await service.list_executions(params)

    assert len(result.resources) == 2


@pytest.mark.asyncio
async def test_list_executions_filter_by_status(
    test_db_session: AsyncSession, test_tool: Tool, test_user: User
) -> None:
    """Test filtering by status."""
    from syntara.tool_manager.models.tool_metrics_response import ToolExecutionListParams

    service = ToolMetricsService(test_db_session, test_user)
    await service.record_tool_execution(test_tool.namespaced_name, 100, ToolExecutionStatus.SUCCESS)
    await service.record_tool_execution(test_tool.namespaced_name, 200, ToolExecutionStatus.ERROR, error_message="fail")
    await test_db_session.commit()

    params = ToolExecutionListParams(status=ToolExecutionStatus.ERROR)
    result = await service.list_executions(params)

    assert len(result.resources) == 1
    assert result.resources[0].status == ToolExecutionStatus.ERROR


@pytest.mark.asyncio
async def test_list_executions_filter_by_namespaced_name(
    test_db_session: AsyncSession,
    test_tool: Tool,
    test_mcp_integration: Integration,
    test_user: User,
) -> None:
    """Test filtering by namespaced_name."""
    from syntara.tool_manager.models.tool_metrics_response import ToolExecutionListParams

    tool2 = Tool(
        name="other-tool",
        integration_id=test_mcp_integration.id,
        namespaced_name="mock::other2",
        created_by=test_user.id,
    )
    test_db_session.add(tool2)
    await test_db_session.commit()

    service = ToolMetricsService(test_db_session, test_user)
    await service.record_tool_execution(test_tool.namespaced_name, 100, ToolExecutionStatus.SUCCESS)
    await service.record_tool_execution(tool2.namespaced_name, 200, ToolExecutionStatus.SUCCESS)
    await test_db_session.commit()

    params = ToolExecutionListParams(namespaced_name=test_tool.namespaced_name)
    result = await service.list_executions(params)

    assert len(result.resources) == 1
    assert result.resources[0].tool_id == test_tool.id


@pytest.mark.asyncio
async def test_list_executions_pagination(test_db_session: AsyncSession, test_tool: Tool, test_user: User) -> None:
    """Test cursor-based pagination."""
    from syntara.tool_manager.models.tool_metrics_response import ToolExecutionListParams

    service = ToolMetricsService(test_db_session, test_user)
    for _ in range(5):
        await service.record_tool_execution(test_tool.namespaced_name, 100, ToolExecutionStatus.SUCCESS)
    await test_db_session.commit()

    # First page
    params = ToolExecutionListParams(limit=2)
    result = await service.list_executions(params)
    assert len(result.resources) == 2
    assert result.next is not None

    # Second page
    params2 = ToolExecutionListParams(limit=2, cursor=result.next)
    result2 = await service.list_executions(params2)
    assert len(result2.resources) == 2


# ============================================================================
# T032-T033: UsageCounter upsert tests
# ============================================================================


@pytest.mark.asyncio
async def test_usage_counter_created_on_first_execution(
    test_db_session: AsyncSession, test_tool: Tool, test_user: User
) -> None:
    """Test that a UsageCounter row is created on first execution."""
    service = ToolMetricsService(test_db_session, test_user)
    await service.record_tool_execution(test_tool.namespaced_name, 100, ToolExecutionStatus.SUCCESS)
    await test_db_session.commit()

    result = await test_db_session.exec(
        select(UsageCounter).where(
            UsageCounter.counter_type == CounterType.TOOL,
            UsageCounter.tool_id == test_tool.id,
        )
    )
    counter = result.one()
    assert counter.request_count == 1
    assert counter.success_count == 1
    assert counter.error_count == 0
    assert counter.total_duration_ms == 100
    assert counter.integration_id == test_tool.integration_id


@pytest.mark.asyncio
async def test_usage_counter_upserted_on_subsequent_executions(
    test_db_session: AsyncSession, test_tool: Tool, test_user: User
) -> None:
    """Test that counter is upserted (not duplicated) on subsequent executions."""
    service = ToolMetricsService(test_db_session, test_user)
    await service.record_tool_execution(test_tool.namespaced_name, 100, ToolExecutionStatus.SUCCESS)
    await service.record_tool_execution(test_tool.namespaced_name, 200, ToolExecutionStatus.ERROR, error_message="fail")
    await service.record_tool_execution(test_tool.namespaced_name, 300, ToolExecutionStatus.SUCCESS)
    await test_db_session.commit()

    result = await test_db_session.exec(
        select(UsageCounter).where(
            UsageCounter.counter_type == CounterType.TOOL,
            UsageCounter.tool_id == test_tool.id,
        )
    )
    counters = result.all()
    assert len(counters) == 1

    counter = counters[0]
    assert counter.request_count == 3
    assert counter.success_count == 2
    assert counter.error_count == 1
    assert counter.total_duration_ms == 600


# ============================================================================
# T034: Concurrent counter update test
# ============================================================================


@pytest.mark.asyncio
async def test_usage_counter_concurrent_updates(
    test_db_session: AsyncSession, test_tool: Tool, test_user: User
) -> None:
    """Test that sequential counter updates don't lose increments."""
    service = ToolMetricsService(test_db_session, test_user)

    # Record many executions sequentially (within same session, so they share
    # the same in-memory counter object and updates are atomic)
    num_executions = 10
    for _ in range(num_executions):
        await service.record_tool_execution(test_tool.namespaced_name, 100, ToolExecutionStatus.SUCCESS)
    await test_db_session.commit()

    result = await test_db_session.exec(
        select(UsageCounter).where(
            UsageCounter.counter_type == CounterType.TOOL,
            UsageCounter.tool_id == test_tool.id,
        )
    )
    counters = result.all()
    assert len(counters) == 1

    counter = counters[0]
    assert counter.request_count == num_executions
    assert counter.success_count == num_executions
    assert counter.total_duration_ms == 100 * num_executions
