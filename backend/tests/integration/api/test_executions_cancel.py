"""Integration tests for POST /api/v1/executions/{id}/cancel endpoint."""

import uuid
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models.invocation import Invocation, InvocationStatus
from syntara.core.models import User
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
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


async def _version_id(test_db_session: AsyncSession, workflow: Workflow) -> uuid.UUID:
    result = await test_db_session.exec(
        select(WorkflowVersion.id).where(
            WorkflowVersion.workflow_id == workflow.id,
            WorkflowVersion.version == workflow.current_version,
        )
    )
    return result.one()


async def _make_execution(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    *,
    input_data: dict[str, Any] | None = None,
    prefix: str = "temporal",
) -> Execution:
    execution = Execution(
        workflow_id=workflow.id,
        workflow_version_id=await _version_id(test_db_session, workflow),
        temporal_workflow_id=f"{prefix}-{uuid.uuid4()}",
        status=ExecutionStatus.RUNNING,
        created_by=test_user.id,
        input_data=input_data or {},
        labels={},
        project_id=workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()
    await test_db_session.refresh(execution)
    return execution


async def _make_invocation(
    test_db_session: AsyncSession,
    test_user: User,
    project_id: uuid.UUID,
    *,
    status: InvocationStatus = InvocationStatus.RUNNING,
    context_data: dict[str, Any] | None = None,
) -> Invocation:
    invocation = Invocation(
        created_by=test_user.id,
        prompt="summarise the incident report",
        session_id=f"session-{uuid.uuid4()}",
        project_id=project_id,
        status=status,
        context_data=context_data or {},
    )
    test_db_session.add(invocation)
    await test_db_session.commit()
    await test_db_session.refresh(invocation)
    return invocation


async def _link_activity(
    test_db_session: AsyncSession,
    execution: Execution,
    invocation: Invocation,
) -> None:
    """Record the agentic activity's heartbeat output, as the sync service does."""
    activity = ActivityExecution(
        execution_id=execution.id,
        activity_name="agentic_v2",
        node_type="agentic",
        temporal_activity_id=f"activity-{uuid.uuid4()}",
        status=ActivityStatus.RUNNING,
        input_data={},
        output_data={"invocation_id": str(invocation.id)},
    )
    test_db_session.add(activity)
    await test_db_session.commit()


@pytest.mark.asyncio
class TestCancelExecutionPropagatesToInvocation:
    """Cancelling an execution must stop the agent work it spawned.

    The agentic node completes asynchronously (``raise_complete_async``) and the
    agent loop runs in a separate builtin AGENT_EXECUTION workflow. The only
    mechanism that stops an in-flight invocation is the planner's DB poll on
    ``Invocation.status == CANCELLED``, so cancelling the user's execution must
    write that status. Ref: AAP-88614.

    The link is read from ``ActivityExecution.output_data`` (written by the
    activity-sync service from the worker's heartbeat), never from
    caller-supplied ``Invocation.context_data``.
    """

    @pytest.mark.parametrize(
        "invocation_status",
        [InvocationStatus.RUNNING, InvocationStatus.CREATED],
    )
    async def test_cancel_execution_cancels_linked_invocation(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        mock_temporal_service: Mock,
        invocation_status: InvocationStatus,
    ) -> None:
        """Cancelling an execution marks its in-flight invocation CANCELLED."""
        execution = await _make_execution(test_db_session, test_user, test_workflow)
        invocation = await _make_invocation(
            test_db_session, test_user, test_workflow.project_id, status=invocation_status
        )
        await _link_activity(test_db_session, execution, invocation)

        response = await auth_client.post(f"/api/v1/executions/{execution.id}/cancel")
        assert response.status_code == status.HTTP_202_ACCEPTED

        await test_db_session.refresh(invocation)
        assert invocation.status == InvocationStatus.CANCELLED
        assert invocation.completed_at is not None

    async def test_cancel_execution_ignores_caller_supplied_context_data_link(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        mock_temporal_service: Mock,
    ) -> None:
        """context_data is caller-writable and must not drive cancellation.

        Any caller of the invocation-create API can put an arbitrary
        ``execution_id`` in ``context_data``; honouring it would let one
        tenant's cancellation reach another tenant's invocation.
        """
        execution = await _make_execution(test_db_session, test_user, test_workflow)
        forged = await _make_invocation(
            test_db_session,
            test_user,
            test_workflow.project_id,
            context_data={"execution_id": str(execution.id)},
        )

        response = await auth_client.post(f"/api/v1/executions/{execution.id}/cancel")
        assert response.status_code == status.HTTP_202_ACCEPTED

        await test_db_session.refresh(forged)
        assert forged.status == InvocationStatus.RUNNING

    async def test_cancel_execution_ignores_invocation_in_another_project(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        mock_temporal_service: Mock,
    ) -> None:
        """Cancellation never crosses a project boundary."""
        from syntara.authz.models.project import Project

        other_project = Project(name=f"other-project-{uuid.uuid4().hex[:8]}", description="Other")
        test_db_session.add(other_project)
        await test_db_session.commit()
        await test_db_session.refresh(other_project)

        execution = await _make_execution(test_db_session, test_user, test_workflow)
        foreign = await _make_invocation(test_db_session, test_user, other_project.id)
        await _link_activity(test_db_session, execution, foreign)

        response = await auth_client.post(f"/api/v1/executions/{execution.id}/cancel")
        assert response.status_code == status.HTTP_202_ACCEPTED

        await test_db_session.refresh(foreign)
        assert foreign.status == InvocationStatus.RUNNING

    async def test_cancel_execution_leaves_unlinked_invocation_untouched(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        mock_temporal_service: Mock,
    ) -> None:
        """Only invocations this execution actually reported are affected."""
        execution = await _make_execution(test_db_session, test_user, test_workflow)
        unrelated = await _make_invocation(test_db_session, test_user, test_workflow.project_id)

        response = await auth_client.post(f"/api/v1/executions/{execution.id}/cancel")
        assert response.status_code == status.HTTP_202_ACCEPTED

        await test_db_session.refresh(unrelated)
        assert unrelated.status == InvocationStatus.RUNNING


@pytest.mark.asyncio
class TestCancelExecutionCancelsBuiltinAgentExecution:
    """The builtin AGENT_EXECUTION workflow must be cancelled with the invocation.

    It is what actually runs the agent loop; leaving it running orphans the
    Temporal workflow. Ref: AAP-88614.
    """

    async def _builtin_agent_workflow(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow_definition: dict[str, Any],
    ) -> Workflow:
        """Resolve the builtin "Agent Execution" workflow, seeding it if absent.

        seed_builtin normally creates it; look it up so this works either way.
        """
        from syntara.authz.models.project import Project
        from syntara.workflows.constants import BUILTIN_PROJECT_NAME, BUILTIN_WORKFLOW_AGENT_EXECUTION

        project_result = await test_db_session.exec(select(Project).where(Project.name == BUILTIN_PROJECT_NAME))
        project = project_result.first()
        if project is None:
            project = Project(name=BUILTIN_PROJECT_NAME, description="Built-in", is_builtin=True)
            test_db_session.add(project)
            await test_db_session.commit()
            await test_db_session.refresh(project)

        workflow_result = await test_db_session.exec(
            select(Workflow).where(
                Workflow.name == BUILTIN_WORKFLOW_AGENT_EXECUTION,
                Workflow.project_id == project.id,
            )
        )
        existing = workflow_result.first()
        if existing is not None:
            return existing

        workflow = Workflow(
            name=BUILTIN_WORKFLOW_AGENT_EXECUTION,
            description="Builtin agent execution",
            created_by=test_user.id,
            is_enabled=False,
            is_builtin=True,
            current_version=1,
            project_id=project.id,
        )
        test_db_session.add(workflow)
        version = WorkflowVersion(
            workflow_id=workflow.id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=test_workflow_definition,
            created_by=test_user.id,
        )
        test_db_session.add(version)
        await test_db_session.flush()
        workflow.published_version_id = version.id
        workflow.is_enabled = True
        await test_db_session.commit()
        await test_db_session.refresh(workflow)
        return workflow

    async def test_cancel_execution_cancels_builtin_agent_execution(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        test_workflow_definition: dict[str, Any],
        mock_temporal_service: Mock,
    ) -> None:
        """The builtin agent execution's Temporal workflow is cancelled too."""
        execution = await _make_execution(test_db_session, test_user, test_workflow)
        invocation = await _make_invocation(test_db_session, test_user, test_workflow.project_id)
        await _link_activity(test_db_session, execution, invocation)

        builtin_workflow = await self._builtin_agent_workflow(test_db_session, test_user, test_workflow_definition)
        agent_execution = await _make_execution(
            test_db_session,
            test_user,
            builtin_workflow,
            input_data={"invocation_id": str(invocation.id)},
            prefix="temporal-agent",
        )

        response = await auth_client.post(f"/api/v1/executions/{execution.id}/cancel")
        assert response.status_code == status.HTTP_202_ACCEPTED

        cancelled = {
            call.kwargs["temporal_workflow_id"] for call in mock_temporal_service.cancel_workflow.call_args_list
        }
        assert agent_execution.temporal_workflow_id in cancelled

    async def test_cancel_execution_does_not_cancel_non_builtin_claimant(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        mock_temporal_service: Mock,
    ) -> None:
        """input_data is caller-supplied, so only the builtin workflow is targeted.

        An ordinary execution whose input happens to name the invocation must
        not be cancelled alongside it.
        """
        execution = await _make_execution(test_db_session, test_user, test_workflow)
        invocation = await _make_invocation(test_db_session, test_user, test_workflow.project_id)
        await _link_activity(test_db_session, execution, invocation)

        impostor = await _make_execution(
            test_db_session,
            test_user,
            test_workflow,
            input_data={"invocation_id": str(invocation.id)},
            prefix="temporal-impostor",
        )

        response = await auth_client.post(f"/api/v1/executions/{execution.id}/cancel")
        assert response.status_code == status.HTTP_202_ACCEPTED

        cancelled = {
            call.kwargs["temporal_workflow_id"] for call in mock_temporal_service.cancel_workflow.call_args_list
        }
        assert impostor.temporal_workflow_id not in cancelled
