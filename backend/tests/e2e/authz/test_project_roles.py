"""TC-1.1: Project-scoped custom role grants read-only access."""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from orchestrator_test_sdk.factories import (
        AssignProjectRoleFactory,
        CredentialFactory,
        ProjectFactory,
        ProjectRoleFactory,
        UserFactory,
        WorkflowFactory,
    )
    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e.auth import api_for
from orchestrator_test_sdk.e2e.constants import MINIMAL_WORKFLOW_DEFINITION
from syntara_api_client.models.workflow_create import WorkflowCreate

pytestmark = [pytest.mark.e2e]

READ_ONLY_POLICIES = [
    "workflow:read:project",
    "credential:read:project",
    "execution:read:project",
]


@pytest.fixture(scope="module")
def project_roles_env(
    admin_api: SyntaraApiRegistry,
    create_project: ProjectFactory,
    create_workflow: WorkflowFactory,
    create_credential: CredentialFactory,
    create_project_role: ProjectRoleFactory,
    create_user: UserFactory,
    assign_project_role_to_user: AssignProjectRoleFactory,
    syntara_base_url: str,
) -> dict[str, Any]:
    """Create project, role, user, resources, and assign role."""
    user_id, name, password = create_user(admin_api, "tc11")
    project_id, _ = create_project(admin_api, "tc11-proj")

    # Create role and assign
    role_name = create_project_role(admin_api, project_id, "reader", READ_ONLY_POLICIES)
    assignment_id = assign_project_role_to_user(admin_api, project_id, user_id, role_name)

    # Seed a workflow and credential
    create_workflow(admin_api, project_id, "tc11")
    create_credential(admin_api, project_id, "tc11")

    limited_api = api_for(syntara_base_url, name, password)
    return {
        "project_id": project_id,
        "role_name": role_name,
        "user_id": user_id,
        "assignment_id": assignment_id,
        "limited_api": limited_api,
        "admin_api": admin_api,
    }


class TestProjectRoles:
    """TC-1.1: Project-scoped custom role grants read-only access."""

    # -- Read access granted by custom role ------------------------------------

    def test_can_read_workflows(self, project_roles_env):
        workflows_list = (
            project_roles_env["limited_api"]
            .projects.list_workflows(
                project_id=project_roles_env["project_id"],
            )
            .assert_and_get()
        )
        assert len(workflows_list.resources) >= 1

    def test_can_read_credentials(self, project_roles_env):
        credentials_list = project_roles_env["limited_api"].credentials.list().assert_and_get()
        assert len(credentials_list.resources) >= 1

    # -- Write access denied ---------------------------------------------------

    def test_cannot_create_workflow(self, project_roles_env):
        resp = project_roles_env["limited_api"].workflows.create(
            body=WorkflowCreate(
                name="should-fail",
                workflow_definition=MINIMAL_WORKFLOW_DEFINITION,
                project_id=project_roles_env["project_id"],
            ),
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN

    # -- Role appears in project role/assignment listings -----------------------

    def test_role_listed_in_roles(self, project_roles_env):
        roles_list = project_roles_env["admin_api"].roles.list().assert_and_get()
        role_names = [r.name for r in roles_list.resources]
        assert project_roles_env["role_name"] in role_names

    def test_assignment_listed_in_project(self, project_roles_env):
        assignments_list = (
            project_roles_env["admin_api"]
            .projects.list_role_assignments(
                project_id=project_roles_env["project_id"],
            )
            .assert_and_get()
        )
        assignment_ids = [str(a.id) for a in assignments_list.resources]
        assert str(project_roles_env["assignment_id"]) in assignment_ids
