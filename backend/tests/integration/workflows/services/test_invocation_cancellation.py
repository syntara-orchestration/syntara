"""DB-backed tests for finding invocations by execution_id JSONB."""

from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models.invocation import Invocation, InvocationStatus
from syntara.core.models import User
from syntara.workflows.services.invocation_cancellation import find_active_invocations_for_execution


def _invocation(
    *,
    user: User,
    project_id: UUID,
    status: InvocationStatus,
    context_data: dict[str, object],
) -> Invocation:
    return Invocation(
        prompt="test prompt",
        created_by=user.id,
        project_id=project_id,
        session_id=f"session-{uuid4()}",
        status=status,
        context_data=context_data,
    )


@pytest.mark.asyncio
async def test_find_active_invocations_matches_top_level_execution_id(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    execution_id = uuid4()
    matching = _invocation(
        user=test_user,
        project_id=test_project_id,
        status=InvocationStatus.RUNNING,
        context_data={"execution_id": str(execution_id)},
    )
    completed = _invocation(
        user=test_user,
        project_id=test_project_id,
        status=InvocationStatus.COMPLETED,
        context_data={"execution_id": str(execution_id)},
    )
    nested_only = _invocation(
        user=test_user,
        project_id=test_project_id,
        status=InvocationStatus.RUNNING,
        context_data={"metadata": {"execution_id": str(execution_id)}},
    )
    other_execution = _invocation(
        user=test_user,
        project_id=test_project_id,
        status=InvocationStatus.CREATED,
        context_data={"execution_id": str(uuid4())},
    )
    test_db_session.add_all([matching, completed, nested_only, other_execution])
    await test_db_session.commit()

    found = await find_active_invocations_for_execution(test_db_session, execution_id)

    assert [inv.id for inv in found] == [matching.id]
