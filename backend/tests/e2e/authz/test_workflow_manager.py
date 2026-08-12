"""TC-1.13: Workflow Manager persona — project-scoped workflow CRUD."""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from uuid import UUID

    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.auth import api_for
from orchestrator_test_sdk.e2e.constants import MINIMAL_WORKFLOW_DEFINITION
from orchestrator_test_sdk.factories import (
    AssignProjectRoleFactory,
    ProjectFactory,
    ProjectRoleFactory,
    UserFactory,
    WorkflowFactory,
    get_bearer_token_type_id,
)
from syntara_api_client.models.credential_create import CredentialCreate
from syntara_api_client.models.credential_create_inputs import CredentialCreateInputs

pytestmark = [pytest.mark.e2e]

_POLICIES = [
    "workflow:create:project",
    "workflow:read:project",
    "workflow:update:project",
    "workflow:delete:project",
]


@pytest.fixture(scope="module")
def workflow_manager_env(
    admin_api: SyntaraApiRegistry,
    create_project: ProjectFactory,
    create_project_role: ProjectRoleFactory,
    create_user: UserFactory,
    assign_project_role_to_user: AssignProjectRoleFactory,
    syntara_base_url: str,
) -> tuple[SyntaraApiRegistry, UUID]:
    """Create project, user, role, assignment and return the user's API."""
    user_id, name, password = create_user(admin_api, "wfmgr")
    project_id, _ = create_project(admin_api, "wfmgr")

    role_name = create_project_role(admin_api, project_id, "wfmgr", _POLICIES)
    assign_project_role_to_user(admin_api, project_id, user_id, role_name)

    user_api = api_for(syntara_base_url, name, password)
    return user_api, project_id


class TestWorkflowManagerAllowed:
    """Positive: workflow CRUD within the project."""

    def test_create_workflow(self, workflow_manager_env, create_workflow: WorkflowFactory):
        user_api, project_id = workflow_manager_env
        wf_name = unique_name("e2e-rbac-wf-wfmgr")
        workflow_id, workflow_name = create_workflow(
            user_api, project_id, name=wf_name, definition=MINIMAL_WORKFLOW_DEFINITION
        )
        assert workflow_id is not None
        assert str(workflow_name).startswith("e2e-rbac-wf-")

    def test_list_workflows(self, workflow_manager_env):
        user_api, project_id = workflow_manager_env
        resp = user_api.projects.list_workflows(project_id=project_id)
        assert resp.status_code == HTTPStatus.OK


class TestWorkflowManagerDenied:
    """Negative: actions outside the workflow scope."""

    def test_cannot_create_credential(self, workflow_manager_env, admin_api: SyntaraApiRegistry):
        user_api, project_id = workflow_manager_env
        # Fetch a valid credential type id via admin so the failure is purely authz
        type_id = get_bearer_token_type_id(admin_api)

        resp = user_api.credentials.create(
            body=CredentialCreate(
                name="should-fail",
                credential_type_id=type_id,
                project_id=project_id,
                inputs=CredentialCreateInputs.from_dict({"token": "nope"}),
            ),
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN
