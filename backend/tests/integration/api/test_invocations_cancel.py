"""Integration tests for POST /api/v1/invocations/{id}/cancel.

These exist for the dependency-injection wiring. InvocationService only cancels
the builtin workflow running an invocation when it was given a temporal service,
and the cancel route is the one invocation endpoint wired to the provider that
supplies one. Without this test the feature could ship dead — every unit test
passes a temporal service in by hand. Ref: AAP-88614.
"""

import uuid
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models.invocation import Invocation, InvocationStatus
from syntara.core.models import User
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService
from tests.integration.helpers.invocations import InvocationFactory
from tests.integration.helpers.workflow import get_or_create_builtin_agent_workflow


@pytest.fixture
def mock_temporal_service(session_app) -> Generator[Mock, None, None]:
    """Override the temporal service the invocations router injects."""
    from syntara.workflows.executions_router import get_temporal_execution_service

    mock_service = Mock(spec=TemporalExecutionService)
    mock_service.cancel_workflow = AsyncMock()

    async def override_get_temporal_service() -> Mock:
        return mock_service

    session_app.dependency_overrides[get_temporal_execution_service] = override_get_temporal_service

    yield mock_service

    session_app.dependency_overrides.pop(get_temporal_execution_service, None)


async def _make_agent_execution(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    *,
    execution_status: ExecutionStatus = ExecutionStatus.RUNNING,
) -> Execution:
    from sqlmodel import select

    version_id = (
        await test_db_session.exec(
            select(WorkflowVersion.id).where(
                WorkflowVersion.workflow_id == workflow.id,
                WorkflowVersion.version == workflow.current_version,
            )
        )
    ).one()
    execution = Execution(
        workflow_id=workflow.id,
        workflow_version_id=version_id,
        temporal_workflow_id=f"temporal-agent-{uuid.uuid4()}",
        status=execution_status,
        created_by=test_user.id,
        input_data={},
        labels={},
        project_id=workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()
    await test_db_session.refresh(execution)
    return execution


@pytest.mark.asyncio
class TestCancelInvocationCancelsAgentExecution:
    """The cancel route must reach Temporal through the FK."""

    async def test_cancel_invocation_cancels_linked_agent_execution(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        test_workflow_definition: dict[str, Any],
        mock_temporal_service: Mock,
        invocation_factory: InvocationFactory,
    ) -> None:
        """Cancelling an invocation cancels the builtin workflow running it."""
        builtin_workflow = await get_or_create_builtin_agent_workflow(
            test_db_session, test_user, test_workflow_definition
        )
        agent_execution = await _make_agent_execution(test_db_session, test_user, builtin_workflow)
        invocation = await invocation_factory.create(
            project_id=test_workflow.project_id,
            agent_execution_id=agent_execution.id,
        )

        response = await auth_client.post(
            f"/api/v1/invocations/{invocation.id}/cancel", json={"reason": "User cancelled"}
        )
        assert response.status_code == status.HTTP_200_OK

        mock_temporal_service.cancel_workflow.assert_awaited_once_with(
            temporal_workflow_id=agent_execution.temporal_workflow_id
        )
        await test_db_session.refresh(invocation)
        assert invocation.status == InvocationStatus.CANCELLED

    async def test_cancel_invocation_without_link_still_succeeds(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_workflow: Workflow,
        mock_temporal_service: Mock,
        invocation_factory: InvocationFactory,
    ) -> None:
        """An unlinked invocation cancels normally; only the tidy-up is skipped."""
        invocation = await invocation_factory.create(project_id=test_workflow.project_id)

        response = await auth_client.post(
            f"/api/v1/invocations/{invocation.id}/cancel", json={"reason": "User cancelled"}
        )
        assert response.status_code == status.HTTP_200_OK

        mock_temporal_service.cancel_workflow.assert_not_called()
        await test_db_session.refresh(invocation)
        assert invocation.status == InvocationStatus.CANCELLED

    async def test_cancel_invocation_skips_terminal_agent_execution(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        test_workflow_definition: dict[str, Any],
        mock_temporal_service: Mock,
        invocation_factory: InvocationFactory,
    ) -> None:
        """An already-finished execution is left alone."""
        builtin_workflow = await get_or_create_builtin_agent_workflow(
            test_db_session, test_user, test_workflow_definition
        )
        agent_execution = await _make_agent_execution(
            test_db_session, test_user, builtin_workflow, execution_status=ExecutionStatus.COMPLETED
        )
        invocation = await invocation_factory.create(
            project_id=test_workflow.project_id,
            agent_execution_id=agent_execution.id,
        )

        response = await auth_client.post(
            f"/api/v1/invocations/{invocation.id}/cancel", json={"reason": "User cancelled"}
        )
        assert response.status_code == status.HTTP_200_OK

        mock_temporal_service.cancel_workflow.assert_not_called()

    async def test_temporal_failure_does_not_fail_the_cancel(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        test_workflow_definition: dict[str, Any],
        mock_temporal_service: Mock,
        invocation_factory: InvocationFactory,
    ) -> None:
        """The status change already committed; a Temporal error must not 500.

        A client retrying after a 500 would get NOT_CANCELLABLE instead.
        """
        mock_temporal_service.cancel_workflow = AsyncMock(side_effect=RuntimeError("temporal unreachable"))
        builtin_workflow = await get_or_create_builtin_agent_workflow(
            test_db_session, test_user, test_workflow_definition
        )
        agent_execution = await _make_agent_execution(test_db_session, test_user, builtin_workflow)
        invocation = await invocation_factory.create(
            project_id=test_workflow.project_id,
            agent_execution_id=agent_execution.id,
        )

        response = await auth_client.post(
            f"/api/v1/invocations/{invocation.id}/cancel", json={"reason": "User cancelled"}
        )
        assert response.status_code == status.HTTP_200_OK

        await test_db_session.refresh(invocation)
        assert invocation.status == InvocationStatus.CANCELLED


@pytest.mark.asyncio
class TestInvocationCancelEndToEnd:
    """Create then cancel an invocation against a real database and Temporal.

    The rest of this module mocks the temporal service to inspect the call. This
    class does not, so the FK is proven to actually persist through the ORM
    against the real schema — the write happens in a second commit after the
    invocation's own, which no mocked-session test can really exercise — and the
    cancel route is proven to run end to end against a real Temporal client.

    It deliberately does not assert the builtin workflow reaches CANCELED: the
    mocked LLM returns instantly, so the workflow has usually COMPLETED before
    the cancel arrives, and such an assertion would pass either way. That the
    right workflow id is handed to Temporal is asserted above with a mock;
    confirming Temporal's own reaction to a cancel is not this change's business.
    """

    async def test_created_invocation_is_linked_to_its_agent_execution(
        self,
        auth_client_with_mocked_llm: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: str,
    ) -> None:
        """agent_execution_id is populated server-side by POST /invocations."""
        create = await auth_client_with_mocked_llm.post(
            "/api/v1/invocations",
            json={
                "prompt": "summarise the incident report",
                "session_id": f"e2e-{uuid.uuid4()}",
                "project_id": str(test_project_id),
            },
        )
        assert create.status_code == status.HTTP_202_ACCEPTED
        invocation_id = uuid.UUID(create.json()["id"])

        invocation = await test_db_session.get(Invocation, invocation_id)
        assert invocation is not None
        await test_db_session.refresh(invocation)
        assert invocation.agent_execution_id is not None, "server did not link the agent execution"

        # The link must point at the builtin Agent Execution workflow's execution.
        agent_execution = await test_db_session.get(Execution, invocation.agent_execution_id)
        assert agent_execution is not None
        workflow = await test_db_session.get(Workflow, agent_execution.workflow_id)
        assert workflow is not None
        assert workflow.name == "Agent Execution"
        assert workflow.is_builtin is True

    async def test_cancel_uses_the_link_against_a_real_temporal_client(
        self,
        auth_client_with_mocked_llm: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: str,
    ) -> None:
        """The cancel route completes against a real Temporal client."""
        create = await auth_client_with_mocked_llm.post(
            "/api/v1/invocations",
            json={
                "prompt": "summarise the incident report",
                "session_id": f"e2e-{uuid.uuid4()}",
                "project_id": str(test_project_id),
            },
        )
        assert create.status_code == status.HTTP_202_ACCEPTED
        invocation_id = uuid.UUID(create.json()["id"])

        cancel = await auth_client_with_mocked_llm.post(
            f"/api/v1/invocations/{invocation_id}/cancel",
            json={"reason": "e2e cancel"},
        )
        assert cancel.status_code == status.HTTP_200_OK

        invocation = await test_db_session.get(Invocation, invocation_id)
        assert invocation is not None
        await test_db_session.refresh(invocation)
        assert invocation.status == InvocationStatus.CANCELLED
