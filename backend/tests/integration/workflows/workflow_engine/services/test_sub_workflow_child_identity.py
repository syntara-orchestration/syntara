"""Replay-safe child-execution identity for sub-workflows (AAP-91263 / OQ-A11).

The child execution id is derived from the iteration-aware invocation identity
(canvas node id plus an ``_iter_{n}`` suffix per enclosing loop), so a
``sub_workflow`` node inside a ``for_each`` produces a distinct child per
iteration, while the persisted lineage metadata keeps the canvas node id.
These tests exercise ``SubWorkflowSetupActivity.run`` against the real,
alembic-built PostgreSQL schema.

Story: AAP-91263 (OQ-A11 identity correctness).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4, uuid5

import pytest

from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.activities.sub_workflow_setup_activity import (
    _SUB_WORKFLOW_NAMESPACE,
    SubWorkflowSetupActivity,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User

_TASK_QUEUE = "sub-wf-child-identity"


def _child_def() -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": "child_trigger", "type": "subworkflow_trigger", "parameters": {}}],
        "nodes": [{"id": "child_script", "type": "script", "parameters": {"language": "bash", "code": "echo ok"}}],
        "edges": [{"from": "child_trigger", "to": "child_script"}],
    }


async def _create_published_child(session: AsyncSession, *, created_by: UUID, project_id: UUID) -> UUID:
    workflow_id = uuid4()
    workflow = Workflow(
        id=workflow_id, name=f"child-{workflow_id.hex[:8]}", created_by=created_by, project_id=project_id
    )
    session.add(workflow)
    await session.flush()
    version = WorkflowVersion(
        id=uuid4(),
        workflow_id=workflow_id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=_child_def(),
        created_by=created_by,
    )
    session.add(version)
    await session.flush()
    workflow.is_enabled = True
    workflow.published_version_id = version.id
    await session.commit()
    return workflow_id


def _params(workflow_id: UUID) -> dict[str, Any]:
    return {"workflow_id": str(workflow_id), "trigger_node_id": "child_trigger", "input_mapping": {}}


def _expected_child_id(parent_execution_id: str, invocation_id: str) -> str:
    return str(uuid5(_SUB_WORKFLOW_NAMESPACE, f"{parent_execution_id}:{invocation_id}"))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_non_loop_identity_unchanged(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """Outside any loop (no invocation_node_id) the child id is the canvas-node derivation."""
    wf_id = await _create_published_child(test_db_session, created_by=test_user.id, project_id=test_project_id)
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)
    parent_exec = str(uuid4())

    result = await setup.run(_params(wf_id), parent_exec, "sub_wf_node", str(test_user.id), 0)

    assert result["execution_id"] == _expected_child_id(parent_exec, "sub_wf_node")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_different_iterations_create_distinct_children(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """Two iterations of the same node (distinct invocation ids) create distinct children."""
    wf_id = await _create_published_child(test_db_session, created_by=test_user.id, project_id=test_project_id)
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)
    parent_exec = str(uuid4())

    r0 = await setup.run(_params(wf_id), parent_exec, "sub_wf_node", str(test_user.id), 0, "sub_wf_node_iter_0")
    r1 = await setup.run(_params(wf_id), parent_exec, "sub_wf_node", str(test_user.id), 0, "sub_wf_node_iter_1")

    assert r0["execution_id"] != r1["execution_id"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_same_invocation_reuses_child(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """Repeating the same logical invocation (same invocation id) reuses the child (idempotent)."""
    wf_id = await _create_published_child(test_db_session, created_by=test_user.id, project_id=test_project_id)
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)
    parent_exec = str(uuid4())

    first = await setup.run(_params(wf_id), parent_exec, "sub_wf_node", str(test_user.id), 0, "sub_wf_node_iter_2")
    second = await setup.run(_params(wf_id), parent_exec, "sub_wf_node", str(test_user.id), 0, "sub_wf_node_iter_2")

    assert first["execution_id"] == second["execution_id"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nested_loops_produce_unique_identities(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """Different inner iterations under the same outer iteration create distinct children."""
    wf_id = await _create_published_child(test_db_session, created_by=test_user.id, project_id=test_project_id)
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)
    parent_exec = str(uuid4())

    a = await setup.run(_params(wf_id), parent_exec, "sub_wf_node", str(test_user.id), 0, "sub_wf_node_iter_1_iter_0")
    b = await setup.run(_params(wf_id), parent_exec, "sub_wf_node", str(test_user.id), 0, "sub_wf_node_iter_1_iter_1")

    assert a["execution_id"] != b["execution_id"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_separate_parents_produce_distinct_children(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """The same invocation id under different parent executions yields distinct children."""
    wf_id = await _create_published_child(test_db_session, created_by=test_user.id, project_id=test_project_id)
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)

    a = await setup.run(_params(wf_id), str(uuid4()), "sub_wf_node", str(test_user.id), 0, "sub_wf_node_iter_0")
    b = await setup.run(_params(wf_id), str(uuid4()), "sub_wf_node", str(test_user.id), 0, "sub_wf_node_iter_0")

    assert a["execution_id"] != b["execution_id"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lineage_metadata_preserves_canvas_node_id(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """The child id is iteration-aware, but persisted lineage keeps the canvas node id."""
    wf_id = await _create_published_child(test_db_session, created_by=test_user.id, project_id=test_project_id)
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)
    parent_exec = str(uuid4())

    result = await setup.run(_params(wf_id), parent_exec, "sub_wf_node", str(test_user.id), 0, "sub_wf_node_iter_3")

    assert result["execution_id"] == _expected_child_id(parent_exec, "sub_wf_node_iter_3")
    async with test_db_session_factory() as session:
        child = await session.get(Execution, UUID(result["execution_id"]))
    assert child is not None
    assert child.execution_metadata["parent_node_id"] == "sub_wf_node"
