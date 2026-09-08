"""Integration tests for workflow hard delete implementation.

Verifies hard delete behavior: DELETE /workflows/{id} removes the workflow,
its versions, and its executions via CASCADE.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlmodel import select

from syntara.approvals.models.approval_request import ApprovalRequest
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

    get_response = await auth_client.get(f"/api/v1/workflows/{workflow_id}")
    assert get_response.status_code == 404

    result = await test_db_session.exec(select(Workflow).where(Workflow.id == workflow_id))
    db_workflow = result.one_or_none()

    assert db_workflow is None, "Workflow still exists — expected hard delete"


@pytest.mark.asyncio
async def test_delete_workflow_cascades_executions_and_versions(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id,
    test_user,
) -> None:
    """Verify executions and versions are cascade-deleted with the workflow."""
    workflow_id = uuid4()
    version_id = uuid4()
    execution_id = uuid4()

    workflow = Workflow(
        id=workflow_id,
        name=f"cascade-test-{uuid4().hex[:8]}",
        project_id=test_project_id,
        created_by=test_user.id,
        current_version=1,
        is_enabled=False,
        workflow_definition=create_minimal_workflow_definition(name="cascade-test"),
    )
    test_db_session.add(workflow)
    await test_db_session.flush()

    version = WorkflowVersion(
        id=version_id,
        workflow_id=workflow_id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=create_minimal_workflow_definition(name="cascade-test"),
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

    exec_result = await test_db_session.exec(select(Execution).where(Execution.id == execution_id))
    assert exec_result.one_or_none() is None, "Execution should cascade-delete with workflow"

    version_result = await test_db_session.exec(select(WorkflowVersion).where(WorkflowVersion.id == version_id))
    assert version_result.one_or_none() is None, "Version should cascade-delete with workflow"


@pytest.mark.asyncio
async def test_delete_workflow_blocked_by_active_execution(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id,
    test_user,
) -> None:
    """Verify DELETE /workflows/{id} returns 409 when non-terminal executions exist."""
    workflow_id = uuid4()
    version_id = uuid4()

    workflow = Workflow(
        id=workflow_id,
        name=f"active-exec-test-{uuid4().hex[:8]}",
        project_id=test_project_id,
        created_by=test_user.id,
        current_version=1,
        is_enabled=False,
        workflow_definition=create_minimal_workflow_definition(name="active-exec-test"),
    )
    test_db_session.add(workflow)
    await test_db_session.flush()

    version = WorkflowVersion(
        id=version_id,
        workflow_id=workflow_id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=create_minimal_workflow_definition(name="active-exec-test"),
        created_by=test_user.id,
    )
    test_db_session.add(version)
    await test_db_session.flush()

    execution = Execution(
        id=uuid4(),
        workflow_id=workflow_id,
        workflow_version_id=version_id,
        project_id=test_project_id,
        created_by=test_user.id,
        status="running",
        temporal_workflow_id=f"test-temporal-{uuid4().hex[:8]}",
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    response = await auth_client.delete(f"/api/v1/workflows/{workflow_id}")
    assert response.status_code == 409

    test_db_session.expire_all()
    result = await test_db_session.exec(select(Workflow).where(Workflow.id == workflow_id))
    assert result.one_or_none() is not None, "Workflow should still exist after blocked delete"


@pytest.mark.asyncio
async def test_delete_workflow_cleans_up_approval_requests(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id,
    test_user,
) -> None:
    """Verify DELETE /workflows/{id} removes orphaned ApprovalRequests."""
    workflow_id = uuid4()
    version_id = uuid4()
    execution_id = uuid4()
    approval_id = uuid4()

    workflow = Workflow(
        id=workflow_id,
        name=f"approval-cleanup-{uuid4().hex[:8]}",
        project_id=test_project_id,
        created_by=test_user.id,
        current_version=1,
        is_enabled=False,
        workflow_definition=create_minimal_workflow_definition(name="approval-cleanup"),
    )
    test_db_session.add(workflow)
    await test_db_session.flush()

    version = WorkflowVersion(
        id=version_id,
        workflow_id=workflow_id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=create_minimal_workflow_definition(name="approval-cleanup"),
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
    await test_db_session.flush()

    approval = ApprovalRequest(
        id=approval_id,
        execution_id=execution_id,
        project_id=test_project_id,
        status="pending",
        name="test-approval",
        approval_node_id="approval-node-1",
        prompt="Test approval",
        next_step_approved={"id": "next", "name": "Next Step", "type": "llm"},
    )
    test_db_session.add(approval)
    await test_db_session.commit()

    response = await auth_client.delete(f"/api/v1/workflows/{workflow_id}")
    assert response.status_code == 204

    test_db_session.expire_all()
    ar_result = await test_db_session.exec(select(ApprovalRequest).where(ApprovalRequest.id == approval_id))
    assert ar_result.one_or_none() is None, "ApprovalRequest should be cleaned up on workflow delete"
