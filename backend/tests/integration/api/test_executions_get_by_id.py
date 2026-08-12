"""Integration tests for GET /api/v1/executions/{id} endpoint."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.models import ActivityExecution, Workflow
from syntara.workflows.models.execution import Execution, ExecutionStatus


@pytest.mark.asyncio
async def test_get_execution_by_id_success(
    auth_client: AsyncClient,
    test_execution: Execution,
    test_workflow: Workflow,
) -> None:
    """Test successfully retrieving an execution by ID."""
    response = await auth_client.get(f"/api/v1/executions/{test_execution.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_execution.id)
    assert data["workflow_id"] == str(test_execution.workflow_id)
    assert data["workflow_name"] == test_workflow.name
    assert data["status"] == ExecutionStatus.PENDING.value
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_get_execution_by_id_not_found(
    auth_client: AsyncClient,
) -> None:
    """Test retrieving a non-existent execution returns 404."""
    non_existent_id = uuid.uuid4()
    response = await auth_client.get(f"/api/v1/executions/{non_existent_id}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_execution_with_error_details(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_execution: Execution,
) -> None:
    """Test retrieving a failed execution includes error details."""
    # Update execution to failed status with error details
    test_execution.status = ExecutionStatus.FAILED
    test_execution.error_details = "Connection timeout to external service"
    await test_db_session.commit()

    # Fetch the execution
    response = await auth_client.get(f"/api/v1/executions/{test_execution.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == ExecutionStatus.FAILED.value
    assert data["error_details"] == "Connection timeout to external service"


@pytest.mark.asyncio
async def test_get_execution_with_completed_at(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_execution: Execution,
) -> None:
    """Test retrieving a completed execution includes completed_at timestamp."""
    # Update execution to completed status with timestamp
    test_execution.status = ExecutionStatus.COMPLETED
    test_execution.completed_at = datetime.now(UTC)
    await test_db_session.commit()

    # Fetch the execution
    response = await auth_client.get(f"/api/v1/executions/{test_execution.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == ExecutionStatus.COMPLETED.value
    assert "completed_at" in data
    assert data["completed_at"] is not None


# ============================================================================
# Include Parameter Tests
# ============================================================================


def _assert_workflow_definition(data: dict[str, Any], test_workflow_definition: dict[str, Any]) -> None:
    # Verify workflow definition matches the test fixture
    # test_workflow_definition is used in test_execution.workflow.workflow_version
    assert "workflow_definition" in data
    assert data["workflow_definition"] is not None
    assert data["workflow_definition"] == test_workflow_definition


def _assert_workflow_activities(data: dict[str, Any], test_activity: ActivityExecution) -> None:
    # Verify workflow activities matches the test fixture
    assert "activities" in data
    assert data["activities"] is not None
    activities = data["activities"]
    assert isinstance(activities, list)
    assert len(activities) == 1
    assert activities[0]["activity_id"] == test_activity.activity_name
    assert activities[0]["status"] == test_activity.status
    assert activities[0]["error_details"] == test_activity.error_details
    # Check datetime fields with proper formatting
    if test_activity.started_at is not None:
        expected_started_at = test_activity.started_at.isoformat().replace("+00:00", "Z")
        assert activities[0]["started_at"] == expected_started_at
    if test_activity.completed_at is not None:
        expected_completed_at = test_activity.completed_at.isoformat().replace("+00:00", "Z")
        assert activities[0]["completed_at"] == expected_completed_at


@pytest.mark.asyncio
async def test_get_execution_by_id_with_include_workflow_definition(
    auth_client: AsyncClient,
    test_execution: Execution,
    test_workflow_definition: dict[str, Any],
) -> None:
    """Test retrieving an execution with include=workflow_definition parameter."""
    response = await auth_client.get(f"/api/v1/executions/{test_execution.id}?include=workflow_definition")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_execution.id)
    assert data["workflow_id"] == str(test_execution.workflow_id)
    assert data["status"] == ExecutionStatus.PENDING.value
    _assert_workflow_definition(data, test_workflow_definition)


@pytest.mark.asyncio
async def test_get_execution_by_id_with_include_activities(
    auth_client: AsyncClient,
    test_execution: Execution,
    test_activity: ActivityExecution,
) -> None:
    """Test retrieving an execution with include=activities parameter."""
    response = await auth_client.get(f"/api/v1/executions/{test_execution.id}?include=activities")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_execution.id)
    assert data["workflow_id"] == str(test_execution.workflow_id)
    assert data["status"] == ExecutionStatus.PENDING.value
    _assert_workflow_activities(data, test_activity)


@pytest.mark.asyncio
async def test_get_execution_by_id_with_include_multiple_values(
    auth_client: AsyncClient,
    test_execution: Execution,
    test_workflow_definition: dict[str, Any],
    test_activity: ActivityExecution,
) -> None:
    """Test retrieving an execution with include=workflow_definition,activities parameter."""
    response = await auth_client.get(f"/api/v1/executions/{test_execution.id}?include=workflow_definition,activities")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_execution.id)
    assert data["workflow_id"] == str(test_execution.workflow_id)
    assert data["status"] == ExecutionStatus.PENDING.value
    _assert_workflow_definition(data, test_workflow_definition)
    _assert_workflow_activities(data, test_activity)


@pytest.mark.asyncio
async def test_get_execution_by_id_with_invalid_include_value(
    auth_client: AsyncClient,
    test_execution: Execution,
) -> None:
    """Test retrieving an execution with invalid include parameter returns 422 (Pydantic validation)."""
    response = await auth_client.get(f"/api/v1/executions/{test_execution.id}?include=invalid_value")

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_get_execution_by_id_with_duplicate_include_values(
    auth_client: AsyncClient,
    test_execution: Execution,
) -> None:
    """Test retrieving an execution with duplicate include values returns 422 (Pydantic validation)."""
    response = await auth_client.get(f"/api/v1/executions/{test_execution.id}?include=activities,activities")

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


# ============================================================================
# workflow_name field tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_execution_by_id_workflow_name_after_soft_delete(
    auth_client: AsyncClient,
    test_execution: Execution,
    test_workflow: Workflow,
    test_user: User,
    test_db_session: AsyncSession,
) -> None:
    """Test that workflow_name is still returned after the workflow is soft-deleted."""
    test_workflow.soft_delete(user_id=test_user.id, deletion_time=datetime.now(UTC))
    await test_db_session.commit()

    response = await auth_client.get(f"/api/v1/executions/{test_execution.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["workflow_name"] == test_workflow.name
