"""Integration tests for workflow hard delete implementation.

Verifies hard delete behavior: DELETE /workflows/{id} removes the row from
the database entirely (not soft-deleted). Executions are disassociated
(workflow_id set to NULL) rather than cascade-deleted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlmodel import select

from syntara.workflows.models import Workflow
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow_version import WorkflowVersion
from tests.helpers.workflow import create_minimal_workflow_definition

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.mark.asyncio
async def test_delete_workflow_removes_row(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id,
    test_user,
) -> None:
    """Verify DELETE /workflows/{id} hard-deletes the workflow row."""
    workflow_id = uuid4()
    workflow = Workflow(
        id=workflow_id,
        name=f"delete-test-{uuid4().hex[:8]}",
        project_id=test_project_id,
        created_by=test_user.id,
        current_version=1,
        is_enabled=False,
        workflow_definition=create_minimal_workflow_definition(name="delete-test"),
    )
    test_db_session.add(workflow)
    await test_db_session.commit()

    response = await auth_client.delete(f"/api/v1/workflows/{workflow_id}")
    assert response.status_code == 204

    result = await test_db_session.exec(select(Workflow).where(Workflow.id == workflow_id))
    db_workflow = result.one_or_none()

    assert db_workflow is None, "Workflow still exists — expected hard delete"


@pytest.mark.asyncio
async def test_delete_workflow_disassociates_executions(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id,
    test_user,
) -> None:
    """Verify executions survive workflow deletion with FKs set to NULL."""
    workflow_id = uuid4()
    version_id = uuid4()
    execution_id = uuid4()

    workflow = Workflow(
        id=workflow_id,
        name=f"disassoc-test-{uuid4().hex[:8]}",
        project_id=test_project_id,
        created_by=test_user.id,
        current_version=1,
        is_enabled=False,
        workflow_definition=create_minimal_workflow_definition(name="disassoc-test"),
    )
    test_db_session.add(workflow)
    await test_db_session.flush()

    version = WorkflowVersion(
        id=version_id,
        workflow_id=workflow_id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=create_minimal_workflow_definition(name="disassoc-test"),
        created_by=test_user.id,
    )
    test_db_session.add(version)
    await test_db_session.flush()

    execution = Execution(
        id=execution_id,
        workflow_id=workflow_id,
        workflow_version_id=version_id,
        project_id=test_project_id,
        created_by=test_user.id,
        status="completed",
        temporal_workflow_id=f"test-temporal-{uuid4().hex[:8]}",
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    response = await auth_client.delete(f"/api/v1/workflows/{workflow_id}")
    assert response.status_code == 204

    test_db_session.expire_all()
    result = await test_db_session.exec(select(Execution).where(Execution.id == execution_id))
    db_execution = result.one_or_none()

    assert db_execution is not None, "Execution was cascade-deleted — expected disassociation"
    assert db_execution.workflow_id is None, "workflow_id should be NULL after disassociation"
    assert db_execution.workflow_version_id is None, "workflow_version_id should be NULL after disassociation"

    version_result = await test_db_session.exec(select(WorkflowVersion).where(WorkflowVersion.id == version_id))
    assert version_result.one_or_none() is None, "Version should cascade-delete with workflow"
