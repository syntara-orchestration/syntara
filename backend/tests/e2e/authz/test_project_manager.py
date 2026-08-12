"""TC-1.16: Project Manager persona -- global project create/read."""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

if TYPE_CHECKING:
    from orchestrator_test_sdk.factories import RoleFactory, UserFactory, UserRoleAssignmentFactory
    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set -- full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e import (
    generate_test_password,
    unique_name,
)
from orchestrator_test_sdk.e2e.auth import api_for
from syntara_api_client.models.project_create import ProjectCreate
from syntara_api_client.models.role_create import RoleCreate
from syntara_api_client.models.user_create import UserCreate

pytestmark = [pytest.mark.e2e]

_POLICIES = [
    "project:create:any",
    "project:read:any",
]


@pytest.fixture(scope="module")
def project_manager_env(
    admin_api: SyntaraApiRegistry,
    create_role: RoleFactory,
    create_user: UserFactory,
    assign_system_role: UserRoleAssignmentFactory,
    syntara_base_url: str,
) -> tuple[SyntaraApiRegistry, UUID]:
    """Create user with system-level project manager role."""
    user_id, name, password = create_user(admin_api, "projmgr")

    role_name = create_role(admin_api, "projmgr", _POLICIES)
    assign_system_role(admin_api, user_id, role_name)
    user_api = api_for(syntara_base_url, name, password)
    return user_api, user_id


class TestProjectManagerAllowed:
    """Positive: create and list projects."""

    def test_create_project(self, project_manager_env):
        user_api, _user_id = project_manager_env
        resp = user_api.projects.create(body=ProjectCreate(name=unique_name("e2e-rbac-projmgr-new")))
        project = resp.assert_and_get()
        project_id = UUID(str(project.id))
        project_name = str(project.name)
        assert project_id is not None
        assert project_name.startswith("e2e-rbac-")

    def test_list_projects(self, project_manager_env):
        user_api, _user_id = project_manager_env
        user_api.projects.list().assert_and_get()


class TestProjectManagerDenied:
    """Negative: cannot create users or system roles."""

    def test_cannot_create_user(self, project_manager_env):
        user_api, _user_id = project_manager_env
        resp = user_api.users.create(
            body=UserCreate(
                username="should-fail-user",
                email="fail@example.com",
                first_name="Should Fail",
                password=generate_test_password(),
            ),
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN

    def test_cannot_create_system_role(self, project_manager_env):
        user_api, _user_id = project_manager_env
        resp = user_api.roles.create(
            body=RoleCreate(name="should-fail-role", policies=["workflow:read:any"]),
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN
