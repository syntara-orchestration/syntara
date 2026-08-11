"""Integration tests for credential:use permission.

Tests the credential:use permission across roles, the for_action=use
list filter, and the credential:use check at workflow save time.
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
    make_project_admin,
    make_project_user,
    make_user_role,
)


@pytest.fixture
async def bearer_type(test_db_session: AsyncSession) -> CredentialType:
    """Create a bearer token credential type."""
    ct = CredentialType(
        name=f"Use-Perm Bearer {uuid4().hex[:8]}",
        description="Bearer token type for credential:use tests",
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
    """Create a test project."""
    project = Project(name=f"use-perm-test-{uuid4().hex[:8]}", description="credential:use test project")
    test_db_session.add(project)
    await test_db_session.commit()
    await test_db_session.refresh(project)
    return project


def _cred_payload(type_id: str, project_id: str) -> dict[str, object]:
    return {
        "name": f"test-cred-{uuid4().hex[:8]}",
        "credential_type_id": type_id,
        "inputs": {"token": "test-secret-value"},
        "project_id": project_id,
    }


# ============================================================================
# credential:use permission in role_conventions (Unit 1 verification)
# ============================================================================


class TestCredentialUseInResourceActions:
    """Verify credential:use appears in the resource-actions API."""

    @pytest.mark.asyncio
    async def test_credential_use_in_resource_actions(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        admin = await user_factory(username="admin-ra", email="admin-ra@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.get("/api/v1/authz/resource_actions")
        assert resp.status_code == 200
        actions = resp.json().get("resource_actions", {})
        assert "use" in actions.get("credential", [])


# ============================================================================
# for_action=use list filter (Unit 3 verification)
# ============================================================================


class TestForActionUseFilter:
    """Test the for_action=use query parameter on credential list."""

    @pytest.mark.asyncio
    async def test_admin_sees_credentials_with_for_action_use(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        bearer_type: CredentialType,
        test_project: Project,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Admin has credential:use and sees credentials."""
        admin = await user_factory(username="admin-fau", email="admin-fau@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        await auth_client.post(
            "/api/v1/credentials",
            json=_cred_payload(str(bearer_type.id), str(test_project.id)),
        )

        resp = await auth_client.get("/api/v1/credentials", params={"for_action": "use"})
        assert resp.status_code == 200
        assert len(resp.json()["resources"]) >= 1

    @pytest.mark.asyncio
    async def test_auditor_sees_empty_with_for_action_use(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        bearer_type: CredentialType,
        test_project: Project,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Auditor has credential:read but NOT credential:use — empty list."""
        admin = await user_factory(username="admin-fau2", email="admin-fau2@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        await auth_client.post(
            "/api/v1/credentials",
            json=_cred_payload(str(bearer_type.id), str(test_project.id)),
        )

        auditor = await user_factory(username="auditor-fau", email="auditor-fau@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.get("/api/v1/credentials", params={"for_action": "use"})
        assert resp.status_code == 200
        assert len(resp.json()["resources"]) == 0

    @pytest.mark.asyncio
    async def test_default_filter_returns_readable_credentials(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        bearer_type: CredentialType,
        test_project: Project,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Without for_action, auditor can read credentials (backward compatible)."""
        admin = await user_factory(username="admin-df", email="admin-df@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        await auth_client.post(
            "/api/v1/credentials",
            json=_cred_payload(str(bearer_type.id), str(test_project.id)),
        )

        auditor = await user_factory(username="auditor-df", email="auditor-df@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.get("/api/v1/credentials")
        assert resp.status_code == 200
        assert len(resp.json()["resources"]) >= 1

    @pytest.mark.asyncio
    async def test_project_user_sees_project_credentials_with_use(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        bearer_type: CredentialType,
        test_project: Project,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Project-user has credential:use at project scope — sees project credentials."""
        admin = await user_factory(username="admin-pu", email="admin-pu@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        await auth_client.post(
            "/api/v1/credentials",
            json=_cred_payload(str(bearer_type.id), str(test_project.id)),
        )

        proj_user = await user_factory(username="puser-fau", email="puser-fau@test.com")
        await make_project_user(test_db_session, proj_user, test_project)
        auth_as(proj_user)

        resp = await auth_client.get("/api/v1/credentials", params={"for_action": "use"})
        assert resp.status_code == 200
        assert len(resp.json()["resources"]) >= 1


# ============================================================================
# credential:use role permission matrix
# ============================================================================


class TestCredentialUsePermissionMatrix:
    """Verify which roles have credential:use via the can_i endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("role_setup", "expected"),
        [
            ("admin", True),
            ("auditor", False),
            ("user", False),
        ],
        ids=["admin-has-use", "auditor-no-use", "user-no-use"],
    )
    async def test_system_role_credential_use(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        role_setup: str,
        expected: bool,  # noqa: FBT001
    ) -> None:
        user = await user_factory(
            username=f"{role_setup}-cu-{uuid4().hex[:4]}",
            email=f"{role_setup}-cu-{uuid4().hex[:4]}@test.com",
        )
        if role_setup == "admin":
            await make_admin(test_db_session, user)
        elif role_setup == "auditor":
            await make_auditor(test_db_session, user)
        else:
            await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"resource_type": "credential", "action": "use"},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("role_setup", "expected"),
        [
            ("project-admin", True),
            ("project-user", True),
        ],
        ids=["project-admin-has-use", "project-user-has-use"],
    )
    async def test_project_role_credential_use(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project: Project,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        role_setup: str,
        expected: bool,  # noqa: FBT001
    ) -> None:
        user = await user_factory(
            username=f"{role_setup}-cu-{uuid4().hex[:4]}",
            email=f"{role_setup}-cu-{uuid4().hex[:4]}@test.com",
        )
        if role_setup == "project-admin":
            await make_project_admin(test_db_session, user, test_project)
        else:
            await make_project_user(test_db_session, user, test_project)
        auth_as(user)

        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={
                "resource_type": "credential",
                "action": "use",
                "resource_project": str(test_project.id),
            },
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is expected
