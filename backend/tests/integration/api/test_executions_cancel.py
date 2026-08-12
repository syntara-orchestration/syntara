"""Integration tests for POST /api/v1/executions/{id}/cancel endpoint."""

import uuid
from collections.abc import Generator
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService
from tests.integration.helpers.error_data import assert_error_data


@pytest.fixture
def mock_temporal_service(session_app) -> Generator[Mock, None, None]:
    """Override temporal service dependency with a mock."""
    from syntara.workflows.executions_router import get_temporal_execution_service

    mock_service = Mock(spec=TemporalExecutionService)
    mock_service.cancel_workflow = AsyncMock()

    async def override_get_temporal_service() -> Mock:
        return mock_service

    session_app.dependency_overrides[get_temporal_execution_service] = override_get_temporal_service

    yield mock_service

    session_app.dependency_overrides.pop(get_temporal_execution_service, None)


@pytest.mark.asyncio
class TestCancelExecution:
    """Integration tests for POST /executions/{execution_id}/cancel."""

    async def test_cancel_execution_success_running(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        mock_temporal_service: Mock,
    ) -> None:
        """Test successfully cancelling a RUNNING execution."""
        result = await test_db_session.exec(
            select(WorkflowVersion.id).where(
                WorkflowVersion.workflow_id == test_workflow.id,
                WorkflowVersion.version == test_workflow.current_version,
            )
        )
        version_id = result.one()

        execution = Execution(
            workflow_id=test_workflow.id,
            workflow_version_id=version_id,
            temporal_workflow_id=f"temporal-{uuid.uuid4()}",
            status=ExecutionStatus.RUNNING,
            created_by=test_user.id,
            input_data={},
            labels={},
            project_id=test_workflow.project_id,
        )
        test_db_session.add(execution)
        await test_db_session.commit()
        await test_db_session.refresh(execution)

        response = await auth_client.post(f"/api/v1/executions/{execution.id}/cancel")

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.content == b""

        mock_temporal_service.cancel_workflow.assert_called_once_with(
            temporal_workflow_id=execution.temporal_workflow_id
        )

    async def test_cancel_execution_success_pending(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        mock_temporal_service: Mock,
    ) -> None:
        """Test successfully cancelling a PENDING execution."""
        result = await test_db_session.exec(
            select(WorkflowVersion.id).where(
                WorkflowVersion.workflow_id == test_workflow.id,
                WorkflowVersion.version == test_workflow.current_version,
            )
        )
        version_id = result.one()

        execution = Execution(
            workflow_id=test_workflow.id,
            workflow_version_id=version_id,
            temporal_workflow_id=f"temporal-{uuid.uuid4()}",
            status=ExecutionStatus.PENDING,
            created_by=test_user.id,
            input_data={},
            labels={},
            project_id=test_workflow.project_id,
        )
        test_db_session.add(execution)
        await test_db_session.commit()
        await test_db_session.refresh(execution)

        response = await auth_client.post(f"/api/v1/executions/{execution.id}/cancel")

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.content == b""

        mock_temporal_service.cancel_workflow.assert_called_once_with(
            temporal_workflow_id=execution.temporal_workflow_id
        )

    async def test_cancel_execution_not_found_returns_404(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that cancelling non-existent execution returns 404."""
        non_existent_id = uuid.uuid4()

        response = await auth_client.post(f"/api/v1/executions/{non_existent_id}/cancel")

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
        "terminal_status",
        [
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        ],
    )
    async def test_cancel_execution_terminal_state_returns_400(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        terminal_status: ExecutionStatus,
    ) -> None:
        """Test that cancelling execution in terminal state returns 400."""
        result = await test_db_session.exec(
            select(WorkflowVersion.id).where(
                WorkflowVersion.workflow_id == test_workflow.id,
                WorkflowVersion.version == test_workflow.current_version,
            )
        )
        version_id = result.one()

        execution = Execution(
            workflow_id=test_workflow.id,
            workflow_version_id=version_id,
            temporal_workflow_id=f"temporal-{uuid.uuid4()}",
            status=terminal_status,
            created_by=test_user.id,
            input_data={},
            labels={},
            project_id=test_workflow.project_id,
        )
        test_db_session.add(execution)
        await test_db_session.commit()
        await test_db_session.refresh(execution)

        response = await auth_client.post(f"/api/v1/executions/{execution.id}/cancel")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Execution In Terminal State",
            detail=f"Cannot cancel execution in {terminal_status.value} state",
            code="EXECUTION_TERMINAL_STATE",
            retryable=False,
        )

    async def test_cancel_execution_with_invalid_uuid_returns_422(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that invalid UUID format returns 422 validation error."""
        response = await auth_client.post("/api/v1/executions/not-a-uuid/cancel")

        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"

        data = response.json()
        assert data["type"] == "https://api.example.com/errors/validation-error"
        assert data["code"] == "REQUEST_VALIDATION_ERROR"
        assert data["retryable"] is False
