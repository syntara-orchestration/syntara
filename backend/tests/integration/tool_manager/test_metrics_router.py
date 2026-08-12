"""Integration tests for tool metrics REST API endpoints.

Tests cover:
- GET /api/v1/tool_manager/metrics/tools (summary endpoint)
- GET /api/v1/tool_manager/metrics/executions (execution history endpoint)
- Filtering, pagination, empty state, time range, and dual-write behavior
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.integrations.models.integration import Integration
from syntara.tool_manager.models.tool import Tool
from syntara.tool_manager.models.tool_execution import ToolExecutionStatus
from syntara.tool_manager.services.tool_metrics_service import ToolMetricsService

# ============================================================================
# T013-T016: Summary endpoint tests
# ============================================================================


@pytest.mark.asyncio
async def test_summary_returns_per_tool_metrics(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_tool: Tool,
    test_user: User,
) -> None:
    """Test summary returns correct per-tool breakdowns."""
    service = ToolMetricsService(test_db_session, test_user)
    await service.record_tool_execution(test_tool.namespaced_name, 100, ToolExecutionStatus.SUCCESS)
    await service.record_tool_execution(test_tool.namespaced_name, 200, ToolExecutionStatus.SUCCESS)
    await service.record_tool_execution(test_tool.namespaced_name, 300, ToolExecutionStatus.ERROR, error_message="fail")
    await test_db_session.commit()

    response = await auth_client.get("/api/v1/tool_manager/metrics/tools")
    assert response.status_code == 200

    data = response.json()
    assert "resources" in data
    assert len(data["resources"]) == 1

    summary = data["resources"][0]
    assert summary["namespaced_name"] == test_tool.namespaced_name
    assert summary["total_executions"] == 3
    assert summary["success_count"] == 2
    assert summary["error_count"] == 1
    assert summary["timeout_count"] == 0
    assert summary["success_rate"] == pytest.approx(2 / 3, rel=1e-2)


@pytest.mark.asyncio
async def test_summary_empty_returns_empty_list(
    auth_client: AsyncClient,
) -> None:
    """Test empty state returns empty resources list."""
    response = await auth_client.get("/api/v1/tool_manager/metrics/tools")
    assert response.status_code == 200

    data = response.json()
    assert data["resources"] == []


@pytest.mark.asyncio
async def test_summary_filter_by_namespaced_name(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_tool: Tool,
    test_mcp_integration: Integration,
    test_user: User,
) -> None:
    """Test filtering summary by namespaced_name."""
    tool2 = Tool(
        name="other-tool",
        integration_id=test_mcp_integration.id,
        namespaced_name="mock::filter_test",
        created_by=test_user.id,
    )
    test_db_session.add(tool2)
    await test_db_session.commit()

    service = ToolMetricsService(test_db_session, test_user)
    await service.record_tool_execution(test_tool.namespaced_name, 100, ToolExecutionStatus.SUCCESS)
    await service.record_tool_execution(tool2.namespaced_name, 200, ToolExecutionStatus.SUCCESS)
    await test_db_session.commit()

    response = await auth_client.get(
        "/api/v1/tool_manager/metrics/tools",
        params={"namespaced_name": test_tool.namespaced_name},
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data["resources"]) == 1
    assert data["resources"][0]["namespaced_name"] == test_tool.namespaced_name


@pytest.mark.asyncio
async def test_summary_filter_by_time_range(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_tool: Tool,
    test_user: User,
) -> None:
    """T016: Test time-filtered summary only includes executions in window."""
    service = ToolMetricsService(test_db_session, test_user)

    # Record executions (all created "now" in the DB)
    await service.record_tool_execution(test_tool.namespaced_name, 100, ToolExecutionStatus.SUCCESS)
    await service.record_tool_execution(test_tool.namespaced_name, 200, ToolExecutionStatus.ERROR, error_message="fail")
    await test_db_session.commit()

    now = datetime.now(UTC)
    start = (now - timedelta(hours=1)).isoformat()
    end = (now + timedelta(hours=1)).isoformat()

    response = await auth_client.get(
        "/api/v1/tool_manager/metrics/tools",
        params={"start_time": start, "end_time": end},
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data["resources"]) == 1
    assert data["resources"][0]["total_executions"] == 2
    assert data["resources"][0]["success_count"] == 1
    assert data["resources"][0]["error_count"] == 1

    # Query with a time range in the past that excludes all executions
    old_start = (now - timedelta(days=30)).isoformat()
    old_end = (now - timedelta(days=29)).isoformat()
    response2 = await auth_client.get(
        "/api/v1/tool_manager/metrics/tools",
        params={"start_time": old_start, "end_time": old_end},
    )
    assert response2.status_code == 200
    assert response2.json()["resources"] == []


# ============================================================================
# T021-T024: Execution history endpoint tests
# ============================================================================


@pytest.mark.asyncio
async def test_executions_returns_records(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_tool: Tool,
    test_user: User,
) -> None:
    """Test execution history returns individual records."""
    service = ToolMetricsService(test_db_session, test_user)
    await service.record_tool_execution(test_tool.namespaced_name, 100, ToolExecutionStatus.SUCCESS)
    await service.record_tool_execution(test_tool.namespaced_name, 200, ToolExecutionStatus.ERROR, error_message="fail")
    await test_db_session.commit()

    response = await auth_client.get("/api/v1/tool_manager/metrics/executions")
    assert response.status_code == 200

    data = response.json()
    assert len(data["resources"]) == 2


@pytest.mark.asyncio
async def test_executions_filter_by_status(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_tool: Tool,
    test_user: User,
) -> None:
    """Test filtering executions by status."""
    service = ToolMetricsService(test_db_session, test_user)
    await service.record_tool_execution(test_tool.namespaced_name, 100, ToolExecutionStatus.SUCCESS)
    await service.record_tool_execution(test_tool.namespaced_name, 200, ToolExecutionStatus.ERROR, error_message="fail")
    await test_db_session.commit()

    response = await auth_client.get(
        "/api/v1/tool_manager/metrics/executions",
        params={"status": "error"},
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data["resources"]) == 1
    assert data["resources"][0]["status"] == "error"


@pytest.mark.asyncio
async def test_executions_pagination(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_tool: Tool,
    test_user: User,
) -> None:
    """Test cursor-based pagination on execution history."""
    service = ToolMetricsService(test_db_session, test_user)
    for _ in range(5):
        await service.record_tool_execution(test_tool.namespaced_name, 100, ToolExecutionStatus.SUCCESS)
    await test_db_session.commit()

    # First page
    response = await auth_client.get(
        "/api/v1/tool_manager/metrics/executions",
        params={"limit": 2},
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data["resources"]) == 2
    assert data["next"] is not None

    # Second page
    response2 = await auth_client.get(
        "/api/v1/tool_manager/metrics/executions",
        params={"limit": 2, "cursor": data["next"]},
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["resources"]) == 2


@pytest.mark.asyncio
async def test_executions_filter_by_namespaced_name(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_tool: Tool,
    test_mcp_integration: Integration,
    test_user: User,
) -> None:
    """T023: Test filtering executions by namespaced_name."""
    tool2 = Tool(
        name="other-tool",
        integration_id=test_mcp_integration.id,
        namespaced_name="mock::exec_filter",
        created_by=test_user.id,
    )
    test_db_session.add(tool2)
    await test_db_session.commit()

    service = ToolMetricsService(test_db_session, test_user)
    await service.record_tool_execution(test_tool.namespaced_name, 100, ToolExecutionStatus.SUCCESS)
    await service.record_tool_execution(test_tool.namespaced_name, 150, ToolExecutionStatus.SUCCESS)
    await service.record_tool_execution(tool2.namespaced_name, 200, ToolExecutionStatus.SUCCESS)
    await test_db_session.commit()

    response = await auth_client.get(
        "/api/v1/tool_manager/metrics/executions",
        params={"namespaced_name": test_tool.namespaced_name},
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data["resources"]) == 2
    for resource in data["resources"]:
        assert resource["tool_id"] == str(test_tool.id)


# ============================================================================
# T027-T028: Automatic metric recording tests (US3)
# ============================================================================


@pytest.mark.asyncio
async def test_record_execution_creates_db_record(
    test_db_session: AsyncSession,
    test_tool: Tool,
    test_user: User,
) -> None:
    """T027: Verify ToolExecution record created with correct fields after recording."""
    service = ToolMetricsService(test_db_session, test_user)
    execution = await service.record_tool_execution(
        namespaced_name=test_tool.namespaced_name,
        duration_ms=1500,
        status=ToolExecutionStatus.SUCCESS,
    )
    await test_db_session.commit()

    assert execution.tool_id == test_tool.id
    assert execution.integration_id == test_tool.integration_id
    assert execution.duration_ms == 1500
    assert execution.status == ToolExecutionStatus.SUCCESS
    assert execution.input_parameters == {}
    assert execution.output_data is None
