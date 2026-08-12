"""TC-1.8: Role stacking -- group role + direct role combine additively."""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set -- full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.auth import api_for
from orchestrator_test_sdk.e2e.constants import MINIMAL_WORKFLOW_DEFINITION
from orchestrator_test_sdk.factories import (
    AssignProjectRoleFactory,
    CredentialFactory,
    GroupFactory,
    ProjectFactory,
    ProjectRoleFactory,
    UserFactory,
    WorkflowFactory,
    add_to_group,
)
from syntara_api_client.models.workflow_create import WorkflowCreate

pytestmark = [pytest.mark.e2e]


class TestRoleStacking:
    """Group role grants workflow:read, direct role grants credential:read + workflow:create.

    Together the user can do all three; neither role alone covers everything.
    """

    def test_group_plus_direct_role_union(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_group: GroupFactory,
        create_workflow: WorkflowFactory,
        create_credential: CredentialFactory,
        create_project_role: ProjectRoleFactory,
        create_user: UserFactory,
        assign_project_role_to_group: AssignProjectRoleFactory,
        assign_project_role_to_user: AssignProjectRoleFactory,
    ) -> None:
        """User gets union of permissions from group role and direct role assignment."""
        # -- setup --
        proj_id, _ = create_project(admin_api, "stack")
        user_id, name, password = create_user(admin_api, "stack")
        group_id, _ = create_group(admin_api, "stack")
        add_to_group(admin_api, group_id, user_id)

        # Group role: workflow:read only
        group_role = create_project_role(
            admin_api,
            proj_id,
            "grp-reader",
            ["workflow:read:project"],
        )
        assign_project_role_to_group(admin_api, proj_id, group_id, group_role)

        # Direct role: credential:read + workflow:create
        direct_role = create_project_role(
            admin_api,
            proj_id,
            "direct-mixed",
            ["credential:read:project", "workflow:create:project"],
        )
        assign_project_role_to_user(admin_api, proj_id, user_id, direct_role)

        # Seed resources
        create_workflow(admin_api, proj_id, "stack-seed")
        create_credential(admin_api, proj_id, "stack-seed")

        user_api = api_for(syntara_base_url, name, password)

        # -- workflow:read (from group role) --
        user_api.projects.list_workflows(project_id=proj_id).assert_and_get()

        # -- credential:read (from direct role) --
        user_api.credentials.list().assert_and_get()

        # -- workflow:create (from direct role) --
        user_api.workflows.create(
            body=WorkflowCreate(
                name=unique_name("stack"),
                workflow_definition=MINIMAL_WORKFLOW_DEFINITION,
                project_id=proj_id,
            ),
        ).assert_and_get()

    def test_group_role_alone_insufficient(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_group: GroupFactory,
        create_credential: CredentialFactory,
        create_project_role: ProjectRoleFactory,
        create_user: UserFactory,
        assign_project_role_to_group: AssignProjectRoleFactory,
    ) -> None:
        """A user with only the group role cannot create workflows or read credentials."""
        proj_id, _ = create_project(admin_api, "stack-grp")
        user_id, name, password = create_user(admin_api, "stack-grp")
        group_id, _ = create_group(admin_api, "stack-grp")
        add_to_group(admin_api, group_id, user_id)

        group_role = create_project_role(
            admin_api,
            proj_id,
            "grp-only",
            ["workflow:read:project"],
        )
        assign_project_role_to_group(admin_api, proj_id, group_id, group_role)

        user_api = api_for(syntara_base_url, name, password)

        # Can read workflows
        user_api.projects.list_workflows(project_id=proj_id).assert_and_get()

        # Cannot create workflows
        resp = user_api.workflows.create(
            body=WorkflowCreate(
                name=unique_name("stack-grp-fail"),
                workflow_definition=MINIMAL_WORKFLOW_DEFINITION,
                project_id=proj_id,
            ),
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN

        # Cannot read credentials (visibility-filtered -- returns empty, not 403)
        cred_id, *_ = create_credential(admin_api, proj_id, "stack-grp-deny")
        cred_list = user_api.credentials.list().assert_and_get()
        resource_ids = {str(r.id) for r in cred_list.resources}
        assert str(cred_id) not in resource_ids, f"Group-only user should not see credential {cred_id}"

    def test_direct_role_alone_insufficient(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_project_role: ProjectRoleFactory,
        create_user: UserFactory,
        assign_project_role_to_user: AssignProjectRoleFactory,
    ) -> None:
        """A user with only the direct role cannot read workflows (only create)."""
        proj_id, _ = create_project(admin_api, "stack-dir")
        user_id, name, password = create_user(admin_api, "stack-dir")

        direct_role = create_project_role(
            admin_api,
            proj_id,
            "dir-only",
            ["credential:read:project", "workflow:create:project"],
        )
        assign_project_role_to_user(admin_api, proj_id, user_id, direct_role)

        user_api = api_for(syntara_base_url, name, password)

        # Cannot read workflows (no workflow:read:project)
        resp = user_api.projects.list_workflows(project_id=proj_id)
        assert resp.status_code == HTTPStatus.FORBIDDEN
