"""Unit tests for InvocationService._start_builtin_workflows.

Covers the FK write that links an invocation to the builtin "Agent Execution"
execution running it. Cancellation reads that link, so a silently missing write
would leave the Temporal workflow lingering with nothing to notice.
"""

from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.models import Invocation, InvocationStatus
from syntara.agent_orchestrator.services.invocation_service import InvocationService
from syntara.core.models import User


@pytest.fixture
def mock_user() -> MagicMock:
    """Lightweight mock user; _start_builtin_workflows only reads identity."""
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.username = "tester"
    user.__principal_type__ = MagicMock()
    user.__principal_type__.value = "user"
    return user


def _invocation() -> Invocation:
    return Invocation(
        id=uuid4(),
        prompt="summarise the incident report",
        created_by=uuid4(),
        session_id="session-1",
        project_id=uuid4(),
        status=InvocationStatus.CREATED,
        context_data={},
    )


def _execution_service(*, agent_execution_id: object = None) -> Mock:
    """Execution service returning a distinct ExecutionRead per workflow name."""
    service = Mock()
    agent_execution = Mock()
    agent_execution.id = agent_execution_id if agent_execution_id is not None else uuid4()
    conversion_execution = Mock()
    conversion_execution.id = uuid4()

    async def create_execution_by_name(*, workflow_name: str, input_data: dict, project_name: str) -> Mock:
        del input_data, project_name
        return conversion_execution if workflow_name == "Document Conversion" else agent_execution

    service.create_execution_by_name = AsyncMock(side_effect=create_execution_by_name)
    service.agent_execution = agent_execution
    service.conversion_execution = conversion_execution
    return service


@pytest.mark.asyncio
class TestStartBuiltinWorkflowsLinksAgentExecution:
    """The agent execution's id is recorded on the invocation."""

    async def test_links_invocation_to_agent_execution(self, mock_user: MagicMock) -> None:
        """The FK is written from the returned ExecutionRead.id and committed."""
        invocation = _invocation()
        mock_session = AsyncMock()
        execution_service = _execution_service()
        service = InvocationService(mock_session, mock_user, execution_service=execution_service)

        await service._start_builtin_workflows(invocation)

        assert invocation.agent_execution_id == execution_service.agent_execution.id
        mock_session.commit.assert_awaited_once()

    async def test_document_conversion_execution_is_not_linked(self, mock_user: MagicMock) -> None:
        """Only the agent execution is linked; conversions run independently."""
        invocation = _invocation()
        mock_session = AsyncMock()
        execution_service = _execution_service()
        service = InvocationService(mock_session, mock_user, execution_service=execution_service)

        await service._start_builtin_workflows(invocation, file_ids=[str(uuid4())])

        assert invocation.agent_execution_id == execution_service.agent_execution.id
        assert invocation.agent_execution_id != execution_service.conversion_execution.id

    async def test_no_execution_service_writes_nothing(self, mock_user: MagicMock) -> None:
        """Without an execution service there is no workflow and no link."""
        invocation = _invocation()
        mock_session = AsyncMock()
        service = InvocationService(mock_session, mock_user)

        await service._start_builtin_workflows(invocation)

        assert invocation.agent_execution_id is None
        mock_session.commit.assert_not_called()

    async def test_link_failure_does_not_fail_invocation_creation(self, mock_user: MagicMock) -> None:
        """A failed FK commit is swallowed: the workflow is already running.

        The invocation itself is already committed, so raising here would 500 a
        request whose side effects have all happened.
        """
        invocation = _invocation()
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock(side_effect=RuntimeError("connection lost"))
        execution_service = _execution_service()
        service = InvocationService(mock_session, mock_user, execution_service=execution_service)

        await service._start_builtin_workflows(invocation)

        mock_session.rollback.assert_awaited_once()

    async def test_invocation_id_stays_in_execution_input_data(self, mock_user: MagicMock) -> None:
        """input_data keeps invocation_id — it is the builtin trigger binding."""
        invocation = _invocation()
        mock_session = AsyncMock()
        execution_service = _execution_service()
        service = InvocationService(mock_session, mock_user, execution_service=execution_service)

        await service._start_builtin_workflows(invocation)

        agent_call = next(
            call
            for call in execution_service.create_execution_by_name.await_args_list
            if call.kwargs["workflow_name"] == "Agent Execution"
        )
        assert agent_call.kwargs["input_data"]["invocation_id"] == str(invocation.id)
