"""TC-1.3: Manager with role-assignment permission can delegate access."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from orchestrator_test_sdk.factories import (
        AssignProjectRoleFactory,
        ProjectFactory,
        ProjectRoleFactory,
        UserFactory,
        WorkflowFactory,
    )
    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)


from orchestrator_test_sdk.e2e.auth import api_for

pytestmark = [pytest.mark.e2e]

MANAGER_POLICIES = [
    "role-assignment:assign:project",
    "role-assignment:read:project",
    "project:read:project",
]

VIEWER_POLICIES = [
    "workflow:read:project",
]


@pytest.fixture(scope="module")
def delegated_access_env(
    admin_api: SyntaraApiRegistry,
    create_project: ProjectFactory,
    create_project_role: ProjectRoleFactory,
    create_user: UserFactory,
    assign_project_role_to_user: AssignProjectRoleFactory,
    create_workflow: WorkflowFactory,
    syntara_base_url: str,
):
    """Create project, manager role, viewer role, manager user, newcomer user."""
    # Create project
    project_id, _ = create_project(admin_api, "tc13")

    # Create the viewer role that the manager will assign
    viewer_role = create_project_role(admin_api, project_id, "viewer", VIEWER_POLICIES)

    # Create the manager role with delegation permissions
    manager_role = create_project_role(admin_api, project_id, "manager", MANAGER_POLICIES)

    # Create manager user
    mgr_id, mgr_name, mgr_pass = create_user(admin_api, "tc13-mgr")

    # Create newcomer user
    new_id, new_name, new_pass = create_user(admin_api, "tc13-new")

    # Assign manager role to manager user (admin does this)
    assign_project_role_to_user(admin_api, project_id, mgr_id, manager_role)

    # Seed a workflow for the newcomer to read later
    create_workflow(admin_api, project_id, "tc13")

    mgr_api = api_for(syntara_base_url, mgr_name, mgr_pass)
    return {
        "project_id": project_id,
        "viewer_role": viewer_role,
        "new_id": new_id,
        "new_user": new_name,
        "new_pass": new_pass,
        "mgr_api": mgr_api,
        "base_url": syntara_base_url,
    }


class TestDelegatedAccess:
    """TC-1.3: Manager with role-assignment permission can delegate access."""

    # -- Manager delegates the viewer role to the newcomer ---------------------

    def test_newcomer_can_read_workflows(
        self, delegated_access_env, assign_project_role_to_user: AssignProjectRoleFactory
    ):
        # Validate that manager can assign role to the newcomer
        assign_project_role_to_user(
            api=delegated_access_env["mgr_api"],
            project_id=delegated_access_env["project_id"],
            user_or_group_id=delegated_access_env["new_id"],
            role_name=delegated_access_env["viewer_role"],
        )
        newcomer_api = api_for(
            delegated_access_env["base_url"],
            delegated_access_env["new_user"],
            delegated_access_env["new_pass"],
        )
        workflows_list = newcomer_api.projects.list_workflows(
            project_id=delegated_access_env["project_id"]
        ).assert_and_get()
        assert len(workflows_list.resources) >= 1

    # -- Manager can list role assignments -------------------------------------

    def test_manager_can_list_assignments(self, delegated_access_env):
        assignments_list = (
            delegated_access_env["mgr_api"]
            .projects.list_role_assignments(
                project_id=delegated_access_env["project_id"],
            )
            .assert_and_get()
        )
        assert len(assignments_list.resources) >= 1
