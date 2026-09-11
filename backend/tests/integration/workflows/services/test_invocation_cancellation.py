"""DB-backed tests for linking invocations to an execution via activity output.

The link is read from ``ActivityExecution.output_data`` — written by the
activity-sync service from the worker's Temporal heartbeat — not from
``Invocation.context_data``, which the invocation-create API accepts verbatim
from the caller. Ref: AAP-88614.

This link is *not* ``Invocation.agent_execution_id``. That FK points the other
way — from an invocation to the builtin workflow running it — and does not
replace this lookup, which answers "which invocations did this user workflow's
agentic nodes start?". Both are needed; do not delete this one.
"""

import uuid
from typing import Any

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models.invocation import InvocationStatus
from syntara.core.models import User
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.services.invocation_cancellation import find_active_invocations_for_execution
from tests.integration.helpers.invocations import InvocationFactory


async def _make_execution(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
) -> Execution:
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
        temporal_workflow_id=f"temporal-{uuid.uuid4()}",
        status=ExecutionStatus.RUNNING,
        created_by=test_user.id,
        input_data={},
        labels={},
        project_id=workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()
    await test_db_session.refresh(execution)
    return execution


async def _link_activity(
    test_db_session: AsyncSession,
    execution: Execution,
    output_data: dict[str, Any],
) -> None:
    """Record an agentic activity's heartbeat output, as the sync service does."""
    activity = ActivityExecution(
        execution_id=execution.id,
        activity_name="agentic_v2",
        node_type="agentic",
        temporal_activity_id=f"activity-{uuid.uuid4()}",
        status=ActivityStatus.RUNNING,
        input_data={},
        output_data=output_data,
    )
    test_db_session.add(activity)
    await test_db_session.commit()


@pytest.mark.asyncio
class TestFindActiveInvocationsForExecution:
    """Lookup resolves invocations through the worker-written activity output."""

    async def test_finds_invocation_linked_by_activity_output(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        invocation_factory: InvocationFactory,
    ) -> None:
        execution = await _make_execution(test_db_session, test_user, test_workflow)
        invocation = await invocation_factory.create(project_id=test_workflow.project_id)
        await _link_activity(test_db_session, execution, {"invocation_id": str(invocation.id)})

        found = await find_active_invocations_for_execution(test_db_session, execution.id)

        assert [inv.id for inv in found] == [invocation.id]

    async def test_ignores_terminal_invocations(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        invocation_factory: InvocationFactory,
    ) -> None:
        execution = await _make_execution(test_db_session, test_user, test_workflow)
        completed = await invocation_factory.create(
            project_id=test_workflow.project_id, status=InvocationStatus.COMPLETED
        )
        await _link_activity(test_db_session, execution, {"invocation_id": str(completed.id)})

        found = await find_active_invocations_for_execution(test_db_session, execution.id)

        assert found == []

    async def test_ignores_caller_supplied_context_data_link(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        invocation_factory: InvocationFactory,
    ) -> None:
        """context_data is caller-writable, so it must not resolve the link."""
        execution = await _make_execution(test_db_session, test_user, test_workflow)
        await invocation_factory.create(
            project_id=test_workflow.project_id,
            context_data={"execution_id": str(execution.id)},
        )

        found = await find_active_invocations_for_execution(test_db_session, execution.id)

        assert found == []

    async def test_ignores_invocation_in_another_project(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        invocation_factory: InvocationFactory,
    ) -> None:
        """Even a valid activity link never crosses a project boundary."""
        from syntara.authz.models.project import Project

        other_project = Project(name=f"other-project-{uuid.uuid4().hex[:8]}", description="Other")
        test_db_session.add(other_project)
        await test_db_session.commit()
        await test_db_session.refresh(other_project)

        execution = await _make_execution(test_db_session, test_user, test_workflow)
        foreign = await invocation_factory.create(project_id=other_project.id)
        await _link_activity(test_db_session, execution, {"invocation_id": str(foreign.id)})

        found = await find_active_invocations_for_execution(test_db_session, execution.id)

        assert found == []

    async def test_ignores_activity_output_without_invocation_id(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        invocation_factory: InvocationFactory,
    ) -> None:
        execution = await _make_execution(test_db_session, test_user, test_workflow)
        await invocation_factory.create(project_id=test_workflow.project_id)
        await _link_activity(test_db_session, execution, {"result": "ok"})

        found = await find_active_invocations_for_execution(test_db_session, execution.id)

        assert found == []

    async def test_malformed_invocation_id_does_not_break_lookup(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        invocation_factory: InvocationFactory,
    ) -> None:
        execution = await _make_execution(test_db_session, test_user, test_workflow)
        invocation = await invocation_factory.create(project_id=test_workflow.project_id)
        await _link_activity(test_db_session, execution, {"invocation_id": "not-a-uuid"})
        await _link_activity(test_db_session, execution, {"invocation_id": str(invocation.id)})

        found = await find_active_invocations_for_execution(test_db_session, execution.id)

        assert [inv.id for inv in found] == [invocation.id]
