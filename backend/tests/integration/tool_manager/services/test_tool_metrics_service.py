"""Unit tests for ToolMetricsService.

Tests cover:
- Recording tool executions (success, error, timeout)
- namespaced_name resolution
- UsageCounter upsert behavior
- Concurrent counter updates
"""

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.tool_manager.models.tool import Tool
from syntara.tool_manager.models.tool_execution import ToolExecutionStatus
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
