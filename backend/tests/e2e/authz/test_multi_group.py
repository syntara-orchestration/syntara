"""TC-1.9: Multi-group membership -- permissions from multiple groups are additive."""

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
    remove_from_group,
)
from syntara_api_client.models.workflow_create import WorkflowCreate

pytestmark = [pytest.mark.e2e]


class TestMultiGroupMembership:
    """User in group-ops and group-security gets union of both groups' permissions.

    group-ops  -> workflow:read + workflow:create
    group-security -> credential:read
    """

    def test_both_groups_grant_full_access(
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
    ) -> None:
        """User in both group-ops and group-security gets union of permissions from both groups."""
        proj_id, _ = create_project(admin_api, "multi")
        user_id, name, password = create_user(admin_api, "multi")

        # group-ops: workflow read + create
        ops_group_id, _ = create_group(admin_api, "ops")
        ops_role = create_project_role(
            admin_api,
            proj_id,
            "ops",
            ["workflow:read:project", "workflow:create:project"],
        )
        assign_project_role_to_group(admin_api, proj_id, ops_group_id, ops_role)

        # group-security: credential read
        sec_group_id, _ = create_group(admin_api, "security")
        sec_role = create_project_role(
            admin_api,
            proj_id,
            "security",
            ["credential:read:project"],
        )
        assign_project_role_to_group(admin_api, proj_id, sec_group_id, sec_role)

        add_to_group(admin_api, ops_group_id, user_id)
        add_to_group(admin_api, sec_group_id, user_id)

        # Seed resources
        create_workflow(admin_api, proj_id, "multi-seed")
        create_credential(admin_api, proj_id, "multi-seed")

        user_api = api_for(syntara_base_url, name, password)

        # workflow:read from ops
        user_api.projects.list_workflows(project_id=proj_id).assert_and_get()

        # workflow:create from ops
        user_api.workflows.create(
            body=WorkflowCreate(
                name=unique_name("multi"),
                workflow_definition=MINIMAL_WORKFLOW_DEFINITION,
                project_id=proj_id,
            ),
        ).assert_and_get()

        # credential:read from security
        user_api.credentials.list().assert_and_get()

    def test_removing_from_ops_revokes_only_ops_permissions(
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
        """Removing user from group-ops revokes workflow:create but keeps credential:read."""
        proj_id, _ = create_project(admin_api, "multi-rev")
        user_id, name, password = create_user(admin_api, "multi-rev")

        ops_group_id, _ = create_group(admin_api, "ops-rev")
        ops_role = create_project_role(
            admin_api,
            proj_id,
            "ops-rev",
            ["workflow:read:project", "workflow:create:project"],
        )
        assign_project_role_to_group(admin_api, proj_id, ops_group_id, ops_role)

        sec_group_id, _ = create_group(admin_api, "sec-rev")
        sec_role = create_project_role(
            admin_api,
            proj_id,
            "sec-rev",
            ["credential:read:project"],
        )
        assign_project_role_to_group(admin_api, proj_id, sec_group_id, sec_role)

        add_to_group(admin_api, ops_group_id, user_id)
        add_to_group(admin_api, sec_group_id, user_id)

        create_credential(admin_api, proj_id, "multi-rev-seed")

        # -- remove from ops --
        remove_from_group(admin_api, ops_group_id, user_id)

        # Re-login to pick up new permissions
        user_api = api_for(syntara_base_url, name, password)

        # credential:read still works (from security group)
        user_api.credentials.list().assert_and_get()

        # workflow:create no longer works
        resp = user_api.workflows.create(
            body=WorkflowCreate(
                name=unique_name("multi-rev"),
                workflow_definition=MINIMAL_WORKFLOW_DEFINITION,
                project_id=proj_id,
            ),
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN

        # workflow:read no longer works
        assert user_api.projects.list_workflows(project_id=proj_id).status_code == HTTPStatus.FORBIDDEN

    def test_removing_from_security_revokes_only_security_permissions(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_group: GroupFactory,
        create_credential: CredentialFactory,
        create_project_role: ProjectRoleFactory,
        create_user: UserFactory,
        assign_project_role_to_group: AssignProjectRoleFactory,
        create_workflow,
    ) -> None:
        """Removing user from group-security revokes credential:read but keeps workflow access."""
        proj_id, _ = create_project(admin_api, "multi-rsec")
        user_id, name, password = create_user(admin_api, "multi-rsec")

        ops_group_id, _ = create_group(admin_api, "ops-rsec")
        ops_role = create_project_role(
            admin_api,
            proj_id,
            "ops-rsec",
            ["workflow:read:project", "workflow:create:project"],
        )
        assign_project_role_to_group(admin_api, proj_id, ops_group_id, ops_role)

        sec_group_id, _ = create_group(admin_api, "sec-rsec")
        sec_role = create_project_role(
            admin_api,
            proj_id,
            "sec-rsec",
            ["credential:read:project"],
        )
        assign_project_role_to_group(admin_api, proj_id, sec_group_id, sec_role)

        add_to_group(admin_api, ops_group_id, user_id)
        add_to_group(admin_api, sec_group_id, user_id)

        create_workflow(admin_api, proj_id, "multi-rsec-seed")

        # -- remove from security --
        remove_from_group(admin_api, sec_group_id, user_id)

        user_api = api_for(syntara_base_url, name, password)

        # workflow:read still works (from ops group)
        user_api.projects.list_workflows(project_id=proj_id).assert_and_get()

        # workflow:create still works
        user_api.workflows.create(
            body=WorkflowCreate(
                name=unique_name("multi-rsec"),
                workflow_definition=MINIMAL_WORKFLOW_DEFINITION,
                project_id=proj_id,
            ),
        ).assert_and_get()

        # credential:read no longer works (visibility-filtered -- returns empty, not 403)
        cred_id, *_ = create_credential(admin_api, proj_id, "multi-rsec-cred")
        cred_list = user_api.credentials.list().assert_and_get()
        resource_ids = {str(r.id) for r in cred_list.resources}
        assert str(cred_id) not in resource_ids, f"User removed from security group should not see credential {cred_id}"
