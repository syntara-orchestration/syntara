"""Integration tests for ``ExecutionService.list_child_executions``.

The Sub-workflow setup activity records ``parent_execution_id`` and
``parent_node_id`` on each child execution's ``execution_metadata``. This
read-only lookup reuses that already-persisted relationship to list the child
(sub-workflow) executions of a parent — scoped to a single node when asked, and
covering ``for_each`` (one child per iteration) and nesting. It does not depend
on the child's terminal state, so children are returned while running and after
failure/cancellation. The parent execution must exist: an unknown parent is a
404 (``ExecutionNotFoundError``), mirroring ``list_execution_activities``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from syntara.authz.engine import AllowedProjectsResult
from syntara.workflows.exceptions import ExecutionNotFoundError
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.services.execution_service import ExecutionService

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User

_EMPTY_DEF = {"schema_version": "2.0.0", "triggers": [], "nodes": [], "edges": []}


async def _create_workflow_version(
    session: AsyncSession, *, created_by: UUID, project_id: UUID, name: str
) -> tuple[UUID, UUID]:
    """Persist a Workflow + WorkflowVersion; return (workflow_id, version_id)."""
    wf_id = uuid4()
    session.add(Workflow(id=wf_id, name=name, created_by=created_by, project_id=project_id))
    await session.flush()
    ver_id = uuid4()
    session.add(
        WorkflowVersion(
            id=ver_id,
            workflow_id=wf_id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=_EMPTY_DEF,
            created_by=created_by,
        )
    )
    await session.flush()
    return wf_id, ver_id


async def _create_execution(
    session: AsyncSession,
    *,
    created_by: UUID,
    project_id: UUID,
    wf_id: UUID,
    ver_id: UUID,
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
    parent_execution_id: str | None = None,
    parent_node_id: str | None = None,
) -> UUID:
    """Persist an Execution, optionally carrying parent linkage in execution_metadata.

    Called with no ``parent_execution_id`` it persists a plain (root) execution,
    which is what the parent-existence lookup in ``list_child_executions`` requires.
    """
    exec_id = uuid4()
    metadata: dict[str, object] | None = None
    if parent_execution_id is not None:
        metadata = {
            "trigger_type": "subworkflow_trigger",
            "parent_execution_id": parent_execution_id,
            "parent_node_id": parent_node_id,
        }
    session.add(
        Execution(
            id=exec_id,
            workflow_id=wf_id,
            workflow_version_id=ver_id,
            project_id=project_id,
            temporal_workflow_id=f"tmp-{exec_id.hex[:8]}",
            status=status,
            created_by=created_by,
            updated_by=created_by,
            execution_metadata=metadata,
        )
    )
    await session.commit()
    return exec_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_returns_child_with_metadata(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """A parent's single child is returned with its workflow metadata."""
    wf_id, ver_id = await _create_workflow_version(
        test_db_session, created_by=test_user.id, project_id=test_project_id, name="child-wf"
    )
    parent_id = await _create_execution(
        test_db_session, created_by=test_user.id, project_id=test_project_id, wf_id=wf_id, ver_id=ver_id
    )
    child_id = await _create_execution(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        wf_id=wf_id,
        ver_id=ver_id,
        parent_execution_id=str(parent_id),
        parent_node_id="sub_wf_node",
    )

    service = ExecutionService(test_db_session, test_user)
    result = await service.list_child_executions(parent_id, node_id="sub_wf_node")

    assert [e.id for e in result.resources] == [child_id]
    assert result.resources[0].workflow_name == "child-wf"
    assert result.resources[0].workflow_version == 1
    assert len(result.resources) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_node_id_filter_scopes_to_one_node(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """With two sub-workflow nodes under one parent, node_id returns only its child."""
    wf_id, ver_id = await _create_workflow_version(
        test_db_session, created_by=test_user.id, project_id=test_project_id, name="child-wf"
    )
    parent_id = await _create_execution(
        test_db_session, created_by=test_user.id, project_id=test_project_id, wf_id=wf_id, ver_id=ver_id
    )
    child_a = await _create_execution(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        wf_id=wf_id,
        ver_id=ver_id,
        parent_execution_id=str(parent_id),
        parent_node_id="node_a",
    )
    await _create_execution(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        wf_id=wf_id,
        ver_id=ver_id,
        parent_execution_id=str(parent_id),
        parent_node_id="node_b",
    )

    service = ExecutionService(test_db_session, test_user)
    scoped = await service.list_child_executions(parent_id, node_id="node_a")
    assert [e.id for e in scoped.resources] == [child_a]

    all_children = await service.list_child_executions(parent_id)
    assert len(all_children.resources) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_for_each_returns_all_children(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """A for_each sub-workflow node's multiple children are all returned, not collapsed."""
    wf_id, ver_id = await _create_workflow_version(
        test_db_session, created_by=test_user.id, project_id=test_project_id, name="child-wf"
    )
    parent_id = await _create_execution(
        test_db_session, created_by=test_user.id, project_id=test_project_id, wf_id=wf_id, ver_id=ver_id
    )
    child_ids = [
        await _create_execution(
            test_db_session,
            created_by=test_user.id,
            project_id=test_project_id,
            wf_id=wf_id,
            ver_id=ver_id,
            parent_execution_id=str(parent_id),
            parent_node_id="loop_sub_wf",
        )
        for _ in range(3)
    ]

    service = ExecutionService(test_db_session, test_user)
    result = await service.list_child_executions(parent_id, node_id="loop_sub_wf")

    assert len(result.resources) == 3
    assert {e.id for e in result.resources} == set(child_ids)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_children_returned_regardless_of_status(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """Running/failed/cancelled children are all returned (linkage persists before terminal state)."""
    wf_id, ver_id = await _create_workflow_version(
        test_db_session, created_by=test_user.id, project_id=test_project_id, name="child-wf"
    )
    parent_id = await _create_execution(
        test_db_session, created_by=test_user.id, project_id=test_project_id, wf_id=wf_id, ver_id=ver_id
    )
    for status in (ExecutionStatus.RUNNING, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED):
        await _create_execution(
            test_db_session,
            created_by=test_user.id,
            project_id=test_project_id,
            wf_id=wf_id,
            ver_id=ver_id,
            status=status,
            parent_execution_id=str(parent_id),
            parent_node_id="sub_wf_node",
        )

    service = ExecutionService(test_db_session, test_user)
    result = await service.list_child_executions(parent_id, node_id="sub_wf_node")

    assert {e.status for e in result.resources} == {
        ExecutionStatus.RUNNING,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_children_returns_empty(test_db_session: AsyncSession, test_user: User, test_project_id: UUID) -> None:
    """An existing parent with no sub-workflow children yields an empty list, not an error."""
    wf_id, ver_id = await _create_workflow_version(
        test_db_session, created_by=test_user.id, project_id=test_project_id, name="child-wf"
    )
    parent_id = await _create_execution(
        test_db_session, created_by=test_user.id, project_id=test_project_id, wf_id=wf_id, ver_id=ver_id
    )

    service = ExecutionService(test_db_session, test_user)
    result = await service.list_child_executions(parent_id)
    assert result.resources == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nonexistent_parent_raises(test_db_session: AsyncSession, test_user: User, test_project_id: UUID) -> None:
    """An unknown parent execution id raises ExecutionNotFoundError (surfaces as a 404)."""
    service = ExecutionService(test_db_session, test_user)
    with pytest.raises(ExecutionNotFoundError):
        await service.list_child_executions(uuid4())


@pytest.mark.integration
@pytest.mark.asyncio
async def test_for_each_ordering_is_deterministic(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """for_each children come back in a stable order across repeated calls (id tiebreaker)."""
    wf_id, ver_id = await _create_workflow_version(
        test_db_session, created_by=test_user.id, project_id=test_project_id, name="child-wf"
    )
    parent_id = await _create_execution(
        test_db_session, created_by=test_user.id, project_id=test_project_id, wf_id=wf_id, ver_id=ver_id
    )
    for _ in range(5):
        await _create_execution(
            test_db_session,
            created_by=test_user.id,
            project_id=test_project_id,
            wf_id=wf_id,
            ver_id=ver_id,
            parent_execution_id=str(parent_id),
            parent_node_id="loop_sub_wf",
        )

    service = ExecutionService(test_db_session, test_user)
    first = await service.list_child_executions(parent_id, node_id="loop_sub_wf", include_total=True)
    second = await service.list_child_executions(parent_id, node_id="loop_sub_wf")

    assert [e.id for e in first.resources] == [e.id for e in second.resources]
    assert first.total == 5


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nested_children(test_db_session: AsyncSession, test_user: User, test_project_id: UUID) -> None:
    """Listing a mid-level child's children returns the grandchild (nesting)."""
    wf_id, ver_id = await _create_workflow_version(
        test_db_session, created_by=test_user.id, project_id=test_project_id, name="child-wf"
    )
    root_id = await _create_execution(
        test_db_session, created_by=test_user.id, project_id=test_project_id, wf_id=wf_id, ver_id=ver_id
    )
    mid_id = await _create_execution(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        wf_id=wf_id,
        ver_id=ver_id,
        parent_execution_id=str(root_id),
        parent_node_id="mid_node",
    )
    leaf_id = await _create_execution(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        wf_id=wf_id,
        ver_id=ver_id,
        parent_execution_id=str(mid_id),
        parent_node_id="leaf_node",
    )

    service = ExecutionService(test_db_session, test_user)
    root_children = await service.list_child_executions(root_id)
    assert [e.id for e in root_children.resources] == [mid_id]

    mid_children = await service.list_child_executions(mid_id)
    assert [e.id for e in mid_children.resources] == [leaf_id]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_visibility_excludes_other_project(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """A child outside the allowed projects is filtered out."""
    wf_id, ver_id = await _create_workflow_version(
        test_db_session, created_by=test_user.id, project_id=test_project_id, name="child-wf"
    )
    parent_id = await _create_execution(
        test_db_session, created_by=test_user.id, project_id=test_project_id, wf_id=wf_id, ver_id=ver_id
    )
    await _create_execution(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        wf_id=wf_id,
        ver_id=ver_id,
        parent_execution_id=str(parent_id),
        parent_node_id="sub_wf_node",
    )

    service = ExecutionService(test_db_session, test_user)
    other_project = AllowedProjectsResult(all_projects=False, project_ids=[uuid4()])
    scoped = await service.list_child_executions(parent_id, allowed_projects=other_project)
    assert scoped.resources == []

    in_scope = AllowedProjectsResult(all_projects=False, project_ids=[test_project_id])
    allowed = await service.list_child_executions(parent_id, allowed_projects=in_scope)
    assert len(allowed.resources) == 1
