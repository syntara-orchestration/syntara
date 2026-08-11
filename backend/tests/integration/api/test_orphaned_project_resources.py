"""Tests that creating resources against a soft-deleted project is rejected.

Validates the fix for AAP-74611 / AAP-74612: workflows, credentials, roles,
and policies must not be creatable against a project whose deleted_at is set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from syntara.credentials.models.credential_type import CredentialType
from tests.helpers.workflow import create_minimal_workflow_definition

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User


@pytest.fixture
async def bearer_type(test_db_session: AsyncSession) -> CredentialType:
    """Create a bearer token credential type for testing."""
    ct = CredentialType(
        name=f"Test Bearer {uuid4().hex[:8]}",
        description="Bearer token type",
        inputs={
            "fields": [{"id": "token", "label": "Token", "type": "string", "secret": True}],
            "required": ["token"],
        },
        injectors={"extra_vars": {"bearer_token": "{{token}}"}, "env": {}, "file": {}},
        managed=False,
    )
    test_db_session.add(ct)
    await test_db_session.commit()
    await test_db_session.refresh(ct)
    return ct


async def _create_and_delete_project(client: AsyncClient) -> str:
    """Create a project, delete it, and return its ID."""
    resp = await client.post(
        "/api/v1/projects",
        json={"name": f"doomed-{uuid4().hex[:8]}", "description": "will be deleted"},
    )
    assert resp.status_code == 201
    project_id: str = resp.json()["id"]

    resp = await client.delete(f"/api/v1/projects/{project_id}")
    assert resp.status_code == 204

    return project_id


@pytest.mark.asyncio
async def test_create_workflow_against_deleted_project_returns_404(jwt_client: AsyncClient) -> None:
    """POST /workflows with a soft-deleted project_id must return 404."""
    project_id = await _create_and_delete_project(jwt_client)

    resp = await jwt_client.post(
        "/api/v1/workflows",
        json={
            "name": f"orphan-wf-{uuid4().hex[:8]}",
            "project_id": project_id,
            "workflow_definition": create_minimal_workflow_definition(),
        },
    )

    assert resp.status_code == 404
    data = resp.json()
    assert data["code"] == "RESOURCE_NOT_FOUND"
    assert project_id in data["detail"]


@pytest.mark.asyncio
async def test_create_credential_against_deleted_project_returns_404(
    jwt_client: AsyncClient,
    bearer_type: CredentialType,
) -> None:
    """POST /credentials with a soft-deleted project_id must return 404."""
    project_id = await _create_and_delete_project(jwt_client)

    resp = await jwt_client.post(
        "/api/v1/credentials",
        json={
            "name": f"orphan-cred-{uuid4().hex[:8]}",
            "credential_type_id": str(bearer_type.id),
            "project_id": project_id,
            "inputs": {"token": "fake-token"},
        },
    )

    assert resp.status_code == 404
    data = resp.json()
    assert data["code"] == "RESOURCE_NOT_FOUND"
    assert project_id in data["detail"]


@pytest.mark.asyncio
async def test_create_role_against_deleted_project_is_rejected(admin_client: AsyncClient) -> None:
    """POST /projects/{id}/roles with a soft-deleted project must be rejected.

    Uses admin_client to bypass authz and test the service-layer check.
    """
    project_id = await _create_and_delete_project(admin_client)

    resp = await admin_client.post(
        f"/api/v1/projects/{project_id}/roles",
        json={
            "name": f"orphan-role-{uuid4().hex[:8]}",
            "policies": ["project-admin"],
        },
    )

    assert resp.status_code == 404
    data = resp.json()
    assert data["code"] == "RESOURCE_NOT_FOUND"
    assert project_id in data["detail"]


@pytest.mark.asyncio
async def test_create_policy_against_deleted_project_is_rejected(admin_client: AsyncClient) -> None:
    """POST /projects/{id}/policies with a soft-deleted project must be rejected.

    Uses admin_client to bypass authz and test the service-layer check.
    """
    project_id = await _create_and_delete_project(admin_client)

    resp = await admin_client.post(
        f"/api/v1/projects/{project_id}/policies",
        json={
            "name": f"orphan-policy-{uuid4().hex[:8]}",
            "statements": [{"effect": "allow", "actions": ["workflow:read"], "scope": "project"}],
        },
    )

    assert resp.status_code == 404
    data = resp.json()
    assert data["code"] == "RESOURCE_NOT_FOUND"
    assert project_id in data["detail"]


@pytest.mark.asyncio
async def test_create_role_toplevel_against_deleted_project_is_rejected(admin_client: AsyncClient) -> None:
    """POST /roles with a soft-deleted project_id in the body must return 404.

    Tests the top-level /roles endpoint (separate from /projects/{id}/roles).
    """
    project_id = await _create_and_delete_project(admin_client)

    resp = await admin_client.post(
        "/api/v1/roles",
        json={
            "name": f"orphan-role-tl-{uuid4().hex[:8]}",
            "policies": ["project-admin"],
            "project_id": project_id,
        },
    )

    assert resp.status_code == 404
    data = resp.json()
    assert data["code"] == "RESOURCE_NOT_FOUND"
    assert project_id in data["detail"]


@pytest.mark.asyncio
async def test_create_policy_toplevel_against_deleted_project_is_rejected(admin_client: AsyncClient) -> None:
    """POST /policies with a soft-deleted project_id in the body must return 404.

    Tests the top-level /policies endpoint (separate from /projects/{id}/policies).
    """
    project_id = await _create_and_delete_project(admin_client)

    resp = await admin_client.post(
        "/api/v1/policies",
        json={
            "name": f"orphan-policy-tl-{uuid4().hex[:8]}",
            "statements": [{"effect": "allow", "actions": ["workflow:read"], "scope": "project"}],
            "project_id": project_id,
        },
    )

    assert resp.status_code == 404
    data = resp.json()
    assert data["code"] == "RESOURCE_NOT_FOUND"
    assert project_id in data["detail"]


@pytest.mark.asyncio
async def test_create_role_assignment_toplevel_against_deleted_project_is_rejected(
    admin_client: AsyncClient,
    test_user: User,
) -> None:
    """POST /role_assignments with a soft-deleted project_id must return 404."""
    project_id = await _create_and_delete_project(admin_client)

    resp = await admin_client.post(
        "/api/v1/role_assignments",
        json={
            "principal_id": str(test_user.id),
            "role_name": "project-admin",
            "project_id": project_id,
        },
    )

    assert resp.status_code == 404
    data = resp.json()
    assert data["code"] == "RESOURCE_NOT_FOUND"
    assert project_id in data["detail"]


# ============================================================================
# PermissionChecker layer: non-admin users get 404 (not 403) for deleted projects.
# Before the PermissionChecker fix, these would return 403 because the checker
# silently degraded to system scope and the user lacked system permissions.
# ============================================================================


@pytest.mark.asyncio
async def test_permchecker_path_param_deleted_project_returns_404(jwt_client: AsyncClient) -> None:
    """PermissionChecker with project_param rejects deleted projects with 404.

    Covers path-based project_id (e.g. /projects/{id}/roles).
    A non-admin user should get 404, not 403.
    """
    project_id = await _create_and_delete_project(jwt_client)

    resp = await jwt_client.post(
        f"/api/v1/projects/{project_id}/roles",
        json={"name": f"perm-role-{uuid4().hex[:8]}", "policies": ["project-admin"]},
    )

    assert resp.status_code == 404
    assert resp.json()["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_permchecker_body_field_deleted_project_returns_404(jwt_client: AsyncClient) -> None:
    """PermissionChecker with body_project_field rejects deleted projects with 404.

    Covers body-based project_id (e.g. POST /workflows with project_id in body).
    A non-admin user should get 404, not 403.
    """
    project_id = await _create_and_delete_project(jwt_client)

    resp = await jwt_client.post(
        "/api/v1/role_assignments",
        json={
            "principal_id": str(uuid4()),
            "role_name": "project-admin",
            "project_id": project_id,
        },
    )

    assert resp.status_code == 404
    assert resp.json()["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_permchecker_nonexistent_project_path_returns_404(jwt_client: AsyncClient) -> None:
    """PermissionChecker rejects a completely nonexistent project UUID in path with 404."""
    fake_id = str(uuid4())

    resp = await jwt_client.get(f"/api/v1/projects/{fake_id}")

    assert resp.status_code == 404
    assert resp.json()["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_create_workflow_with_nonexistent_project_returns_404(jwt_client: AsyncClient) -> None:
    """POST /workflows with a totally nonexistent project_id must return 404."""
    fake_id = str(uuid4())

    resp = await jwt_client.post(
        "/api/v1/workflows",
        json={
            "name": f"phantom-wf-{uuid4().hex[:8]}",
            "project_id": fake_id,
            "workflow_definition": create_minimal_workflow_definition(),
        },
    )

    assert resp.status_code == 404
    data = resp.json()
    assert data["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_create_workflow_without_project_returns_422(jwt_client: AsyncClient) -> None:
    """POST /workflows with no project_id must return 422 (project_id is required)."""
    resp = await jwt_client.post(
        "/api/v1/workflows",
        json={
            "name": f"global-wf-{uuid4().hex[:8]}",
            "workflow_definition": create_minimal_workflow_definition(),
        },
    )

    assert resp.status_code == 422
