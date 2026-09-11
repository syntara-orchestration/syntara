"""Integration tests for the invocations.agent_execution_id backfill.

Tests the custom SQL from migration d5b8c2f04e71, which populates the new FK
from the legacy ``executions.input_data->>'invocation_id'`` link.

``make check-migrations`` only round-trips migrations against an *empty*
database, so the backfill statement is never exercised there. This is the only
coverage it has.

The SQL is copied verbatim from the migration into ``_BACKFILL_SQL`` below and
run against the live schema, following the pattern of
``test_config_to_parameters_migration.py``.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models.invocation import Invocation
from syntara.authz.models.project import Project
from syntara.core.models import User
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from tests.helpers.workflow import create_minimal_workflow_definition
from tests.integration.helpers.invocations import InvocationFactory

# The exact SQL from the alembic migration upgrade()
_BACKFILL_SQL = """
UPDATE invocations AS i
SET agent_execution_id = picked.execution_id
FROM (
    SELECT DISTINCT ON (((e.input_data ->> 'invocation_id')::uuid))
           (e.input_data ->> 'invocation_id')::uuid AS invocation_id,
           e.id                                     AS execution_id
    FROM executions AS e
    JOIN workflows  AS w ON w.id = e.workflow_id
    JOIN projects   AS p ON p.id = w.project_id
    WHERE w.name = 'Agent Execution' AND w.is_builtin IS TRUE
      AND p.name = 'built-in'        AND p.is_builtin IS TRUE
      AND e.input_data ->> 'invocation_id' ~*
          '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    ORDER BY ((e.input_data ->> 'invocation_id')::uuid),
             (e.status::text IN ('completed','completed_with_errors','failed','cancelled')) ASC,
             e.created_at DESC
) AS picked
WHERE i.id = picked.invocation_id
  AND i.agent_execution_id IS NULL
  AND EXISTS (SELECT 1 FROM executions e2
              WHERE e2.id = picked.execution_id AND e2.created_at >= i.created_at);
"""


async def _make_workflow(
    session: AsyncSession,
    user: User,
    *,
    name: str,
    project_name: str,
    workflow_builtin: bool,
    project_builtin: bool,
) -> Workflow:
    """Create a workflow under a project, both with configurable is_builtin."""
    result = await session.exec(text("SELECT id FROM projects WHERE name = :name").bindparams(name=project_name))  # type: ignore[call-overload]
    existing_project_id = result.scalar_one_or_none()
    if existing_project_id is None:
        project = Project(name=project_name, description="backfill test", is_builtin=project_builtin)
        session.add(project)
        await session.flush()
        project_id = project.id
    else:
        project_id = existing_project_id

    workflow = Workflow(
        name=name,
        created_by=user.id,
        is_enabled=False,
        is_builtin=workflow_builtin,
        current_version=1,
        project_id=project_id,
    )
    session.add(workflow)
    version = WorkflowVersion(
        workflow_id=workflow.id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=create_minimal_workflow_definition(name=name),
        created_by=user.id,
    )
    session.add(version)
    await session.flush()
    workflow.published_version_id = version.id
    workflow.is_enabled = True
    await session.flush()
    return workflow


async def _make_execution(
    session: AsyncSession,
    user: User,
    workflow: Workflow,
    *,
    invocation_id: str | None,
    status: ExecutionStatus = ExecutionStatus.RUNNING,
    created_at: datetime | None = None,
) -> Execution:
    result = await session.exec(
        text("SELECT id FROM workflow_versions WHERE workflow_id = :wf").bindparams(wf=workflow.id)  # type: ignore[call-overload]
    )
    version_id = result.scalar_one()
    execution = Execution(
        workflow_id=workflow.id,
        workflow_version_id=version_id,
        temporal_workflow_id=f"temporal-{uuid.uuid4()}",
        status=status,
        created_by=user.id,
        input_data={} if invocation_id is None else {"invocation_id": invocation_id},
        labels={},
        project_id=workflow.project_id,
    )
    session.add(execution)
    await session.flush()
    if created_at is not None:
        await session.exec(
            text("UPDATE executions SET created_at = :ts WHERE id = :eid").bindparams(  # type: ignore[call-overload]
                ts=created_at, eid=execution.id
            )
        )
    return execution


async def _run_backfill(session: AsyncSession) -> None:
    await session.exec(text(_BACKFILL_SQL))  # type: ignore[call-overload]
    await session.flush()


async def _agent_execution_id(session: AsyncSession, invocation: Invocation) -> uuid.UUID | None:
    result = await session.exec(
        text("SELECT agent_execution_id FROM invocations WHERE id = :iid").bindparams(iid=invocation.id)  # type: ignore[call-overload]
    )
    return result.scalar_one()


@pytest.fixture
async def builtin_agent_workflow(test_db_session: AsyncSession, test_user: User) -> Workflow:
    """The builtin "Agent Execution" workflow in the builtin project."""
    return await _make_workflow(
        test_db_session,
        test_user,
        name="Agent Execution",
        project_name="built-in",
        workflow_builtin=True,
        project_builtin=True,
    )


@pytest.mark.asyncio
class TestInvocationAgentExecutionBackfill:
    """The backfill resolves the legacy JSONB link into the new FK."""

    async def test_links_invocation_to_builtin_agent_execution(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        invocation_factory: InvocationFactory,
        builtin_agent_workflow: Workflow,
    ) -> None:
        """Happy path: the builtin execution claiming an invocation is linked."""
        invocation = await invocation_factory.create(commit=False)
        execution = await _make_execution(
            test_db_session, test_user, builtin_agent_workflow, invocation_id=str(invocation.id)
        )

        await _run_backfill(test_db_session)

        assert await _agent_execution_id(test_db_session, invocation) == execution.id

    async def test_ignores_non_builtin_claimant(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        invocation_factory: InvocationFactory,
    ) -> None:
        """input_data was caller-writable, so an ordinary workflow cannot claim.

        This is the persisted form of the runtime is_builtin guard that
        ``_cancel_agent_execution_for_invocation`` used to apply on every cancel.
        """
        impostor_workflow = await _make_workflow(
            test_db_session,
            test_user,
            name="Agent Execution",
            project_name=f"not-builtin-{uuid.uuid4().hex[:8]}",
            workflow_builtin=False,
            project_builtin=False,
        )
        invocation = await invocation_factory.create(commit=False)
        await _make_execution(test_db_session, test_user, impostor_workflow, invocation_id=str(invocation.id))

        await _run_backfill(test_db_session)

        assert await _agent_execution_id(test_db_session, invocation) is None

    async def test_ignores_builtin_named_workflow_in_other_project(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        invocation_factory: InvocationFactory,
    ) -> None:
        """A workflow flagged builtin but outside the builtin project is ignored."""
        other_workflow = await _make_workflow(
            test_db_session,
            test_user,
            name="Agent Execution",
            project_name=f"other-builtin-{uuid.uuid4().hex[:8]}",
            workflow_builtin=True,
            project_builtin=True,
        )
        invocation = await invocation_factory.create(commit=False)
        await _make_execution(test_db_session, test_user, other_workflow, invocation_id=str(invocation.id))

        await _run_backfill(test_db_session)

        assert await _agent_execution_id(test_db_session, invocation) is None

    async def test_tolerates_malformed_invocation_id(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        invocation_factory: InvocationFactory,
        builtin_agent_workflow: Workflow,
    ) -> None:
        """A non-uuid historical value must not abort the whole migration.

        Without the regex guard the ``::uuid`` cast raises and every other row
        is left unlinked.
        """
        await _make_execution(test_db_session, test_user, builtin_agent_workflow, invocation_id="not-a-uuid")
        invocation = await invocation_factory.create(commit=False)
        execution = await _make_execution(
            test_db_session, test_user, builtin_agent_workflow, invocation_id=str(invocation.id)
        )

        await _run_backfill(test_db_session)

        assert await _agent_execution_id(test_db_session, invocation) == execution.id

    async def test_picks_newest_non_terminal_execution_deterministically(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        invocation_factory: InvocationFactory,
        builtin_agent_workflow: Workflow,
    ) -> None:
        """Retries leave several claimants; the live one wins, newest first."""
        invocation = await invocation_factory.create(commit=False)
        base = datetime.now(UTC)
        await _make_execution(
            test_db_session,
            test_user,
            builtin_agent_workflow,
            invocation_id=str(invocation.id),
            status=ExecutionStatus.FAILED,
            created_at=base + timedelta(minutes=10),
        )
        await _make_execution(
            test_db_session,
            test_user,
            builtin_agent_workflow,
            invocation_id=str(invocation.id),
            status=ExecutionStatus.RUNNING,
            created_at=base + timedelta(minutes=1),
        )
        newest_live = await _make_execution(
            test_db_session,
            test_user,
            builtin_agent_workflow,
            invocation_id=str(invocation.id),
            status=ExecutionStatus.RUNNING,
            created_at=base + timedelta(minutes=5),
        )

        await _run_backfill(test_db_session)

        assert await _agent_execution_id(test_db_session, invocation) == newest_live.id

    async def test_ignores_execution_created_before_the_invocation(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        invocation_factory: InvocationFactory,
        builtin_agent_workflow: Workflow,
    ) -> None:
        """A forged id pointing at an older execution must not link."""
        older = await _make_execution(
            test_db_session,
            test_user,
            builtin_agent_workflow,
            invocation_id=None,
            created_at=datetime.now(UTC) - timedelta(days=1),
        )
        invocation = await invocation_factory.create(commit=False)
        await test_db_session.exec(
            text("UPDATE executions SET input_data = CAST(:new_data AS jsonb) WHERE id = :eid").bindparams(  # type: ignore[call-overload]
                new_data=f'{{"invocation_id": "{invocation.id}"}}', eid=older.id
            )
        )

        await _run_backfill(test_db_session)

        assert await _agent_execution_id(test_db_session, invocation) is None

    async def test_is_idempotent(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        invocation_factory: InvocationFactory,
        builtin_agent_workflow: Workflow,
    ) -> None:
        """Re-running never moves an already-populated link."""
        invocation = await invocation_factory.create(commit=False)
        execution = await _make_execution(
            test_db_session, test_user, builtin_agent_workflow, invocation_id=str(invocation.id)
        )

        await _run_backfill(test_db_session)
        first = await _agent_execution_id(test_db_session, invocation)
        await _run_backfill(test_db_session)

        assert first == execution.id
        assert await _agent_execution_id(test_db_session, invocation) == execution.id
