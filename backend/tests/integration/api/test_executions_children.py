"""Endpoint tests for GET /api/v1/executions/{id}/children.

Focus: authorization (read access to the *parent* execution via ``_exec_perm_read``)
and project visibility (children outside the caller's visible projects are not
exposed). Complements the service-level tests in
``tests/integration/workflows/test_list_child_executions.py``.

The default ``jwt_client`` authenticates as an admin (the api conftest puts
``test_user`` in an admin-roled group), so admin-bypass cannot exercise
project scoping. The denial / visibility tests therefore authenticate as a
purpose-built limited user via ``auth_client`` + ``auth_as`` — the pattern the
api conftest documents for authz-specific tests.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlmodel import select

from syntara.authz.models.project import Project
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow_version import WorkflowVersion
from tests.integration.api.conftest import make_project_user

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User
    from syntara.workflows.models.workflow import Workflow


async def _add_child(
    session: AsyncSession,
    *,
    parent: Execution,
    node_id: str,
    project_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Persist a child execution linked to ``parent`` via execution_metadata."""
    child_id = uuid.uuid4()
    session.add(
        Execution(
            id=child_id,
            workflow_id=parent.workflow_id,
            workflow_version_id=parent.workflow_version_id,
            temporal_workflow_id=f"child-{child_id.hex[:8]}",
            status=ExecutionStatus.COMPLETED,
            input_data={},
            created_by=parent.created_by,
            project_id=project_id or parent.project_id,
            execution_metadata={
                "trigger_type": "subworkflow_trigger",
                "parent_execution_id": str(parent.id),
                "parent_node_id": node_id,
            },
        )
    )
    await session.commit()
    return child_id


@pytest.mark.asyncio
async def test_children_returned_for_accessible_parent(
    jwt_client: AsyncClient, test_execution: Execution, test_db_session: AsyncSession
) -> None:
    """A caller with read access to the parent gets its child executions."""
    child_id = await _add_child(test_db_session, parent=test_execution, node_id="sub_wf_node")

    response = await jwt_client.get(f"/api/v1/executions/{test_execution.id}/children")

    assert response.status_code == 200
    ids = [r["id"] for r in response.json()["resources"]]
    assert str(child_id) in ids


@pytest.mark.asyncio
async def test_children_scoped_by_node_id(
    jwt_client: AsyncClient, test_execution: Execution, test_db_session: AsyncSession
) -> None:
    """node_id scopes results to a single parent Sub-workflow node."""
    node_a = await _add_child(test_db_session, parent=test_execution, node_id="node_a")
    await _add_child(test_db_session, parent=test_execution, node_id="node_b")

    response = await jwt_client.get(f"/api/v1/executions/{test_execution.id}/children?node_id=node_a")

    assert response.status_code == 200
    ids = [r["id"] for r in response.json()["resources"]]
    assert ids == [str(node_a)]


@pytest.mark.asyncio
async def test_children_nonexistent_parent_returns_404(jwt_client: AsyncClient) -> None:
    """An unknown parent execution yields a 404 (service parent-existence check)."""
    response = await jwt_client.get(f"/api/v1/executions/{uuid.uuid4()}/children")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_children_parent_in_another_project_denied(
    auth_client: AsyncClient,
    auth_as: Callable[[User], None],
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """A caller without read access to the parent's project is denied (403/404)."""
    other_project = Project(name=f"other-{uuid.uuid4().hex[:8]}", description="Other")
    test_db_session.add(other_project)
    await test_db_session.commit()
    await test_db_session.refresh(other_project)

    version_id = (
        await test_db_session.exec(select(WorkflowVersion.id).where(WorkflowVersion.workflow_id == test_workflow.id))
    ).first()
    foreign_parent = uuid.uuid4()
    test_db_session.add(
        Execution(
            id=foreign_parent,
            workflow_id=test_workflow.id,
            workflow_version_id=version_id,
            temporal_workflow_id=f"foreign-{foreign_parent.hex[:8]}",
            status=ExecutionStatus.PENDING,
            input_data={},
            created_by=test_user.id,
            project_id=other_project.id,
        )
    )
    await test_db_session.commit()

    # Authenticate as a user with no role on any project.
    outsider = await user_factory(
        username=f"outsider-{uuid.uuid4().hex[:8]}",
        email=f"outsider-{uuid.uuid4().hex[:8]}@example.com",
    )
    auth_as(outsider)

    response = await auth_client.get(f"/api/v1/executions/{foreign_parent}/children")
    assert response.status_code in (403, 404)


@pytest.mark.asyncio
async def test_children_excludes_child_outside_visible_projects(
    auth_client: AsyncClient,
    auth_as: Callable[[User], None],
    test_execution: Execution,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """Children in projects the caller can't see are filtered out, even for an accessible parent."""
    other_project = Project(name=f"other-{uuid.uuid4().hex[:8]}", description="Other")
    test_db_session.add(other_project)
    await test_db_session.commit()
    await test_db_session.refresh(other_project)

    visible = await _add_child(test_db_session, parent=test_execution, node_id="sub_wf_node")
    hidden = await _add_child(
        test_db_session, parent=test_execution, node_id="sub_wf_node", project_id=other_project.id
    )

    # Authenticate as a user scoped to the parent's project only (project-user
    # grants execution:read there, but not in other_project).
    parent_project = (
        await test_db_session.exec(select(Project).where(Project.id == test_execution.project_id))
    ).first()
    assert parent_project is not None
    scoped = await user_factory(
        username=f"scoped-{uuid.uuid4().hex[:8]}",
        email=f"scoped-{uuid.uuid4().hex[:8]}@example.com",
    )
    await make_project_user(test_db_session, scoped, parent_project)
    auth_as(scoped)

    response = await auth_client.get(f"/api/v1/executions/{test_execution.id}/children")

    assert response.status_code == 200
    ids = [r["id"] for r in response.json()["resources"]]
    assert str(visible) in ids
    assert str(hidden) not in ids
