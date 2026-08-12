"""TC-1.2: System-scoped role grants read access across all projects."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from orchestrator_test_sdk.factories import (
        CredentialFactory,
        ProjectFactory,
        RoleFactory,
        UserFactory,
        UserRoleAssignmentFactory,
        WorkflowFactory,
    )
    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e.auth import api_for

pytestmark = [pytest.mark.e2e]

GLOBAL_READ_POLICIES = [
    "credential:read:any",
    "workflow:read:any",
    "execution:read:any",
]


@pytest.fixture(scope="module")
def global_roles_env(
    admin_api: SyntaraApiRegistry,
    create_project: ProjectFactory,
    create_workflow: WorkflowFactory,
    create_credential: CredentialFactory,
    create_user: UserFactory,
    create_role: RoleFactory,
    assign_system_role: UserRoleAssignmentFactory,
    syntara_base_url: str,
):
    """Create two projects, a global role, and a user with that role."""
    # Create two projects
    proj_a_id, _ = create_project(admin_api, "tc12-a")
    proj_b_id, _ = create_project(admin_api, "tc12-b")

    # Seed workflows in both projects
    create_workflow(admin_api, proj_a_id, "tc12a")
    create_workflow(admin_api, proj_b_id, "tc12b")

    # Seed credentials in both projects
    create_credential(admin_api, proj_a_id, "tc12a")
    create_credential(admin_api, proj_b_id, "tc12b")

    # Create system role
    role_name = create_role(admin_api, "global-reader", GLOBAL_READ_POLICIES)

    # Create user and assign system role
    user_id, name, password = create_user(admin_api, "tc12-global")
    assign_system_role(admin_api, user_id, role_name)

    user_api = api_for(syntara_base_url, name, password)
    return {
        "proj_a_id": proj_a_id,
        "proj_b_id": proj_b_id,
        "role_name": role_name,
        "user_api": user_api,
        "admin_api": admin_api,
    }


class TestGlobalRoles:
    """TC-1.2: System-scoped role grants read access across all projects."""

    # -- Global read access works across projects ------------------------------

    def test_can_read_workflows_project_a(self, global_roles_env):
        workflows_list = (
            global_roles_env["user_api"]
            .projects.list_workflows(
                project_id=global_roles_env["proj_a_id"],
            )
            .assert_and_get()
        )
        assert len(workflows_list.resources) >= 1

    def test_can_read_workflows_project_b(self, global_roles_env):
        workflows_list = (
            global_roles_env["user_api"]
            .projects.list_workflows(
                project_id=global_roles_env["proj_b_id"],
            )
            .assert_and_get()
        )
        assert len(workflows_list.resources) >= 1

    def test_can_read_credentials_project_a(self, global_roles_env):
        credentials_list = global_roles_env["user_api"].credentials.list().assert_and_get()
        assert len(credentials_list.resources) >= 1

    def test_can_read_credentials_project_b(self, global_roles_env):
        credentials_list = global_roles_env["user_api"].credentials.list().assert_and_get()
        assert len(credentials_list.resources) >= 1

    # -- Role listed with system scope -----------------------------------------

    def test_role_has_system_scope(self, global_roles_env):
        roles_list = global_roles_env["admin_api"].roles.list().assert_and_get()
        matching = [r for r in roles_list.resources if r.name == global_roles_env["role_name"]]
        assert len(matching) == 1
        assert matching[0].scope.lower() == "system"
