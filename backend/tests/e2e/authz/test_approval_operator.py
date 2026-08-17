"""TC-1.15: Approval Operator persona — list/decide approvals."""

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

from orchestrator_test_sdk.e2e.auth import api_for
from orchestrator_test_sdk.e2e.constants import MINIMAL_WORKFLOW_DEFINITION
from orchestrator_test_sdk.factories import (
    AssignProjectRoleFactory,
    ProjectFactory,
    ProjectRoleFactory,
    UserFactory,
    get_bearer_token_type_id,
)
from syntara_api_client.models.credential_create import CredentialCreate
from syntara_api_client.models.credential_create_inputs import CredentialCreateInputs
from syntara_api_client.models.workflow_create import WorkflowCreate

pytestmark = [pytest.mark.e2e]

_POLICIES = [
    "approval:read:project",
    "approval:decide:project",
]


@pytest.fixture(scope="module")
def approval_operator_env(
    admin_api: SyntaraApiRegistry,
    create_user: UserFactory,
    create_project: ProjectFactory,
    create_project_role: ProjectRoleFactory,
    assign_project_role_to_user: AssignProjectRoleFactory,
    syntara_base_url: str,
) -> tuple[SyntaraApiRegistry, UUID]:
    """Create project, user with approval policies."""
    user_id, name, password = create_user(admin_api, "approv")
    project_id, _ = create_project(admin_api, "approv")

    role_name = create_project_role(admin_api, project_id, "approv", _POLICIES)
    assign_project_role_to_user(admin_api, project_id, user_id, role_name)

    user_api = api_for(syntara_base_url, name, password)
    return user_api, project_id


class TestApprovalOperatorAllowed:
    """Positive: list approvals."""

    def test_list_approvals(self, approval_operator_env):
        user_api, _project_id = approval_operator_env
        resp = user_api.approvals.list()
        assert resp.status_code == HTTPStatus.OK


class TestApprovalOperatorDenied:
    """Negative: cannot create workflows or credentials."""

    def test_cannot_create_workflow(self, approval_operator_env):
        user_api, project_id = approval_operator_env
        resp = user_api.workflows.create(
            body=WorkflowCreate(
                name="should-fail",
                workflow_definition=MINIMAL_WORKFLOW_DEFINITION,
                project_id=project_id,
            ),
        )
        assert resp.status_code == HTTPStatus.FORBIDDEN

    def test_cannot_create_credential(self, approval_operator_env, admin_api: SyntaraApiRegistry):
        user_api, project_id = approval_operator_env
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
