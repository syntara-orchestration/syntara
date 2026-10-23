"""Contract tests for opt-in workflow invocation schema discovery."""

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import Project
from syntara.core.models import User
from syntara.workflows.models import Workflow, WorkflowVersion
from syntara.workflows.models.workflow_publish_event import PublishAction, WorkflowPublishEvent


def _version_definition(*, draft_only_trigger: bool = False, eligible: bool = True) -> dict[str, Any]:
    triggers: list[dict[str, Any]] = [
        {"id": "manual_entry", "name": "Manual", "type": "manual_trigger", "parameters": {}},
    ]
    if eligible:
        triggers.extend(
            [
                {
                    "id": "child_entry",
                    "name": "Child Entry",
                    "type": "subworkflow_trigger",
                    "parameters": {
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "username": {"type": "string"},
                                "retry_count": {"type": "integer", "default": 2},
                            },
                            "required": ["username"],
                        }
                    },
                },
                {
                    "id": "child_entry_secondary",
                    "name": "Secondary Entry",
                    "type": "subworkflow_trigger",
                    "parameters": {},
                },
            ]
        )
    if draft_only_trigger:
        triggers.append(
            {
                "id": "draft_only_entry",
                "name": "Draft Only",
                "type": "subworkflow_trigger",
                "parameters": {"input_schema": {"type": "object", "properties": {"draft": {"type": "boolean"}}}},
            }
        )
    return {
        "schema_version": "2.0.0",
        "name": "invocation-schema-workflow",
        "triggers": triggers,
        "nodes": [],
        "edges": [],
    }


async def _create_workflow(
    session: AsyncSession,
    user: User,
    project_id: UUID,
    *,
    published: bool,
    eligible: bool = True,
) -> Workflow:
    workflow = Workflow(
        name=f"invocation-schema-{uuid4().hex[:8]}",
        created_by=user.id,
        project_id=project_id,
        current_version=2 if published else 1,
        is_enabled=False,
    )
    session.add(workflow)
    await session.flush()

    published_version = WorkflowVersion(
        workflow_id=workflow.id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=_version_definition(eligible=eligible),
        created_by=user.id,
    )
    session.add(published_version)

    if published:
        session.add(
            WorkflowVersion(
                workflow_id=workflow.id,
                version=2,
                schema_version="2.0.0",
                workflow_definition=_version_definition(draft_only_trigger=True),
                created_by=user.id,
            )
        )

    await session.flush()
    if published:
        workflow.published_version_id = published_version.id
        workflow.is_enabled = True
        session.add(
            WorkflowPublishEvent(
                workflow_id=workflow.id,
                version_id=published_version.id,
                action=PublishAction.PUBLISHED,
                actor_id=user.id,
            )
        )
        await session.flush()
    return workflow


@pytest.mark.asyncio
async def test_get_workflow_includes_only_published_subworkflow_trigger_schemas(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: str,
) -> None:
    workflow = await _create_workflow(test_db_session, test_user, UUID(test_project_id), published=True)
    path = f"/api/v1/workflows/{workflow.id}"

    ordinary_response = await auth_client.get(path)
    assert ordinary_response.status_code == 200
    assert "invocation_schema" not in ordinary_response.json()
    assert ordinary_response.json()["version"]["version"] == 2

    response = await auth_client.get(f"{path}/invocation_schema")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "workflow_id": str(workflow.id),
        "published_version_id": str(workflow.published_version_id),
        "published_version": 1,
        "is_eligible": True,
        "triggers": [
            {
                "trigger_node_id": "child_entry",
                "name": "Child Entry",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "username": {"type": "string"},
                        "retry_count": {"type": "integer", "default": 2},
                    },
                    "required": ["username"],
                },
            },
            {"trigger_node_id": "child_entry_secondary", "name": "Secondary Entry", "input_schema": {}},
        ],
    }


@pytest.mark.asyncio
async def test_invocation_schema_requires_a_published_version_but_plain_get_does_not(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: str,
) -> None:
    workflow = await _create_workflow(test_db_session, test_user, UUID(test_project_id), published=False)
    path = f"/api/v1/workflows/{workflow.id}"

    ordinary_response = await auth_client.get(path)
    assert ordinary_response.status_code == 200
    assert "invocation_schema" not in ordinary_response.json()

    schema_response = await auth_client.get(f"{path}/invocation_schema")
    assert schema_response.status_code == 404


@pytest.mark.asyncio
async def test_invocation_schema_request_for_unknown_workflow_returns_404(auth_client: AsyncClient) -> None:
    response = await auth_client.get(
        f"/api/v1/workflows/{uuid4()}/invocation_schema",
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_invocation_schema_requires_workflow_read_permission(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: str,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    workflow = await _create_workflow(test_db_session, test_user, UUID(test_project_id), published=True)
    reader_without_permission = await user_factory(
        username=f"no-workflow-read-{uuid4().hex[:8]}",
        email=f"no-workflow-read-{uuid4().hex[:8]}@example.com",
    )
    auth_as(reader_without_permission)

    response = await auth_client.get(
        f"/api/v1/workflows/{workflow.id}/invocation_schema",
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_published_workflow_without_subworkflow_trigger_returns_empty_schema(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: str,
) -> None:
    workflow = await _create_workflow(
        test_db_session,
        test_user,
        UUID(test_project_id),
        published=True,
        eligible=False,
    )

    response = await auth_client.get(
        f"/api/v1/workflows/{workflow.id}/invocation_schema",
    )

    assert response.status_code == 200
    assert response.json() == {
        "workflow_id": str(workflow.id),
        "published_version_id": str(workflow.published_version_id),
        "published_version": 1,
        "is_eligible": False,
        "triggers": [],
    }


@pytest.mark.asyncio
async def test_stateless_validate_does_not_apply_project_scope_check(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    other_project = Project(name=f"other-project-{uuid4().hex[:8]}")
    test_db_session.add(other_project)
    await test_db_session.flush()
    child = Workflow(
        name=f"cross-project-child-{uuid4().hex[:8]}",
        created_by=test_user.id,
        project_id=other_project.id,
        current_version=1,
        is_enabled=False,
    )
    test_db_session.add(child)
    await test_db_session.flush()

    response = await auth_client.post(
        "/api/v1/workflows/validate",
        json={
            "workflow_definition": {
                "schema_version": "2.0.0",
                "name": "stateless-parent",
                "triggers": [{"id": "manual", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "call_child",
                        "name": "Call child",
                        "type": "sub_workflow",
                        "parameters": {"workflow_id": str(child.id), "trigger_node_id": "child_entry"},
                    }
                ],
                "edges": [{"from": "manual", "to": "call_child"}],
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["is_valid"] is True
    assert response.json()["findings"] == []
