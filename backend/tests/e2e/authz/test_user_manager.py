"""TC-1.18: User Manager persona — global user create/read/update."""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from uuid import UUID

    from orchestrator_test_sdk.factories import RoleFactory, UserFactory, UserRoleAssignmentFactory
    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e import generate_test_password
from orchestrator_test_sdk.e2e.auth import api_for
from syntara_api_client.models.role_create import RoleCreate
from syntara_api_client.models.sub_resource_role_assignment_create import SubResourceRoleAssignmentCreate
from syntara_api_client.models.user_create import UserCreate
from syntara_api_client.models.user_update import UserUpdate

pytestmark = [pytest.mark.e2e]

_POLICIES = [
    "user:create:any",
    "user:read:any",
    "user:update:any",
]


@pytest.fixture(scope="module")
def user_manager_env(
    admin_api: SyntaraApiRegistry,
    create_role: RoleFactory,
    assign_system_role: UserRoleAssignmentFactory,
    create_user: UserFactory,
    syntara_base_url: str,
) -> tuple[SyntaraApiRegistry, UUID]:
    """Create user with system-level user manager role."""
    user_id, name, password = create_user(admin_api, "usermgr")

    role_name = create_role(admin_api, "usermgr", _POLICIES)
    assign_system_role(admin_api, user_id, role_name)

    user_api = api_for(syntara_base_url, name, password)
    return user_api, user_id


class TestUserManagerAllowed:
    """Positive: create, list, and update users."""

    def test_create_user(self, user_manager_env):
        from uuid import uuid4

        user_api, _user_id = user_manager_env
        suffix = uuid4().hex[:6]
        resp = user_api.users.create(
            body=UserCreate(
                username=f"e2e-rbac-usermgr-{suffix}",
                email=f"usermgr-{suffix}@example.com",
                first_name="Target User",
                password=generate_test_password(),
            ),
        )
        assert resp.status_code in (HTTPStatus.OK, HTTPStatus.CREATED), (
            f"Expected user creation to succeed, got {resp.status_code}"
        )
        created_user = resp.parsed
        assert created_user is not None

        # Store for later tests
        TestUserManagerAllowed._created_user_id = str(created_user.id)

    def test_list_users(self, user_manager_env):
        user_api, _user_id = user_manager_env
        user_api.users.list().assert_and_get()

    def test_update_user_first_name(self, user_manager_env):
        user_api, _user_id = user_manager_env
        target_id = getattr(TestUserManagerAllowed, "_created_user_id", None)
        if target_id is None:
            pytest.skip("Depends on test_create_user having run first")

        user_api.users.update(
            user_id=target_id,
            body=UserUpdate(first_name="Updated Name"),
        ).assert_and_get()


class TestUserManagerDenied:
    """Negative: cannot create system roles or assign roles."""

    def test_cannot_create_system_role(self, user_manager_env):
        user_api, _user_id = user_manager_env
        resp = user_api.roles.create(
            body=RoleCreate(name="should-fail-role", policies=["workflow:read:any"]),
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN

    def test_cannot_assign_role_to_user(self, user_manager_env):
        user_api, _user_id = user_manager_env
        target_id = getattr(TestUserManagerAllowed, "_created_user_id", None)
        if target_id is None:
            pytest.skip("Depends on test_create_user having run first")

        resp = user_api.users.create_role_assignment(
            user_id=target_id,
            body=SubResourceRoleAssignmentCreate(role_name="admin"),
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN
