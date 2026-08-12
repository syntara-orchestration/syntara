"""TC-1.12: Credentials Manager persona — project-scoped credential CRUD."""

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
    CredentialFactory,
    ProjectFactory,
    ProjectRoleFactory,
    UserFactory,
    get_bearer_token_type_id,
)
from syntara_api_client.models.workflow_create import WorkflowCreate

pytestmark = [pytest.mark.e2e]

# Policies that define the "credentials manager" persona
_POLICIES = [
    "credential:create:project",
    "credential:read:project",
    "credential:update:project",
    "credential:delete:project",
]


@pytest.fixture(scope="module")
def credentials_manager_env(
    admin_api: SyntaraApiRegistry,
    create_user: UserFactory,
    create_project_role: ProjectRoleFactory,
    create_project: ProjectFactory,
    assign_project_role_to_user: AssignProjectRoleFactory,
    syntara_base_url: str,
) -> tuple[SyntaraApiRegistry, UUID]:
    """Create project, user, role, assignment and return the user's API."""
    user_id, name, password = create_user(admin_api, "credmgr")
    project_id, _ = create_project(admin_api, "credmgr")

    role_name = create_project_role(admin_api, project_id, "credmgr", _POLICIES)
    assign_project_role_to_user(admin_api, project_id, user_id, role_name)

    user_api = api_for(syntara_base_url, name, password)
    return user_api, project_id


class TestCredentialsManagerAllowed:
    """Positive: credential CRUD within the project."""

    def test_create_and_list_credential(
        self, credentials_manager_env, admin_api: SyntaraApiRegistry, create_credential: CredentialFactory
    ):
        user_api, project_id = credentials_manager_env
        cred_name = unique_name("e2e-rbac-cred-credmgr")
        type_id = get_bearer_token_type_id(admin_api)
        create_credential(api=user_api, project_id=project_id, name=cred_name, type_id=type_id)

        cred_list = user_api.credentials.list().assert_and_get()
        listed_names = [str(c.name) for c in cred_list.resources]
        assert cred_name in listed_names


class TestCredentialsManagerDenied:
    """Negative: actions outside the credential scope."""

    def test_cannot_create_workflow(self, credentials_manager_env):
        user_api, project_id = credentials_manager_env
        resp = user_api.workflows.create(
            body=WorkflowCreate(
                name="should-fail",
                workflow_definition=MINIMAL_WORKFLOW_DEFINITION,
                project_id=project_id,
            ),
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN
