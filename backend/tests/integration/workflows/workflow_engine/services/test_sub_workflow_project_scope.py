"""Same-project isolation for sub-workflow invocation (DB-backed).

The setup activity rejects a sub-workflow whose child workflow is not in the parent
execution's project, before any child Execution is created. These tests exercise
``SubWorkflowSetupActivity.run`` against the real alembic-built schema and verify the
actual database state after rejection.

Scope: project isolation ONLY. Execute-permission (RBAC, AC-3) is out of scope and
tracked under AAP-91266.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4, uuid5

import pytest
from temporalio.exceptions import ApplicationError

from syntara.authz.models.project import Project
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.activities.sub_workflow_setup_activity import (
    _SUB_WORKFLOW_NAMESPACE,
    SubWorkflowSetupActivity,
)
from tests.integration.helpers.subworkflow import seed_parent_execution

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User

_TASK_QUEUE = "sub-wf-project-scope"
_SCOPE_ERROR = "SubWorkflowProjectScopeError"
_NODE_ID = "sub_wf_node"


def _child_def() -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": "child_trigger", "type": "subworkflow_trigger", "parameters": {}}],
        "nodes": [{"id": "child_script", "type": "script", "parameters": {"language": "bash", "code": "echo ok"}}],
        "edges": [{"from": "child_trigger", "to": "child_script"}],
    }


async def _create_published_child(session: AsyncSession, *, created_by: UUID, project_id: UUID) -> tuple[UUID, UUID]:
    """Create an enabled, published child workflow. Returns (workflow_id, version_id)."""
    workflow_id = uuid4()
    session.add(
        Workflow(id=workflow_id, name=f"child-{workflow_id.hex[:8]}", created_by=created_by, project_id=project_id)
    )
    await session.flush()
    version_id = uuid4()
    session.add(
        WorkflowVersion(
            id=version_id,
            workflow_id=workflow_id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=_child_def(),
            created_by=created_by,
        )
    )
    await session.flush()
    workflow = await session.get(Workflow, workflow_id)
    assert workflow is not None
    workflow.is_enabled = True
    workflow.published_version_id = version_id
    await session.commit()
    return workflow_id, version_id


async def _make_project(session: AsyncSession) -> UUID:
    project = Project(name=f"scope-proj-{uuid4().hex[:8]}", description="cross-project scope test")
    session.add(project)
    await session.flush()
    return project.id


def _params(workflow_id: UUID) -> dict[str, Any]:
    return {"workflow_id": str(workflow_id), "trigger_node_id": "child_trigger", "input_mapping": {}}


def _child_id(parent_execution_id: str, invocation_id: str = _NODE_ID) -> UUID:
    return uuid5(_SUB_WORKFLOW_NAMESPACE, f"{parent_execution_id}:{invocation_id}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_same_project_creates_and_persists_child(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """A same-project parent and child create and persist a child Execution."""
    child_wf_id, _ = await _create_published_child(test_db_session, created_by=test_user.id, project_id=test_project_id)
    parent_exec = str(await seed_parent_execution(test_db_session, created_by=test_user.id, project_id=test_project_id))
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)

    result = await setup.run(_params(child_wf_id), parent_exec, _NODE_ID, str(test_user.id), 0)

    assert result["execution_id"] == str(_child_id(parent_exec))
    async with test_db_session_factory() as session:
        child = await session.get(Execution, UUID(result["execution_id"]))
    assert child is not None
    assert child.project_id == test_project_id
    assert child.status == ExecutionStatus.PENDING


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cross_project_rejected_before_child_creation(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """A child in a different project is rejected and no child Execution is persisted."""
    other_project = await _make_project(test_db_session)
    child_wf_id, _ = await _create_published_child(test_db_session, created_by=test_user.id, project_id=other_project)
    parent_exec = str(await seed_parent_execution(test_db_session, created_by=test_user.id, project_id=test_project_id))
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)

    with pytest.raises(ApplicationError) as exc:
        await setup.run(_params(child_wf_id), parent_exec, _NODE_ID, str(test_user.id), 0)

    assert exc.value.type == _SCOPE_ERROR
    assert exc.value.non_retryable is True
    async with test_db_session_factory() as session:
        assert await session.get(Execution, _child_id(parent_exec)) is None  # verify DB: no child row


@pytest.mark.integration
@pytest.mark.asyncio
async def test_missing_parent_execution_rejected(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """A parent execution that does not exist is rejected, not bypassed."""
    child_wf_id, _ = await _create_published_child(test_db_session, created_by=test_user.id, project_id=test_project_id)
    parent_exec = str(uuid4())  # no parent Execution row seeded
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)

    with pytest.raises(ApplicationError) as exc:
        await setup.run(_params(child_wf_id), parent_exec, _NODE_ID, str(test_user.id), 0)

    assert exc.value.type == _SCOPE_ERROR
    assert exc.value.non_retryable is True
    async with test_db_session_factory() as session:
        assert await session.get(Execution, _child_id(parent_exec)) is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resume_path_cannot_bypass_project_validation(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """An already-created cross-project child is still rejected on the resume path."""
    other_project = await _make_project(test_db_session)
    child_wf_id, child_version_id = await _create_published_child(
        test_db_session, created_by=test_user.id, project_id=other_project
    )
    parent_exec = str(await seed_parent_execution(test_db_session, created_by=test_user.id, project_id=test_project_id))

    # Simulate a pre-existing child (e.g. created before the gate existed) in the other
    # project, under the deterministic child id the activity will derive -> forces the
    # idempotent resume path on the next run.
    existing_child_id = _child_id(parent_exec)
    test_db_session.add(
        Execution(
            id=existing_child_id,
            workflow_id=child_wf_id,
            workflow_version_id=child_version_id,
            project_id=other_project,
            temporal_workflow_id=f"preexisting-{existing_child_id.hex[:8]}",
            status=ExecutionStatus.PENDING,
            created_by=test_user.id,
            updated_by=test_user.id,
        )
    )
    await test_db_session.commit()
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)

    with pytest.raises(ApplicationError) as exc:
        await setup.run(_params(child_wf_id), parent_exec, _NODE_ID, str(test_user.id), 0)

    assert exc.value.type == _SCOPE_ERROR
    assert exc.value.non_retryable is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nested_uses_immediate_parent_project(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """A grandchild is validated against the immediate parent execution's project."""
    # Root parent + child both in test_project_id: run #1 creates a child execution in it.
    child_wf_id, _ = await _create_published_child(test_db_session, created_by=test_user.id, project_id=test_project_id)
    root_parent = str(await seed_parent_execution(test_db_session, created_by=test_user.id, project_id=test_project_id))
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)

    child = await setup.run(_params(child_wf_id), root_parent, _NODE_ID, str(test_user.id), 0)
    child_exec_id = child["execution_id"]  # this child execution is in test_project_id

    # A grandchild workflow in a DIFFERENT project, invoked from the child execution as
    # the immediate parent, must be rejected against the immediate parent's project.
    other_project = await _make_project(test_db_session)
    grandchild_wf_id, _ = await _create_published_child(
        test_db_session, created_by=test_user.id, project_id=other_project
    )

    with pytest.raises(ApplicationError) as exc:
        await setup.run(_params(grandchild_wf_id), child_exec_id, _NODE_ID, str(test_user.id), 1)

    assert exc.value.type == _SCOPE_ERROR
    assert exc.value.non_retryable is True
    async with test_db_session_factory() as session:
        assert await session.get(Execution, _child_id(child_exec_id)) is None
