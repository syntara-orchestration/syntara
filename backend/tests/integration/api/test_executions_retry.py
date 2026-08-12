"""Integration tests for POST /api/v1/executions/{id}/retry endpoint."""

import uuid
from collections.abc import Generator
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.models.execution import Execution, ExecutionMode, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.models.responses import WorkflowStartResponse
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService
from tests.integration.helpers.error_data import assert_error_data


@pytest.fixture
def mock_temporal_service(session_app) -> Generator[Mock, None, None]:
    """Override temporal service dependency with a mock."""
    from syntara.workflows.executions_router import get_temporal_execution_service

    mock_service = Mock(spec=TemporalExecutionService)

    new_execution_id = str(uuid.uuid4())
    mock_service.start_workflow = AsyncMock(
        return_value=WorkflowStartResponse(
            execution_id=new_execution_id,
            workflow_id="wf-mock",
            temporal_workflow_id=f"temporal-{new_execution_id}",
            temporal_run_id=f"run-{new_execution_id}",
            status="RUNNING",
            started_at="2026-01-01T00:00:00Z",
        )
    )

    async def override_get_temporal_service() -> Mock:
        return mock_service

    session_app.dependency_overrides[get_temporal_execution_service] = override_get_temporal_service

    yield mock_service

    session_app.dependency_overrides.pop(get_temporal_execution_service, None)


async def _create_execution(
    session: AsyncSession,
    workflow: Workflow,
    user: User,
    *,
    execution_status: ExecutionStatus = ExecutionStatus.FAILED,
    mode: ExecutionMode = ExecutionMode.STANDARD,
) -> Execution:
    """Create a test execution record."""
    result = await session.exec(
        select(WorkflowVersion.id).where(
            WorkflowVersion.workflow_id == workflow.id,
            WorkflowVersion.version == workflow.current_version,
        )
    )
    version_id = result.one()

    execution = Execution(
        workflow_id=workflow.id,
        workflow_version_id=version_id,
        temporal_workflow_id=f"temporal-{uuid.uuid4()}",
        status=execution_status,
        created_by=user.id,
        input_data={"key": "value"},
        labels={},
        project_id=workflow.project_id,
        mode=mode,
        trigger_node_id="trigger_manual",
    )
    session.add(execution)
    await session.commit()
    await session.refresh(execution)
    return execution


@pytest.mark.asyncio
class TestRetryExecution:
    """Integration tests for POST /executions/{execution_id}/retry."""

    @pytest.mark.parametrize(
        "execution_status",
        [
            ExecutionStatus.FAILED,
            ExecutionStatus.COMPLETED,
            ExecutionStatus.COMPLETED_WITH_ERRORS,
            ExecutionStatus.CANCELLED,
        ],
    )
    async def test_retry_execution_success(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        mock_temporal_service: Mock,
        execution_status: ExecutionStatus,
    ) -> None:
        """Test successfully retrying a terminal execution."""
        execution = await _create_execution(
            test_db_session, test_workflow, test_user, execution_status=execution_status
        )

        response = await auth_client.post(f"/api/v1/executions/{execution.id}/retry")

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["workflow_id"] == str(execution.workflow_id)
        assert data["workflow_version_id"] == str(execution.workflow_version_id)
        assert data["input_data"] == execution.input_data
        assert data["retried_from_execution_id"] == str(execution.id)
        assert data["status"] == "pending"

        mock_temporal_service.start_workflow.assert_called_once()

    async def test_retry_execution_not_found_returns_404(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that retrying a non-existent execution returns 404."""
        non_existent_id = uuid.uuid4()

        response = await auth_client.post(f"/api/v1/executions/{non_existent_id}/retry")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/resource-not-found",
            title="Execution Not Found",
            detail="The requested execution was not found",
            code="EXECUTION_NOT_FOUND",
            retryable=False,
        )

    @pytest.mark.parametrize(
        "non_terminal_status",
        [
            ExecutionStatus.PENDING,
            ExecutionStatus.RUNNING,
            ExecutionStatus.PAUSED,
        ],
    )
    async def test_retry_non_terminal_execution_returns_409(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        non_terminal_status: ExecutionStatus,
    ) -> None:
        """Test that retrying a non-terminal execution returns 409."""
        execution = await _create_execution(
            test_db_session, test_workflow, test_user, execution_status=non_terminal_status
        )

        response = await auth_client.post(f"/api/v1/executions/{execution.id}/retry")

        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/resource-conflict",
            title="Execution Not Retryable",
            detail=data["detail"],
            code="EXECUTION_NOT_RETRYABLE",
            retryable=False,
        )

    async def test_retry_test_execution_returns_409(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
    ) -> None:
        """Test that retrying a test execution returns 409."""
        execution = await _create_execution(test_db_session, test_workflow, test_user, mode=ExecutionMode.TEST)

        response = await auth_client.post(f"/api/v1/executions/{execution.id}/retry")

        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/resource-conflict",
            title="Execution Not Retryable",
            detail=data["detail"],
            code="EXECUTION_NOT_RETRYABLE",
            retryable=False,
        )
