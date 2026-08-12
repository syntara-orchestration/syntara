"""Integration tests for POST /api/v1/executions endpoint."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio.service import RPCError, RPCStatusCode

from syntara.core.models import User
from syntara.workflows.models import Workflow
from syntara.workflows.models.execution import Execution
from syntara.workflows.workflow_engine.services.temporal_execution_service import (
    TemporalExecutionService,
)


@pytest.mark.asyncio
async def test_create_execution_success(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test successful execution creation."""
    response = await auth_client.post(
        "/api/v1/executions",
        json={
            "workflow_id": str(test_workflow.id),
            "input_data": {"key": "value"},
            "trigger_node_id": "trigger_manual",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["workflow_id"] == str(test_workflow.id)
    assert data["status"] == "pending"
    assert data["created_by"] == str(test_user.id)  # Updated from started_by
    assert data["input_data"] == {"key": "value"}
    assert "temporal_workflow_id" in data
    assert data["labels"] == {}
    assert data["current_activities"] == []


@pytest.mark.asyncio
async def test_create_execution_with_default_input_data(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test execution creation with default empty input_data."""
    response = await auth_client.post(
        "/api/v1/executions",
        json={
            "workflow_id": str(test_workflow.id),
            "trigger_node_id": "trigger_manual",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["input_data"] == {}


@pytest.mark.asyncio
async def test_create_execution_workflow_not_found(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test execution creation with non-existent workflow."""
    non_existent_id = uuid.uuid4()
    response = await auth_client.post(
        "/api/v1/executions",
        json={
            "workflow_id": str(non_existent_id),
            "input_data": {},
            "trigger_node_id": "trigger_manual",
        },
    )

    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "The requested workflow was not found"


@pytest.mark.asyncio
async def test_create_execution_unpublished_workflow_succeeds(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test manual execution succeeds even for unpublished workflows."""
    test_workflow.is_enabled = False
    test_workflow.published_version_id = None
    await test_db_session.commit()
    response = await auth_client.post(
        "/api/v1/executions",
        json={"workflow_id": str(test_workflow.id), "input_data": {}, "trigger_node_id": "trigger_manual"},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_create_execution_invalid_workflow_id(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test execution creation with invalid UUID format."""
    response = await auth_client.post(
        "/api/v1/executions",
        json={
            "workflow_id": "not-a-uuid",
            "input_data": {},
        },
    )

    assert response.status_code == 422  # Validation error


# ============================================================================
# Temporal Service Failure Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception",
    [
        pytest.param(
            ConnectionError("Connection refused"),
            id="connection_error",
        ),
        pytest.param(
            RPCError(
                "Temporal server unavailable",
                status=RPCStatusCode.UNAVAILABLE,
                raw_grpc_status=b"",
            ),
            id="rpc_unavailable",
        ),
        pytest.param(
            OSError("Network unreachable"),
            id="os_error",
        ),
        pytest.param(
            RuntimeError("Temporal client initialization failed"),
            id="runtime_error",
        ),
    ],
)
async def test_create_execution_temporal_connection_failure_graceful_degradation(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    exception: Exception,
) -> None:
    """Test execution creation when Temporal service connection fails.

    When Temporal service is unavailable during connection (any connection-related
    exception), the API should gracefully degrade:
    - Still create the execution successfully
    - Use a stub workflow ID instead of a real Temporal workflow ID
    - Return HTTP 201 with the execution details

    This ensures graceful degradation when Temporal is down, regardless of the
    specific exception type (ConnectionError, RPCError, OSError, RuntimeError).
    """
    # Mock create_temporal_execution_service to raise the exception
    with patch(
        "syntara.workflows.executions_router.create_temporal_execution_service",
        side_effect=exception,
    ):
        response = await auth_client.post(
            "/api/v1/executions",
            json={
                "workflow_id": str(test_workflow.id),
                "input_data": {"key": "value"},
                "trigger_node_id": "trigger_manual",
            },
        )

    # Should still succeed with stub workflow ID (graceful degradation)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["workflow_id"] == str(test_workflow.id)
    assert data["status"] == "pending"
    assert data["created_by"] == str(test_user.id)
    assert data["input_data"] == {"key": "value"}

    # Verify temporal_workflow_id is a stub (starts with "exec-")
    assert "temporal_workflow_id" in data
    assert data["temporal_workflow_id"].startswith("exec-")

    # Verify execution was persisted to database with stub workflow ID
    result = await test_db_session.exec(select(Execution).where(Execution.id == uuid.UUID(data["id"])))
    execution = result.one()
    assert execution.temporal_workflow_id == data["temporal_workflow_id"]
    assert execution.temporal_workflow_id.startswith("exec-")
    assert execution.status.value == "pending"
    assert execution.workflow_id == test_workflow.id
    assert execution.created_by == test_user.id
    assert execution.input_data == {"key": "value"}


@pytest.mark.asyncio
async def test_create_execution_temporal_workflow_start_failure(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test execution creation when Temporal workflow start fails.

    When Temporal service is available but workflow start fails (e.g., invalid
    workflow definition, Temporal internal error), the API should:
    - Return HTTP 500 with error details
    - Not create the execution in the database (no orphaned records)

    This verifies the two-phase creation process:
    1. Start Temporal workflow FIRST
    2. Create database record ONLY if Temporal succeeds
    """
    # Count executions before the request
    result = await test_db_session.exec(select(func.count()).select_from(Execution))
    executions_before = result.one()

    # Mock create_temporal_execution_service to return a service
    mock_temporal_service = AsyncMock()

    # Mock start_workflow to raise RPCError (workflow start failure)
    rpc_error = RPCError(
        "Workflow start failed: invalid workflow definition",
        status=RPCStatusCode.INVALID_ARGUMENT,
        raw_grpc_status=b"",
    )
    mock_temporal_service.start_workflow = AsyncMock(side_effect=rpc_error)

    async def mock_create_service() -> TemporalExecutionService:
        return mock_temporal_service

    with patch(
        "syntara.workflows.executions_router.create_temporal_execution_service",
        side_effect=mock_create_service,
    ):
        response = await auth_client.post(
            "/api/v1/executions",
            json={
                "workflow_id": str(test_workflow.id),
                "input_data": {"key": "value"},
                "trigger_node_id": "trigger_manual",
            },
        )

    # Should fail with 500 error and RFC 9457 format
    assert response.status_code == 500
    data = response.json()

    # Verify RFC 9457 Problem Details format
    assert "type" in data
    assert "title" in data
    assert "detail" in data
    assert "code" in data
    assert data["code"] == "TEMPORAL_WORKFLOW_ERROR"
    assert data["detail"] == "Temporal workflow operation failed"

    # Verify no execution was created in the database (two-phase invariant)
    result = await test_db_session.exec(select(func.count()).select_from(Execution))
    executions_after = result.one()
    assert executions_after == executions_before, "No orphaned execution should be created on Temporal failure"


@pytest.mark.asyncio
async def test_create_execution_with_trigger_node_id(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test that trigger_node_id round-trips through the API and database."""
    response = await auth_client.post(
        "/api/v1/executions",
        json={
            "workflow_id": str(test_workflow.id),
            "input_data": {},
            "trigger_node_id": "trigger_manual",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["trigger_node_id"] == "trigger_manual"

    # Verify persisted to database
    result = await test_db_session.exec(select(Execution).where(Execution.id == uuid.UUID(data["id"])))
    execution = result.one()
    assert execution.trigger_node_id == "trigger_manual"


@pytest.mark.asyncio
async def test_create_execution_without_trigger_node_id_returns_422(
    auth_client: AsyncClient,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test that omitting trigger_node_id returns a 422 validation error."""
    response = await auth_client.post(
        "/api/v1/executions",
        json={
            "workflow_id": str(test_workflow.id),
            "input_data": {},
        },
    )

    assert response.status_code == 422
