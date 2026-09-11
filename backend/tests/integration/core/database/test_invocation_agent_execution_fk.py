"""FK rules for invocations.agent_execution_id on the live, migrated schema.

``executions_workflow_id_fkey`` is ON DELETE CASCADE (migration 7367ba3d8ccb),
so a workflow hard-delete purges its executions. A default NO ACTION FK from
invocations would turn that purge into an IntegrityError, which is why the
column is declared ``ondelete="SET NULL"``.

``confdeltype`` is read from ``pg_constraint`` rather than from SQLAlchemy
model metadata, so a hand-written migration declaring a different rule than the
model would still be caught. Precedent: ``test_user_group_delete_fk_constraints.py``.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.models.execution import ExecutionStatus
from syntara.workflows.services.workflow_service import WorkflowService
from tests.integration.helpers.execution import ExecutionFactory
from tests.integration.helpers.invocations import InvocationFactory
from tests.integration.helpers.workflow import WorkflowFactory


async def _agent_execution_id(session: AsyncSession, invocation_id: uuid.UUID) -> uuid.UUID | None:
    result = await session.exec(
        text("SELECT agent_execution_id FROM invocations WHERE id = :iid").bindparams(iid=invocation_id)  # type: ignore[call-overload]
    )
    return result.scalar_one()


@pytest.mark.asyncio
class TestInvocationAgentExecutionForeignKey:
    """The FK must survive the execution rows disappearing underneath it."""

    async def test_fk_is_declared_set_null(self, test_db_session: AsyncSession) -> None:
        """'n' = SET NULL in pg_constraint.confdeltype."""
        result = await test_db_session.exec(
            text(
                "SELECT confdeltype::text FROM pg_constraint "
                "WHERE conrelid = CAST('invocations' AS regclass) "
                "AND conname = 'invocations_agent_execution_id_fkey'"
            )  # type: ignore[call-overload]
        )
        assert result.scalar_one_or_none() == "n"

    async def test_workflow_hard_delete_nulls_the_link(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        workflow_factory: WorkflowFactory,
        execution_factory: ExecutionFactory,
        invocation_factory: InvocationFactory,
    ) -> None:
        """Deleting a workflow cascades to its executions without an IntegrityError."""
        workflow, version = await workflow_factory.create()
        execution = await execution_factory.create(workflow, version, status=ExecutionStatus.COMPLETED)
        invocation = await invocation_factory.create(
            project_id=workflow.project_id,
            agent_execution_id=execution.id,
            commit=False,
        )
        await test_db_session.commit()

        service = WorkflowService(test_db_session, test_user)
        await service.delete_workflow(workflow.id)
        await test_db_session.commit()

        assert await _agent_execution_id(test_db_session, invocation.id) is None
