"""TC-1.7: Cross-project isolation — roles on one project do not leak to another."""

from __future__ import annotations

import os
from http import HTTPStatus
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

from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.auth import api_for
from orchestrator_test_sdk.e2e.constants import MINIMAL_WORKFLOW_DEFINITION
from syntara_api_client.models.workflow_create import WorkflowCreate

pytestmark = [pytest.mark.e2e]


class TestCrossProjectIsolation:
    """User with different roles on two projects gets correct access on each."""

    def test_writer_on_alpha_reader_on_beta(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_project_role: ProjectRoleFactory,
        create_user: UserFactory,
        assign_project_role_to_user: AssignProjectRoleFactory,
        create_workflow: WorkflowFactory,
    ) -> None:
        # -- setup --
        alpha_id, _ = create_project(admin_api, "alpha")
        beta_id, _ = create_project(admin_api, "beta")
        user_id, user_name, user_pass = create_user(admin_api, "cross")

        # Writer role: read + create workflows
        writer_role = create_project_role(
            admin_api,
            alpha_id,
            "writer",
            ["workflow:read:project", "workflow:create:project"],
        )
        assign_project_role_to_user(admin_api, alpha_id, user_id, writer_role)

        # Reader role: read-only workflows
        reader_role = create_project_role(
            admin_api,
            beta_id,
            "reader",
            ["workflow:read:project"],
        )
        assign_project_role_to_user(admin_api, beta_id, user_id, reader_role)

        # Seed a workflow in each project so reads return data
        create_workflow(admin_api, alpha_id, "alpha-seed")
        create_workflow(admin_api, beta_id, "beta-seed")

        user_api = api_for(syntara_base_url, user_name, user_pass)

        # -- can read workflows in alpha --
        user_api.projects.list_workflows(project_id=alpha_id).assert_successful()

        # -- can create workflow in alpha --
        create_workflow(
            api=user_api, project_id=alpha_id, name=unique_name("cross-alpha"), definition=MINIMAL_WORKFLOW_DEFINITION
        )

        # -- can read workflows in beta --
        user_api.projects.list_workflows(project_id=beta_id).assert_successful()

        # -- cannot create workflow in beta --
        resp_beta_create = user_api.workflows.create(
            body=WorkflowCreate(
                name=unique_name("cross-beta"),
                workflow_definition=MINIMAL_WORKFLOW_DEFINITION,
                project_id=beta_id,
            ),
        )
        assert resp_beta_create.status_code == HTTPStatus.FORBIDDEN
