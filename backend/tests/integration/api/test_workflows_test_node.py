"""Integration tests for POST /api/v1/workflows/{workflow_id}/test endpoint.

Uses auth_client + test_db_session pattern for:
- Testing invalid UUID format validation (syntara_api expects UUID type)
- Creating test data via DB fixtures for speed
- Direct DB state verification where needed
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_publish_event import PublishAction, WorkflowPublishEvent
from syntara.workflows.models.workflow_version import WorkflowVersion

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User


@pytest_asyncio.fixture
async def multi_node_workflow(test_db_session: AsyncSession, test_user: User) -> Workflow:
    """Create a workflow with two nodes for testing pre-resolved outputs."""
    workflow_def: dict[str, Any] = {
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger_manual", "type": "manual_trigger"}],
        "nodes": [
            {
                "id": "predecessor_node",
                "name": "predecessor_node",
                "type": "script",
                "parameters": {"language": "bash", "code": "echo predecessor"},
            },
            {
                "id": "test_activity",
                "name": "test_activity",
                "type": "script",
                "parameters": {"language": "bash", "code": "echo test"},
            },
        ],
        "edges": [
            {"from": "trigger_manual", "to": "predecessor_node"},
            {"from": "predecessor_node", "to": "test_activity"},
        ],
    }
    from syntara.authz.models.project import Project

    project = Project(name=f"test-node-project-{uuid.uuid4().hex[:8]}")
    test_db_session.add(project)
    await test_db_session.flush()

    workflow = Workflow(
        name=f"multi-node-test-{uuid.uuid4().hex[:8]}",
        is_enabled=False,
        created_by=test_user.id,
        updated_by=test_user.id,
        current_version=1,
        project_id=project.id,
    )
    test_db_session.add(workflow)

    version = WorkflowVersion(
        workflow_id=workflow.id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=workflow_def,
        created_by=test_user.id,
    )
    test_db_session.add(version)
    await test_db_session.flush()
    workflow.published_version_id = version.id
    workflow.is_enabled = True
    publish_event = WorkflowPublishEvent(
        workflow_id=workflow.id,
        version_id=version.id,
        action=PublishAction.PUBLISHED,
        actor_id=test_user.id,
    )
    test_db_session.add(publish_event)
    await test_db_session.commit()
    await test_db_session.refresh(workflow)
    return workflow


@pytest.mark.asyncio
async def test_test_workflow_node_success(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test successful single-node test execution creation."""
    response = await auth_client.post(
        f"/api/v1/workflows/{test_workflow.id}/test",
        json={
            "target_node_id": "test_activity",
            "pre_resolved_nodes": {},
            "trigger_inputs": {"key": "value"},
            "trigger_node_id": "trigger_manual",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["workflow_id"] == str(test_workflow.id)
    assert data["status"] == "pending"
    assert data["mode"] == "test"
    assert data["created_by"] == str(test_user.id)
    assert data["execution_metadata"] is not None
    assert data["execution_metadata"]["target_node_id"] == "test_activity"
    assert data["temporal_workflow_id"] is not None


@pytest.mark.asyncio
async def test_test_workflow_node_with_pre_resolved(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    multi_node_workflow: Workflow,
) -> None:
    """Test execution with pre-resolved node outputs."""
    response = await auth_client.post(
        f"/api/v1/workflows/{multi_node_workflow.id}/test",
        json={
            "target_node_id": "test_activity",
            "pre_resolved_nodes": {
                "predecessor_node": {
                    "output": {"status": "mocked", "value": 42},
                    "control": None,
                },
            },
            "trigger_inputs": {"key": "value"},
            "trigger_node_id": "trigger_manual",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["mode"] == "test"
    assert data["execution_metadata"] is not None
    pre_resolved = data["execution_metadata"]["pre_resolved_nodes"]
    assert "predecessor_node" in pre_resolved
    assert pre_resolved["predecessor_node"]["output"] == {"status": "mocked", "value": 42}


@pytest.mark.asyncio
async def test_test_workflow_node_workflow_not_found(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test execution with non-existent workflow returns 404."""
    non_existent_id = uuid.uuid4()
    response = await auth_client.post(
        f"/api/v1/workflows/{non_existent_id}/test",
        json={
            "target_node_id": "some_node",
            "pre_resolved_nodes": {},
            "trigger_inputs": {},
            "trigger_node_id": "trigger_manual",
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_test_workflow_node_invalid_target_node(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test execution with invalid target_node_id returns 422."""
    response = await auth_client.post(
        f"/api/v1/workflows/{test_workflow.id}/test",
        json={
            "target_node_id": "nonexistent_node",
            "pre_resolved_nodes": {},
            "trigger_inputs": {},
            "trigger_node_id": "trigger_manual",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_test_workflow_node_empty_target_node_id(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test execution with empty target_node_id returns 422."""
    response = await auth_client.post(
        f"/api/v1/workflows/{test_workflow.id}/test",
        json={
            "target_node_id": "",
            "pre_resolved_nodes": {},
            "trigger_inputs": {},
            "trigger_node_id": "trigger_manual",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_test_workflow_node_target_in_pre_resolved(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test execution with target_node_id in pre_resolved_nodes returns 422."""
    response = await auth_client.post(
        f"/api/v1/workflows/{test_workflow.id}/test",
        json={
            "target_node_id": "test_activity",
            "pre_resolved_nodes": {
                "test_activity": {"output": {"v": 1}},
            },
            "trigger_inputs": {},
            "trigger_node_id": "trigger_manual",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_test_workflow_node_invalid_workflow_id(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test execution with invalid UUID format returns 422.

    NOTE: This test requires auth_client (not syntara_api) because the generated
    client's test_node() method expects a UUID type parameter and cannot accept
    invalid string formats like "not-a-uuid" for validation testing.
    """
    response = await auth_client.post(
        "/api/v1/workflows/not-a-uuid/test",
        json={
            "target_node_id": "some_node",
            "pre_resolved_nodes": {},
            "trigger_inputs": {},
            "trigger_node_id": "trigger_manual",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_test_node_with_execute_target_false(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    multi_node_workflow: Workflow,
) -> None:
    """Test execution with execute_target=False creates test execution with correct metadata."""
    response = await auth_client.post(
        f"/api/v1/workflows/{multi_node_workflow.id}/test",
        json={
            "target_node_id": "test_activity",
            "pre_resolved_nodes": {
                "predecessor_node": {
                    "output": {"status": "mocked"},
                    "control": None,
                },
            },
            "trigger_inputs": {"key": "value"},
            "execute_target": False,
            "trigger_node_id": "trigger_manual",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["mode"] == "test"
    assert data["execution_metadata"]["execute_target"] is False
    assert data["execution_metadata"]["target_node_id"] == "test_activity"


@pytest.mark.asyncio
async def test_test_node_execute_target_false_allows_target_in_pre_resolved(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    multi_node_workflow: Workflow,
) -> None:
    """Test execution with execute_target=False allows target_node_id in pre_resolved_nodes."""
    response = await auth_client.post(
        f"/api/v1/workflows/{multi_node_workflow.id}/test",
        json={
            "target_node_id": "test_activity",
            "pre_resolved_nodes": {
                "test_activity": {
                    "output": {"custom": "value"},
                    "control": None,
                },
            },
            "trigger_inputs": {},
            "execute_target": False,
            "trigger_node_id": "trigger_manual",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["mode"] == "test"
    # Verify the target is in pre_resolved_nodes
    pre_resolved = data["execution_metadata"]["pre_resolved_nodes"]
    assert "test_activity" in pre_resolved
    assert pre_resolved["test_activity"]["output"] == {"custom": "value"}
