"""TC-1.4: Group role + direct role stacking for two members."""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.auth import api_for
from orchestrator_test_sdk.e2e.constants import MINIMAL_WORKFLOW_DEFINITION
from orchestrator_test_sdk.factories import (
    AssignProjectRoleFactory,
    GroupFactory,
    ProjectFactory,
    ProjectRoleFactory,
    UserFactory,
    WorkflowFactory,
    add_to_group,
)
from syntara_api_client.models.workflow_create import WorkflowCreate

pytestmark = [pytest.mark.e2e]

READ_POLICIES = [
    "workflow:read:project",
    "credential:read:project",
]

WRITE_POLICIES = [
    "workflow:create:project",
    "workflow:update:project",
]


@pytest.fixture(scope="module")
def group_access_env(
    admin_api: SyntaraApiRegistry,
    assign_project_role_to_group: AssignProjectRoleFactory,
    assign_project_role_to_user: AssignProjectRoleFactory,
    create_group: GroupFactory,
    create_user: UserFactory,
    create_project: ProjectFactory,
    create_project_role: ProjectRoleFactory,
    create_workflow: WorkflowFactory,
    syntara_base_url: str,
):
    """Create project, group, two users, and assign roles."""
    # Create project
    project_id, _ = create_project(admin_api, "tc14")

    # Roles
    reader_role = create_project_role(admin_api, project_id, "grp-reader", READ_POLICIES)
    writer_role = create_project_role(admin_api, project_id, "grp-writer", WRITE_POLICIES)

    # Group
    group_id, _ = create_group(admin_api, "tc14-grp")

    # User 1 (group only)
    u1_id, u1_name, u1_pass = create_user(admin_api, "tc14-grponly")

    # User 2 (group + direct)
    u2_id, u2_name, u2_pass = create_user(admin_api, "tc14-grpdirect")

    # Both users in the group
    add_to_group(admin_api, group_id, u1_id)
    add_to_group(admin_api, group_id, u2_id)

    # Group gets read-only role
    assign_project_role_to_group(admin_api, project_id, group_id, reader_role)

    # User 2 additionally gets direct writer role
    assign_project_role_to_user(admin_api, project_id, u2_id, writer_role)

    # Seed a workflow for read tests
    create_workflow(admin_api, project_id, "tc14")

    u1_api = api_for(syntara_base_url, u1_name, u1_pass)
    u2_api = api_for(syntara_base_url, u2_name, u2_pass)
    return {
        "project_id": project_id,
        "u1_api": u1_api,
        "u2_api": u2_api,
    }


class TestGroupAccess:
    """TC-1.4: Group role + direct role stacking for two members."""

    # -- User 1 (group only): read OK, create denied ---------------------------

    def test_group_only_can_read_workflows(self, group_access_env):
        workflows_list = (
            group_access_env["u1_api"]
            .projects.list_workflows(
                project_id=group_access_env["project_id"],
            )
            .assert_and_get()
        )
        assert len(workflows_list.resources) >= 1

    def test_group_only_cannot_create_workflow(self, group_access_env):
        resp = group_access_env["u1_api"].workflows.create(
            body=WorkflowCreate(
                name="should-fail-grp",
                workflow_definition=MINIMAL_WORKFLOW_DEFINITION,
                project_id=group_access_env["project_id"],
            ),
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN

    # -- User 2 (group + direct): read OK, create OK --------------------------

    def test_group_plus_direct_can_read_workflows(self, group_access_env):
        workflows_list = (
            group_access_env["u2_api"]
            .projects.list_workflows(
                project_id=group_access_env["project_id"],
            )
            .assert_and_get()
        )
        assert len(workflows_list.resources) >= 1

    def test_group_plus_direct_can_create_workflow(self, group_access_env):
        resp = group_access_env["u2_api"].workflows.create(
            body=WorkflowCreate(
                name=unique_name("grp-direct"),
                workflow_definition=MINIMAL_WORKFLOW_DEFINITION,
                project_id=group_access_env["project_id"],
            ),
        )
        assert resp.status_code == HTTPStatus.CREATED
