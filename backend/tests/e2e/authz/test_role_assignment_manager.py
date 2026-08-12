"""TC-1.17: Role Assignment Manager persona — assign/revoke project roles."""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest

if TYPE_CHECKING:
    from orchestrator_test_sdk.factories import (
        AssignProjectRoleFactory,
        ProjectFactory,
        ProjectRoleFactory,
        UserFactory,
    )
    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e.auth import api_for
from orchestrator_test_sdk.e2e.constants import MINIMAL_WORKFLOW_DEFINITION
from syntara_api_client.models.role_assignment_create import RoleAssignmentCreate
from syntara_api_client.models.sub_resource_role_assignment_create import SubResourceRoleAssignmentCreate
from syntara_api_client.models.workflow_create import WorkflowCreate

pytestmark = [pytest.mark.e2e]

_POLICIES = [
    "role-assignment:assign:project",
    "role-assignment:read:project",
    "role-assignment:revoke:project",
]


@pytest.fixture(scope="module")
def role_assignment_manager_env(
    admin_api: SyntaraApiRegistry,
    create_project: ProjectFactory,
    create_project_role: ProjectRoleFactory,
    create_user: UserFactory,
    assign_project_role_to_user: AssignProjectRoleFactory,
    syntara_base_url: str,
) -> dict[str, Any]:
    """Create project, manager user, target user, and a role to assign."""
    project_id, _ = create_project(admin_api, "rolemgr")

    # Manager user — can assign/revoke roles in the project
    mgr_id, mgr_name, mgr_pass = create_user(admin_api, "rolemgr")

    mgr_role = create_project_role(admin_api, project_id, "rolemgr", _POLICIES)
    assign_project_role_to_user(admin_api, project_id, mgr_id, mgr_role)
    mgr_api = api_for(syntara_base_url, mgr_name, mgr_pass)

    # Target user — will receive/lose the "project-user" built-in role
    target_id, target_name, target_pass = create_user(admin_api, "roletgt")

    return {
        "mgr_api": mgr_api,
        "project_id": project_id,
        "mgr_id": mgr_id,
        "target_id": target_id,
        "base_url": syntara_base_url,
        "target_user": target_name,
        "target_pass": target_pass,
    }


class TestRoleAssignmentManagerAllowed:
    """Positive: assign, list, and revoke project roles."""

    def test_assign_list_revoke_cycle(self, role_assignment_manager_env):
        role_env = role_assignment_manager_env
        mgr_api = role_env["mgr_api"]
        project_id = role_env["project_id"]
        target_id = role_env["target_id"]
        base_url = role_env["base_url"]
        target_user = role_env["target_user"]
        target_pass = role_env["target_pass"]

        # 1. Assign "project-user" to target
        assign_resp = mgr_api.projects.create_role_assignment(
            project_id=project_id,
            body=RoleAssignmentCreate(
                principal_id=target_id,
                role_name="project-user",
            ),
        )
        assert assign_resp.status_code in (HTTPStatus.OK, HTTPStatus.CREATED), (
            f"Expected assignment to succeed, got {assign_resp.status_code}"
        )
        assignment = assign_resp.parsed
        assignment_id = UUID(str(assignment.id))

        # 2. List assignments — should include the one we just created
        assignments_list = mgr_api.projects.list_role_assignments(project_id=project_id).assert_and_get()
        ids = [str(a.id) for a in assignments_list.resources]
        assert str(assignment_id) in ids

        # 3. Target user should now have access (can list workflows in project)
        target_api = api_for(base_url, target_user, target_pass)
        target_api.projects.list_workflows(project_id=project_id).assert_and_get()

        # 4. Revoke the assignment
        del_resp = mgr_api.projects.delete_role_assignment(
            project_id=project_id,
            assignment_id=assignment_id,
        )
        assert del_resp.status_code in (HTTPStatus.NO_CONTENT, HTTPStatus.OK)

        # 5. Target user should lose access
        target_api2 = api_for(base_url, target_user, target_pass)
        wf_resp2 = target_api2.projects.list_workflows(project_id=project_id)
        assert wf_resp2.status_code == HTTPStatus.FORBIDDEN


class TestRoleAssignmentManagerDenied:
    """Negative: cannot assign system roles or create workflows."""

    def test_cannot_assign_system_role(self, role_assignment_manager_env):
        """Role assignment manager cannot assign system roles (scope boundary enforcement)."""
        role_env = role_assignment_manager_env
        mgr_api = role_env["mgr_api"]
        target_id = role_env["target_id"]
        resp = mgr_api.users.create_role_assignment(
            user_id=target_id,
            body=SubResourceRoleAssignmentCreate(role_name="admin"),
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN

    def test_cannot_create_workflow(self, role_assignment_manager_env):
        """Role assignment manager cannot create workflows (limited to role management only)."""
        from orchestrator_test_sdk.e2e import unique_name

        role_env = role_assignment_manager_env
        mgr_api = role_env["mgr_api"]
        project_id = role_env["project_id"]
        resp = mgr_api.workflows.create(
            body=WorkflowCreate(
                name=unique_name("should-fail"),
                workflow_definition=MINIMAL_WORKFLOW_DEFINITION,
                project_id=project_id,
            ),
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN
