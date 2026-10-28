"""Always-latest published-version resolution for sub-workflows.

The Sub-workflow setup activity resolves the target workflow's currently
published version at invocation time (not at save time). These tests exercise
that resolution against the real, alembic-built PostgreSQL schema by calling
``SubWorkflowSetupActivity.run`` directly (it uses no Temporal activity context),
covering:

* a published v1 is resolved and used,
* republishing v2 makes the next run resolve v2 without changing the caller,
* an unpublished target raises a non-retryable error naming the target,
* the resolved version is pinned on the persisted child execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.activities.sub_workflow_setup_activity import (
    SubWorkflowSetupActivity,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User

_TASK_QUEUE = "sub-wf-version-resolution"


def _child_def(code: str) -> dict[str, Any]:
    """A minimal published-child definition whose script code identifies the version."""
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": "child_trigger", "type": "subworkflow_trigger", "parameters": {}}],
        "nodes": [{"id": "child_script", "type": "script", "parameters": {"language": "bash", "code": code}}],
        "edges": [{"from": "child_trigger", "to": "child_script"}],
    }


def _params(workflow_id: UUID) -> dict[str, Any]:
    """Resolved sub_workflow node parameters pointing at the child workflow."""
    return {"workflow_id": str(workflow_id), "trigger_node_id": "child_trigger", "input_mapping": {}}


async def _create_child_workflow(
    session: AsyncSession,
    *,
    created_by: UUID,
    project_id: UUID,
    versions: list[tuple[int, str]],
    publish: int | None,
) -> tuple[UUID, dict[int, UUID]]:
    """Create a child Workflow with the given (version_number, code) versions.

    Publishes ``publish`` (a version number) by setting ``published_version_id`` and
    ``is_enabled``; pass ``None`` to leave the workflow unpublished. Returns the
    workflow id and a map of version number -> version id.
    """
    workflow_id = uuid4()
    workflow = Workflow(
        id=workflow_id,
        name=f"child-{workflow_id.hex[:8]}",
        created_by=created_by,
        project_id=project_id,
    )
    session.add(workflow)
    await session.flush()

    version_ids: dict[int, UUID] = {}
    for num, code in versions:
        version = WorkflowVersion(
            id=uuid4(),
            workflow_id=workflow_id,
            version=num,
            schema_version="2.0.0",
            workflow_definition=_child_def(code),
            created_by=created_by,
        )
        session.add(version)
        version_ids[num] = version.id
    # Flush so the versions exist before the workflow FK points at one
    # (published_version_id is a plain FK column, not an ORM relationship, so the
    # unit-of-work cannot order the version INSERTs before the workflow UPDATE).
    await session.flush()

    if publish is not None:
        workflow.is_enabled = True
        workflow.published_version_id = version_ids[publish]
    await session.commit()
    return workflow_id, version_ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resolves_published_version_at_invocation(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """A published v1 is resolved and its definition returned."""
    wf_id, _ = await _create_child_workflow(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        versions=[(1, "echo v1")],
        publish=1,
    )
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)

    result = await setup.run(_params(wf_id), str(uuid4()), "sub_wf_node", str(test_user.id), 0)

    assert result["child_workflow_version"] == 1
    assert result["workflow_definition"]["nodes"][0]["parameters"]["code"] == "echo v1"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_republished_version_used_on_next_run_without_caller_change(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """Republishing v2 makes the next run resolve v2 — the caller params are unchanged."""
    wf_id, version_ids = await _create_child_workflow(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        versions=[(1, "echo v1"), (2, "echo v2")],
        publish=1,
    )
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)
    params = _params(wf_id)  # identical caller params for both runs

    first = await setup.run(params, str(uuid4()), "sub_wf_node", str(test_user.id), 0)
    assert first["child_workflow_version"] == 1
    assert first["workflow_definition"]["nodes"][0]["parameters"]["code"] == "echo v1"

    # Republish v2 — no change to the caller's workflow definition / params.
    workflow = await test_db_session.get(Workflow, wf_id)
    assert workflow is not None
    workflow.published_version_id = version_ids[2]
    await test_db_session.commit()

    second = await setup.run(params, str(uuid4()), "sub_wf_node", str(test_user.id), 0)
    assert second["child_workflow_version"] == 2
    assert second["workflow_definition"]["nodes"][0]["parameters"]["code"] == "echo v2"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unpublished_target_raises_non_retryable_naming_target(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """An unpublished target raises a non-retryable error that names the target."""
    wf_id, _ = await _create_child_workflow(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        versions=[(1, "echo v1")],
        publish=None,
    )
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)

    with pytest.raises(ApplicationError) as exc_info:
        await setup.run(_params(wf_id), str(uuid4()), "sub_wf_node", str(test_user.id), 0)

    assert exc_info.value.type == "WorkflowNotPublishedError"
    assert exc_info.value.non_retryable is True
    assert str(wf_id) in str(exc_info.value)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resolved_version_pinned_on_child_execution(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """The child execution is pinned to the version resolved at invocation.

    Republishing a newer version afterwards does not repoint the already-created
    child execution's workflow_version_id.
    """
    wf_id, version_ids = await _create_child_workflow(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        versions=[(1, "echo v1"), (2, "echo v2")],
        publish=1,
    )
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)

    result = await setup.run(_params(wf_id), str(uuid4()), "sub_wf_node", str(test_user.id), 0)
    child_execution_id = UUID(result["execution_id"])

    # Republish v2 after the child execution was created.
    workflow = await test_db_session.get(Workflow, wf_id)
    assert workflow is not None
    workflow.published_version_id = version_ids[2]
    await test_db_session.commit()

    async with test_db_session_factory() as session:
        child_execution = await session.get(Execution, child_execution_id)
    assert child_execution is not None
    assert child_execution.workflow_version_id == version_ids[1]
