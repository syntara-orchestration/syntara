"""E2E coverage for Form Trigger submission authorization."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

    from orchestrator_test_sdk.factories import (
        AssignProjectRoleFactory,
        ProjectFactory,
        ProjectRoleFactory,
        UserFactory,
    )
    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models import WorkflowCreate, WorkflowRead

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e.auth import api_for

from ._helpers import (
    assert_consumer_completed,
    assert_forbidden,
    assert_no_executions_for_workflow,
    create_form_trigger_workflow,
    submit_form_trigger,
    submit_form_trigger_and_track,
)
from ._workflows import REQUIRED_AND_OPTIONAL_FIELDS

pytestmark = [pytest.mark.e2e]

_NAME_PREFIX = "e2e-form-trigger-permissions"
_DESCRIPTION = "E2E: authorize Form Trigger submissions"
_AUTHORIZED_POLICIES = ["workflow:read:project", "execution:run:project", "execution:read:project"]
_DENIED_POLICIES = ["workflow:read:project", "execution:read:project"]
_VALID_SUBMISSION: dict[str, Any] = {
    "required_text": "authorized submission",
    "required_email": "tester@example.com",
    "optional_number": 7,
}


@pytest.fixture(scope="module")
def form_trigger_permission_env(
    admin_api: SyntaraApiRegistry,
    syntara_base_url: str,
    create_user: UserFactory,
    create_project: ProjectFactory,
    create_project_role: ProjectRoleFactory,
    assign_project_role_to_user: AssignProjectRoleFactory,
) -> dict[str, Any]:
    """Project plus users with and without execution:run permission."""
    project_id, _ = create_project(admin_api, "form-trigger-perm")

    def _user_api(prefix: str, policies: list[str]) -> SyntaraApiRegistry:
        user_id, username, password = create_user(admin_api, prefix, group_names=[])
        role_name = create_project_role(admin_api, project_id, prefix, policies)
        assign_project_role_to_user(admin_api, project_id, user_id, role_name)
        return api_for(syntara_base_url, username, password)

    return {
        "project_id": project_id,
        "allowed_api": _user_api("ft-allowed", _AUTHORIZED_POLICIES),
        "denied_api": _user_api("ft-denied", _DENIED_POLICIES),
    }


def _build_workflow(
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    project_id: UUID,
) -> WorkflowRead:
    """Build this module's Form Trigger workflow in its dedicated project."""
    return create_form_trigger_workflow(
        workflow_factory,
        project_id,
        name_prefix=_NAME_PREFIX,
        description=_DESCRIPTION,
        form_fields=REQUIRED_AND_OPTIONAL_FIELDS,
    )


def test_user_with_execution_run_can_submit_form_trigger(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    form_trigger_permission_env: dict[str, Any],
    form_execution_cleanup: Callable[[UUID], None],
) -> None:
    """A project user with execution:run can start and complete a Form Trigger.

    Procedure:
    1. Create a Form Trigger workflow in the dedicated project.
    2. Submit valid data as the user with execution:run:project.
    3. Wait for the execution's consumer node to complete.

    Expected:
    - The submission creates an execution and its consumer completes.
    """
    workflow = _build_workflow(workflow_factory, form_trigger_permission_env["project_id"])
    execution = submit_form_trigger_and_track(
        form_trigger_permission_env["allowed_api"],
        workflow,
        _VALID_SUBMISSION,
        form_execution_cleanup,
    )

    assert_consumer_completed(syntara_api, UUID(str(execution.id)))


def test_user_without_execution_run_is_denied_and_no_execution_is_created(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    form_trigger_permission_env: dict[str, Any],
) -> None:
    """A project reader without execution:run cannot start a Form Trigger.

    Procedure:
    1. Create a Form Trigger workflow in the dedicated project.
    2. Submit valid data as the user without execution:run:project.
    3. Check the response and list executions with the admin API.

    Expected:
    - The submission returns 403 AUTHORIZATION_DENIED.
    - No execution exists for the workflow.
    """
    workflow = _build_workflow(workflow_factory, form_trigger_permission_env["project_id"])
    response = submit_form_trigger(
        form_trigger_permission_env["denied_api"],
        workflow,
        _VALID_SUBMISSION,
    )

    assert_forbidden(response, expected_code="AUTHORIZATION_DENIED")
    assert_no_executions_for_workflow(syntara_api, UUID(str(workflow.id)))


def test_authorization_is_enforced_before_form_validation(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    form_trigger_permission_env: dict[str, Any],
) -> None:
    """Authorization rejects the request before required-field validation runs.

    Procedure:
    1. Create a Form Trigger workflow with required fields.
    2. Submit an empty payload as the user without execution:run:project.
    3. Check the response and list executions with the admin API.

    Expected:
    - The submission returns 403 AUTHORIZATION_DENIED rather than 422.
    - No execution exists for the workflow.
    """
    workflow = _build_workflow(workflow_factory, form_trigger_permission_env["project_id"])
    response = submit_form_trigger(form_trigger_permission_env["denied_api"], workflow, {})

    assert_forbidden(response, expected_code="AUTHORIZATION_DENIED")
    assert_no_executions_for_workflow(syntara_api, UUID(str(workflow.id)))
