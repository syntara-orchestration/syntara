"""Integration tests for credential RBAC authorization.

Tests the permission matrix (6 roles x 5 actions) and project isolation
for credential endpoints. Follows the patterns in test_authz_hardening.py.

All credentials must belong to a project (Option B — no global credentials).
"""

from collections.abc import Awaitable, Callable
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import Project
from syntara.core.models import User
from syntara.credentials.models.credential_type import CredentialType
from tests.integration.api.conftest import (
    make_admin,
    make_auditor,
    make_user_role,
)


@pytest.fixture
async def bearer_type(test_db_session: AsyncSession) -> CredentialType:
    """Create a bearer token credential type for RBAC tests."""
    ct = CredentialType(
        name=f"RBAC Test Bearer {uuid4().hex[:8]}",
        description="Bearer token type for RBAC tests",
        inputs={
            "fields": [
                {"id": "token", "label": "Token", "type": "string", "secret": True},
            ],
            "required": ["token"],
        },
        injectors={"extra_vars": {"bearer_token": "{{token}}"}, "env": {}, "file": {}},
        managed=False,
    )
    test_db_session.add(ct)
    await test_db_session.commit()
    await test_db_session.refresh(ct)
    return ct


@pytest.fixture
async def test_project(test_db_session: AsyncSession) -> Project:
    """Create a test project for credential RBAC tests."""
    project = Project(name=f"rbac-test-{uuid4().hex[:8]}", description="RBAC test project")
    test_db_session.add(project)
    await test_db_session.commit()
    await test_db_session.refresh(project)
    return project


def _cred_payload(type_id: str, project_id: str, name: str | None = None) -> dict[str, object]:
    """Build a credential create payload. project_id is required."""
    return {
        "name": name or f"test-cred-{uuid4().hex[:8]}",
        "credential_type_id": type_id,
        "inputs": {"token": "test-secret-value"},
        "project_id": project_id,
    }


# ============================================================================
# Permission Matrix: Role x Action
# ============================================================================


class TestAdminPermissions:
    """Admin role can perform all credential operations."""

    @pytest.mark.asyncio
    async def test_admin_can_create(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        bearer_type: CredentialType,
        test_project: Project,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        admin = await user_factory(username="admin-cred-c", email="admin-cred-c@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.post(
            "/api/v1/credentials",
            json=_cred_payload(str(bearer_type.id), str(test_project.id)),
        )
        assert resp.status_code == 201
        assert resp.json()["project_id"] == str(test_project.id)

    @pytest.mark.asyncio
    async def test_admin_can_list(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        admin = await user_factory(username="admin-cred-l", email="admin-cred-l@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.get("/api/v1/credentials")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_delete(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        bearer_type: CredentialType,
        test_project: Project,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        admin = await user_factory(username="admin-cred-d", email="admin-cred-d@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.post(
            "/api/v1/credentials",
            json=_cred_payload(str(bearer_type.id), str(test_project.id)),
        )
        assert resp.status_code == 201
        cred_id = resp.json()["id"]

        resp = await auth_client.delete(f"/api/v1/credentials/{cred_id}")
        assert resp.status_code == 204


class TestUserPermissions:
    """User role cannot access credentials (no credential policies)."""

    @pytest.mark.asyncio
    async def test_user_cannot_create(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        bearer_type: CredentialType,
        test_project: Project,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        user = await user_factory(username="user-uc", email="user-uc@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)
        resp = await auth_client.post(
            "/api/v1/credentials",
            json=_cred_payload(str(bearer_type.id), str(test_project.id)),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_user_cannot_read(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        bearer_type: CredentialType,
        test_project: Project,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        admin = await user_factory(username="admin-ur", email="admin-ur@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        resp = await auth_client.post(
            "/api/v1/credentials",
            json=_cred_payload(str(bearer_type.id), str(test_project.id)),
        )
        assert resp.status_code == 201
        cred_id = resp.json()["id"]

        user = await user_factory(username="user-ur", email="user-ur@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)
        resp = await auth_client.get(f"/api/v1/credentials/{cred_id}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_user_cannot_delete(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        bearer_type: CredentialType,
        test_project: Project,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        admin = await user_factory(username="admin-ud", email="admin-ud@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        resp = await auth_client.post(
            "/api/v1/credentials",
            json=_cred_payload(str(bearer_type.id), str(test_project.id)),
        )
        assert resp.status_code == 201
        cred_id = resp.json()["id"]

        user = await user_factory(username="user-ud", email="user-ud@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)
        resp = await auth_client.delete(f"/api/v1/credentials/{cred_id}")
        assert resp.status_code == 403


class TestAuditorPermissions:
    """Auditor role can only read credentials."""

    @pytest.mark.asyncio
    async def test_auditor_can_list(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        auditor = await user_factory(username="auditor-cl", email="auditor-cl@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.get("/api/v1/credentials")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_auditor_cannot_create(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        bearer_type: CredentialType,
        test_project: Project,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        auditor = await user_factory(username="auditor-cc", email="auditor-cc@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.post(
            "/api/v1/credentials",
            json=_cred_payload(str(bearer_type.id), str(test_project.id)),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_auditor_cannot_update(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        bearer_type: CredentialType,
        test_project: Project,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        admin = await user_factory(username="admin-au", email="admin-au@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        resp = await auth_client.post(
            "/api/v1/credentials",
            json=_cred_payload(str(bearer_type.id), str(test_project.id)),
        )
        assert resp.status_code == 201
        cred_id = resp.json()["id"]

        auditor = await user_factory(username="auditor-au", email="auditor-au@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)
        resp = await auth_client.patch(
            f"/api/v1/credentials/{cred_id}",
            json={"name": "hacked"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_auditor_cannot_delete(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        bearer_type: CredentialType,
        test_project: Project,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        admin = await user_factory(username="admin-ad", email="admin-ad@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        resp = await auth_client.post(
            "/api/v1/credentials",
            json=_cred_payload(str(bearer_type.id), str(test_project.id)),
        )
        assert resp.status_code == 201
        cred_id = resp.json()["id"]

        auditor = await user_factory(username="auditor-ad", email="auditor-ad@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)
        resp = await auth_client.delete(f"/api/v1/credentials/{cred_id}")
        assert resp.status_code == 403


# ============================================================================
# Project Isolation
# ============================================================================


class TestProjectIsolation:
    """All credentials must belong to a project (Option B)."""

    @pytest.mark.asyncio
    async def test_credential_requires_project_id(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        bearer_type: CredentialType,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Creating a credential without project_id returns 422."""
        admin = await user_factory(username="admin-req", email="admin-req@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.post(
            "/api/v1/credentials",
            json={
                "name": "missing-project",
                "credential_type_id": str(bearer_type.id),
                "inputs": {"token": "test"},
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_credential_with_project_id(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        bearer_type: CredentialType,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Credential with project_id is stored correctly."""
        admin = await user_factory(username="admin-pi", email="admin-pi@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.post("/api/v1/projects", json={"name": "cred-test-proj"})
        assert resp.status_code == 201
        project_id = resp.json()["id"]

        resp = await auth_client.post(
            "/api/v1/credentials",
            json=_cred_payload(str(bearer_type.id), project_id, name="proj-cred"),
        )
        assert resp.status_code == 201
        assert resp.json()["project_id"] == project_id

    @pytest.mark.asyncio
    async def test_credential_type_endpoints_no_rbac(
        self,
        auth_client: AsyncClient,
        bearer_type: CredentialType,
        test_user: User,
        auth_as: Callable[[User], None],
    ) -> None:
        """Credential type endpoints remain accessible without RBAC (auth-only)."""
        auth_as(test_user)

        resp = await auth_client.get("/api/v1/credential_types")
        assert resp.status_code == 200

        resp = await auth_client.get(f"/api/v1/credential_types/{bearer_type.id}")
        assert resp.status_code == 200
