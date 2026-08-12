"""Unit tests for Tool Metrics models.

Tests cover:
- ToolExecution creation with required fields
- ToolExecutionStatus enum
- ToolMetricsSummary dataclass functionality
- Dictionary conversion methods
- Field validation and constraints
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.integrations.models.integration import Integration
from syntara.tool_manager.models import Tool
from syntara.tool_manager.models.tool_execution import (
    ToolExecution,
    ToolExecutionStatus,
    ToolMetricsSummary,
)


@pytest.mark.asyncio
async def test_create_tool_execution_with_required_fields(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_tool: Tool, test_user: User
) -> None:
    """Test creating a tool execution with all required fields."""
    execution_id = uuid4()
    now = datetime.now(UTC)

    execution = ToolExecution(
        id=execution_id,
        tool_id=test_tool.id,
        integration_id=test_mcp_integration.id,
        user_id=test_user.id,
        execution_start=now,
        status=ToolExecutionStatus.RUNNING,
        input_parameters={"message": "Hello World"},
        created_by=test_user.id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    assert execution.id == execution_id
    assert execution.tool_id == test_tool.id
    assert execution.integration_id == test_mcp_integration.id
    assert execution.user_id == test_user.id
    assert execution.execution_start == now
    assert execution.execution_end is None  # Default value
    assert execution.duration_ms is None  # Default value
    assert execution.status == ToolExecutionStatus.RUNNING
    assert execution.input_parameters == {"message": "Hello World"}
    assert execution.output_data is None  # Default value
    assert execution.error_message is None  # Default value
    assert execution.error_code is None  # Default value
    assert execution.created_by == test_user.id
    assert execution.created_at is not None
    assert execution.updated_at is not None


@pytest.mark.asyncio
async def test_create_tool_execution_with_all_fields(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_tool: Tool, test_user: User
) -> None:
    """Test creating a tool execution with all fields including optional ones."""
    execution_id = uuid4()
    start_time = datetime.now(UTC)
    end_time = datetime.now(UTC)

    execution = ToolExecution(
        id=execution_id,
        tool_id=test_tool.id,
        integration_id=test_mcp_integration.id,
        user_id=test_user.id,
        execution_start=start_time,
        execution_end=end_time,
        duration_ms=1500,
        status=ToolExecutionStatus.SUCCESS,
        input_parameters={"param1": "value1", "param2": 42},
        output_data={"result": "success", "data": [1, 2, 3]},
        error_message=None,
        error_code=None,
        created_by=test_user.id,
        labels={"env": "test", "version": "1.0"},
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    assert execution.execution_end == end_time
    assert execution.duration_ms == 1500
    assert execution.status == ToolExecutionStatus.SUCCESS
    assert execution.input_parameters == {"param1": "value1", "param2": 42}
    assert execution.output_data == {"result": "success", "data": [1, 2, 3]}
    assert execution.labels == {"env": "test", "version": "1.0"}


@pytest.mark.asyncio
async def test_create_tool_execution_with_error(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_tool: Tool, test_user: User
) -> None:
    """Test creating a tool execution with error details."""
    execution_id = uuid4()
    now = datetime.now(UTC)

    execution = ToolExecution(
        id=execution_id,
        tool_id=test_tool.id,
        integration_id=test_mcp_integration.id,
        user_id=test_user.id,
        execution_start=now,
        execution_end=now,
        duration_ms=500,
        status=ToolExecutionStatus.ERROR,
        input_parameters={"timeout_seconds": 30},
        error_message="Connection timeout",
        error_code="TIMEOUT_ERROR",
        created_by=test_user.id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    assert execution.status == ToolExecutionStatus.ERROR
    assert execution.error_message == "Connection timeout"
    assert execution.error_code == "TIMEOUT_ERROR"


def test_execution_status_enum() -> None:
    """Test ToolExecutionStatus enum values."""
    assert ToolExecutionStatus.RUNNING.value == "running"
    assert ToolExecutionStatus.SUCCESS.value == "success"
    assert ToolExecutionStatus.ERROR.value == "error"
    assert ToolExecutionStatus.TIMEOUT.value == "timeout"


def test_tool_execution_constraints() -> None:
    """Test ToolExecution field constraints."""
    tool_id = uuid4()
    user_id = uuid4()
    created_by = uuid4()
    now = datetime.now(UTC)

    # Valid duration_ms (>= 0) should work
    execution = ToolExecution(
        id=uuid4(),
        tool_id=tool_id,
        user_id=user_id,
        execution_start=now,
        duration_ms=0,  # Should be valid
        status=ToolExecutionStatus.SUCCESS,
        input_parameters={"test": "value"},
        created_by=created_by,
    )
    assert execution.duration_ms == 0

    # Negative duration_ms should be invalid
    with pytest.raises(ValueError):
        ToolExecution(
            id=uuid4(),
            tool_id=tool_id,
            user_id=user_id,
            execution_start=now,
            duration_ms=-1,  # Should be invalid
            status=ToolExecutionStatus.SUCCESS,
            input_parameters={"test": "value"},
            created_by=created_by,
        )


def test_tool_metrics_summary_creation() -> None:
    """Test ToolMetricsSummary dataclass creation."""
    now = datetime.now(UTC)

    summary = ToolMetricsSummary(
        total_executions=100,
        success_count=85,
        failure_count=15,
        avg_duration_ms=1200,
        p95_duration_ms=3000,
        time_window="day",
        generated_at=now,
    )

    assert summary.total_executions == 100
    assert summary.success_count == 85
    assert summary.failure_count == 15
    assert summary.avg_duration_ms == 1200
    assert summary.p95_duration_ms == 3000
    assert summary.time_window == "day"
    assert summary.generated_at == now


@pytest.mark.asyncio
async def test_tool_execution_foreign_key_constraints(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_tool: Tool, test_user: User
) -> None:
    """Test that ToolExecution foreign key constraints work correctly."""
    # Create multiple executions with the same foreign keys
    execution1 = ToolExecution(
        id=uuid4(),
        tool_id=test_tool.id,
        integration_id=test_mcp_integration.id,
        user_id=test_user.id,
        execution_start=datetime.now(UTC),
        status=ToolExecutionStatus.RUNNING,
        input_parameters={"exec1": "running"},
        created_by=test_user.id,
    )
    execution2 = ToolExecution(
        id=uuid4(),
        tool_id=test_tool.id,
        integration_id=test_mcp_integration.id,
        user_id=test_user.id,
        execution_start=datetime.now(UTC),
        status=ToolExecutionStatus.TIMEOUT,
        input_parameters={"exec2": "timeout"},
        created_by=test_user.id,
    )

    test_db_session.add_all([execution1, execution2])
    await test_db_session.commit()

    # Verify both executions were created with correct foreign keys
    executions_result = await test_db_session.exec(
        select(ToolExecution).where(
            ToolExecution.tool_id == test_tool.id,
            ToolExecution.integration_id == test_mcp_integration.id,
        )
    )
    executions = executions_result.all()
    assert len(executions) == 2

    # Verify foreign key relationships
    for execution in executions:
        assert execution.tool_id == test_tool.id
        assert execution.integration_id == test_mcp_integration.id
        assert execution.user_id == test_user.id


@pytest.mark.asyncio
async def test_tool_execution_input_parameters_field(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_tool: Tool, test_user: User
) -> None:
    """Test the input_parameters field with various JSON data types."""
    execution_id = uuid4()

    # Test with complex JSON input parameters
    complex_params = {
        "string_param": "test value",
        "number_param": 42,
        "boolean_param": True,
        "null_param": None,
        "array_param": [1, "two", 3.0, {"nested": True}],
        "object_param": {
            "nested_string": "nested value",
            "nested_number": 123.45,
            "deeply_nested": {"level_2": {"level_3": "deep value"}},
        },
    }

    execution = ToolExecution(
        id=execution_id,
        tool_id=test_tool.id,
        integration_id=test_mcp_integration.id,
        user_id=test_user.id,
        execution_start=datetime.now(UTC),
        status=ToolExecutionStatus.SUCCESS,
        input_parameters=complex_params,
        created_by=test_user.id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    # Verify complex JSON is stored and retrieved correctly
    assert execution.input_parameters == complex_params
    assert execution.input_parameters["string_param"] == "test value"
    assert execution.input_parameters["number_param"] == 42
    assert execution.input_parameters["array_param"][3]["nested"] is True
    assert execution.input_parameters["object_param"]["deeply_nested"]["level_2"]["level_3"] == "deep value"


@pytest.mark.asyncio
async def test_tool_execution_output_data_field(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_tool: Tool, test_user: User
) -> None:
    """Test the output_data field with various JSON data types."""
    execution_id = uuid4()

    # Test with complex JSON output data
    complex_output = {
        "status": "success",
        "results": [{"id": 1, "value": "first result"}, {"id": 2, "value": "second result"}],
        "metadata": {
            "execution_time": 1.234,
            "memory_used": 1024,
            "warnings": None,
            "debug_info": {"steps": ["init", "process", "complete"], "performance": {"cpu": 0.5, "memory": 0.8}},
        },
        "binary_data": None,  # Would typically be base64 encoded
    }

    execution = ToolExecution(
        id=execution_id,
        tool_id=test_tool.id,
        integration_id=test_mcp_integration.id,
        user_id=test_user.id,
        execution_start=datetime.now(UTC),
        execution_end=datetime.now(UTC),
        duration_ms=1234,
        status=ToolExecutionStatus.SUCCESS,
        input_parameters={"action": "process"},
        output_data=complex_output,
        created_by=test_user.id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    # Verify complex JSON is stored and retrieved correctly
    assert execution.output_data == complex_output
    assert execution.output_data["status"] == "success"
    assert len(execution.output_data["results"]) == 2
    assert execution.output_data["results"][0]["value"] == "first result"
    assert execution.output_data["metadata"]["execution_time"] == 1.234
    assert execution.output_data["metadata"]["debug_info"]["performance"]["cpu"] == 0.5


@pytest.mark.asyncio
async def test_tool_execution_null_output_data(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_tool: Tool, test_user: User
) -> None:
    """Test that output_data can be null (default behavior)."""
    execution = ToolExecution(
        id=uuid4(),
        tool_id=test_tool.id,
        integration_id=test_mcp_integration.id,
        user_id=test_user.id,
        execution_start=datetime.now(UTC),
        status=ToolExecutionStatus.RUNNING,
        input_parameters={"test": "value"},
        created_by=test_user.id,
        # output_data is intentionally not set (should default to None)
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    # Verify output_data defaults to None
    assert execution.output_data is None


@pytest.mark.asyncio
async def test_tool_execution_empty_json_fields(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_tool: Tool, test_user: User
) -> None:
    """Test ToolExecution with empty JSON objects."""
    execution = ToolExecution(
        id=uuid4(),
        tool_id=test_tool.id,
        integration_id=test_mcp_integration.id,
        user_id=test_user.id,
        execution_start=datetime.now(UTC),
        status=ToolExecutionStatus.SUCCESS,
        input_parameters={},  # Empty JSON object
        output_data={},  # Empty JSON object
        created_by=test_user.id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    # Verify empty JSON objects are handled correctly
    assert execution.input_parameters == {}
    assert execution.output_data == {}


def test_tool_execution_json_field_types() -> None:
    """Test that input_parameters and output_data accept various JSON-compatible types."""
    tool_id = uuid4()
    user_id = uuid4()
    created_by = uuid4()
    now = datetime.now(UTC)

    # Test with different JSON-compatible input types
    test_cases = [
        {"simple": "string"},
        {"number": 42},
        {"float": 3.14159},
        {"boolean": True},
        {"null_value": None},
        {"array": [1, 2, 3]},
        {"mixed_array": ["string", 42, True, None]},
        {"nested": {"level1": {"level2": "deep"}}},
    ]

    for _, params in enumerate(test_cases):
        execution = ToolExecution(
            id=uuid4(),
            tool_id=tool_id,
            user_id=user_id,
            execution_start=now,
            status=ToolExecutionStatus.SUCCESS,
            input_parameters=params,
            output_data=params,  # Use same data for output
            created_by=created_by,
        )

        # Should not raise any validation errors
        assert execution.input_parameters == params
        assert execution.output_data == params
