"""E2E coverage for form-prompt responder restrictions and submit permission.

Submitting a response requires BOTH the form_prompt:submit permission on the
prompt's project AND membership of the prompt's responder lists. When both
responder lists are empty the membership check is skipped and the permission
alone governs.
"""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models import WorkflowCreate, WorkflowRead

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e.auth import api_for
from orchestrator_test_sdk.factories import (
    AssignProjectRoleFactory,
    GroupFactory,
    ProjectFactory,
    ProjectRoleFactory,
    UserFactory,
    add_to_group,
)
from syntara_api_client.models.activity_data_output_data_type_0 import ActivityDataOutputDataType0

from ._helpers import (
    assert_consumer_completed,
    assert_forbidden,
    assert_prompt_not_consumed,
    assert_responders_configured,
    get_form_prompt,
    start_pending_form_prompt,
    submit_form_prompt,
)
from ._workflows import APPROVAL_REASON_FIELD

pytestmark = [pytest.mark.e2e]

_SUBMIT_POLICIES = ["form_prompt:read:project", "form_prompt:submit:project"]
_READ_ONLY_POLICIES = ["form_prompt:read:project"]
_RESPONSE = {"reason": "approved by e2e"}


@pytest.fixture(scope="module")
def responder_env(
    admin_api: SyntaraApiRegistry,
    create_project: ProjectFactory,
    create_project_role: ProjectRoleFactory,
    create_user: UserFactory,
    create_group: GroupFactory,
    assign_project_role_to_user: AssignProjectRoleFactory,
    syntara_base_url: str,
) -> dict[str, Any]:
    """Project, two groups, and four users with distinct form-prompt access."""
    project_id, _ = create_project(admin_api, "form-prompt-rbac")

    submitter_role = create_project_role(admin_api, project_id, "fp-submitter", _SUBMIT_POLICIES)
    reader_role = create_project_role(admin_api, project_id, "fp-reader", _READ_ONLY_POLICIES)

    # group_names=[] keeps users out of the seeded `users` group, which carries
    # project-user (and therefore form_prompt:submit) on the default project.
    user_a_id, user_a_name, user_a_pass = create_user(admin_api, "fp-allowed", group_names=[])
    user_b_id, user_b_name, user_b_pass = create_user(admin_api, "fp-outsider", group_names=[])
    user_c_id, user_c_name, user_c_pass = create_user(admin_api, "fp-nosubmit", group_names=[])
    user_d_id, user_d_name, user_d_pass = create_user(admin_api, "fp-neither", group_names=[])

    assign_project_role_to_user(admin_api, project_id, user_a_id, submitter_role)
    assign_project_role_to_user(admin_api, project_id, user_b_id, submitter_role)
    assign_project_role_to_user(admin_api, project_id, user_c_id, reader_role)
    assign_project_role_to_user(admin_api, project_id, user_d_id, submitter_role)

    other_project_id, _ = create_project(admin_api, "form-prompt-other-project")
    other_project_submitter_role = create_project_role(
        admin_api,
        other_project_id,
        "fp-other-project-submitter",
        _SUBMIT_POLICIES,
    )
    assign_project_role_to_user(admin_api, other_project_id, user_c_id, other_project_submitter_role)

    group_x_id, group_x_name = create_group(admin_api, "fp-grp-allowed")
    group_y_id, group_y_name = create_group(admin_api, "fp-grp-other")
    add_to_group(admin_api, group_x_id, user_a_id)
    add_to_group(admin_api, group_x_id, user_c_id)
    add_to_group(admin_api, group_y_id, user_b_id)

    return {
        "project_id": project_id,
        "user_a_name": user_a_name,
        "user_b_name": user_b_name,
        "user_c_name": user_c_name,
        "user_d_name": user_d_name,
        "user_a_api": api_for(syntara_base_url, user_a_name, user_a_pass),
        "user_b_api": api_for(syntara_base_url, user_b_name, user_b_pass),
        "user_c_api": api_for(syntara_base_url, user_c_name, user_c_pass),
        "user_d_api": api_for(syntara_base_url, user_d_name, user_d_pass),
        "group_x_name": group_x_name,
        "group_y_name": group_y_name,
    }


def _start(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    responder_env: dict[str, Any],
    track_execution: Callable[[UUID], None],
    *,
    prefix: str,
    responder_users: list[str] | None = None,
    responder_groups: list[str] | None = None,
) -> tuple[UUID, UUID]:
    """Start a workflow with configured responders and return its IDs."""
    exec_id, prompt_row = start_pending_form_prompt(
        syntara_api,
        workflow_factory,
        responder_env["project_id"],
        workflow_name_prefix=f"e2e-form-prompt-{prefix}",
        description="Form prompt responder access control",
        track_execution=track_execution,
        producer_output={"ready": True},
        form_fields=[APPROVAL_REASON_FIELD],
        responder_users=responder_users,
        responder_groups=responder_groups,
    )
    prompt_id = UUID(str(prompt_row.id))
    assert_responders_configured(
        get_form_prompt(syntara_api, prompt_id),
        expected_users=responder_users,
        expected_groups=responder_groups,
    )
    return exec_id, prompt_id


class TestResponderUsers:
    """Form prompts restricted to explicitly named usernames."""

    def test_responder_user_can_submit(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        responder_env: dict[str, Any],
        form_prompt_execution_cleanup: Callable[[UUID], None],
    ) -> None:
        """A named responder with submit permission can submit successfully.

        Procedure:
        1. Start a workflow whose form prompt names user A as its responder.
        2. Submit a valid response as A.
        3. Wait for the workflow to finish and inspect the prompt activity output.

        Expected:
        - The submit returns 200 and the consumer completes.
        - The prompt activity records a submitted outcome.
        """
        exec_id, prompt_id = _start(
            syntara_api,
            workflow_factory,
            responder_env,
            form_prompt_execution_cleanup,
            prefix="responder-user-submit",
            responder_users=[responder_env["user_a_name"]],
        )
        response = submit_form_prompt(responder_env["user_a_api"], prompt_id, _RESPONSE)
        assert response.status_code == HTTPStatus.OK

        final = assert_consumer_completed(syntara_api, exec_id)
        activities = {activity.activity_id: activity for activity in (final.activities or [])}
        prompt_activity = activities["prompt"]
        assert isinstance(prompt_activity.output_data, ActivityDataOutputDataType0)
        assert prompt_activity.output_data.to_dict()["outcome"] == "submitted"

    def test_user_with_permission_but_not_responder_is_forbidden(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        responder_env: dict[str, Any],
        form_prompt_execution_cleanup: Callable[[UUID], None],
    ) -> None:
        """A submit-capable user outside the responder list is rejected.

        Procedure:
        1. Start a prompt restricted to user A.
        2. Submit as user B, who has submit permission but is not a responder.
        3. Confirm the prompt remains pending, then submit as A.

        Expected:
        - B receives 403 FORM_PROMPT_NOT_AUTHORIZED.
        - The rejected request leaves the prompt live and A can complete it.
        """
        exec_id, prompt_id = _start(
            syntara_api,
            workflow_factory,
            responder_env,
            form_prompt_execution_cleanup,
            prefix="non-responder-user",
            responder_users=[responder_env["user_a_name"]],
        )
        response = submit_form_prompt(responder_env["user_b_api"], prompt_id, _RESPONSE)
        assert_forbidden(response, expected_code="FORM_PROMPT_NOT_AUTHORIZED")
        assert_prompt_not_consumed(syntara_api, exec_id, prompt_id)

        response = submit_form_prompt(responder_env["user_a_api"], prompt_id, _RESPONSE)
        assert response.status_code == HTTPStatus.OK
        assert_consumer_completed(syntara_api, exec_id)

    def test_responder_user_without_submit_permission_is_forbidden(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        responder_env: dict[str, Any],
        form_prompt_execution_cleanup: Callable[[UUID], None],
    ) -> None:
        """A listed responder without the submit permission is rejected by RBAC.

        Procedure:
        1. Start a prompt restricted to users A and C.
        2. Submit as C, who is listed but has only read permission.
        3. Confirm the prompt remains pending, then submit as A.

        Expected:
        - C receives 403 AUTHORIZATION_DENIED.
        - The rejected request leaves the prompt live and A can complete it.
        """
        exec_id, prompt_id = _start(
            syntara_api,
            workflow_factory,
            responder_env,
            form_prompt_execution_cleanup,
            prefix="responder-user-no-permission",
            responder_users=[responder_env["user_a_name"], responder_env["user_c_name"]],
        )
        response = submit_form_prompt(responder_env["user_c_api"], prompt_id, _RESPONSE)
        assert_forbidden(response, expected_code="AUTHORIZATION_DENIED")
        assert_prompt_not_consumed(syntara_api, exec_id, prompt_id)

        response = submit_form_prompt(responder_env["user_a_api"], prompt_id, _RESPONSE)
        assert response.status_code == HTTPStatus.OK
        assert_consumer_completed(syntara_api, exec_id)


class TestResponderGroups:
    """Form prompts restricted to members of explicitly named groups."""

    def test_responder_group_member_can_submit(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        responder_env: dict[str, Any],
        form_prompt_execution_cleanup: Callable[[UUID], None],
    ) -> None:
        """A member of the configured responder group can submit.

        Procedure:
        1. Start a prompt restricted to group X.
        2. Submit a valid response as A, a member of group X.
        3. Wait for the workflow to finish.

        Expected:
        - The submit returns 200 and the consumer completes.
        """
        exec_id, prompt_id = _start(
            syntara_api,
            workflow_factory,
            responder_env,
            form_prompt_execution_cleanup,
            prefix="responder-group-submit",
            responder_groups=[responder_env["group_x_name"]],
        )
        response = submit_form_prompt(responder_env["user_a_api"], prompt_id, _RESPONSE)
        assert response.status_code == HTTPStatus.OK
        assert_consumer_completed(syntara_api, exec_id)

    def test_member_of_other_group_is_forbidden(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        responder_env: dict[str, Any],
        form_prompt_execution_cleanup: Callable[[UUID], None],
    ) -> None:
        """A submit-capable member of another group is not an allowed responder.

        Procedure:
        1. Start a prompt restricted to group X.
        2. Submit as B, a member of group Y, and check the prompt remains pending.
        3. Submit as A, a member of group X, to prove the prompt remains usable.

        Expected:
        - B receives 403 FORM_PROMPT_NOT_AUTHORIZED.
        - The rejected request leaves the prompt live and A can complete it.
        """
        exec_id, prompt_id = _start(
            syntara_api,
            workflow_factory,
            responder_env,
            form_prompt_execution_cleanup,
            prefix="other-responder-group",
            responder_groups=[responder_env["group_x_name"]],
        )
        response = submit_form_prompt(responder_env["user_b_api"], prompt_id, _RESPONSE)
        assert_forbidden(response, expected_code="FORM_PROMPT_NOT_AUTHORIZED")
        assert_prompt_not_consumed(syntara_api, exec_id, prompt_id)

        response = submit_form_prompt(responder_env["user_a_api"], prompt_id, _RESPONSE)
        assert response.status_code == HTTPStatus.OK
        assert_consumer_completed(syntara_api, exec_id)

    def test_responder_group_member_without_submit_permission_is_forbidden(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        responder_env: dict[str, Any],
        form_prompt_execution_cleanup: Callable[[UUID], None],
    ) -> None:
        """Group membership does not bypass the submit permission check.

        Procedure:
        1. Start a prompt restricted to group X.
        2. Submit as C, who belongs to X but has only read permission.
        3. Check the prompt remains pending, then submit as A.

        Expected:
        - C receives 403 AUTHORIZATION_DENIED.
        - The rejected request leaves the prompt live and A can complete it.
        """
        exec_id, prompt_id = _start(
            syntara_api,
            workflow_factory,
            responder_env,
            form_prompt_execution_cleanup,
            prefix="responder-group-no-permission",
            responder_groups=[responder_env["group_x_name"]],
        )
        response = submit_form_prompt(responder_env["user_c_api"], prompt_id, _RESPONSE)
        assert_forbidden(response, expected_code="AUTHORIZATION_DENIED")
        assert_prompt_not_consumed(syntara_api, exec_id, prompt_id)

        response = submit_form_prompt(responder_env["user_a_api"], prompt_id, _RESPONSE)
        assert response.status_code == HTTPStatus.OK
        assert_consumer_completed(syntara_api, exec_id)


class TestCombinedResponderLists:
    """Combined responder lists allow either direct users or group members."""

    def test_named_user_can_submit_with_both_responder_lists(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        responder_env: dict[str, Any],
        form_prompt_execution_cleanup: Callable[[UUID], None],
    ) -> None:
        """A named user can submit even when outside the configured group.

        Procedure:
        1. Start a prompt naming B directly and listing group X.
        2. Submit as B, who belongs to group Y rather than group X.
        3. Wait for the workflow to finish.

        Expected:
        - Both responder lists are persisted as configured.
        - B's direct responder entry allows submission and the consumer completes.
        """
        exec_id, prompt_id = _start(
            syntara_api,
            workflow_factory,
            responder_env,
            form_prompt_execution_cleanup,
            prefix="combined-responders-direct-user",
            responder_users=[responder_env["user_b_name"]],
            responder_groups=[responder_env["group_x_name"]],
        )
        response = submit_form_prompt(responder_env["user_b_api"], prompt_id, _RESPONSE)
        assert response.status_code == HTTPStatus.OK
        assert_consumer_completed(syntara_api, exec_id)

    def test_group_member_can_submit_with_both_responder_lists(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        responder_env: dict[str, Any],
        form_prompt_execution_cleanup: Callable[[UUID], None],
    ) -> None:
        """A listed group member can submit without a direct user entry.

        Procedure:
        1. Start a prompt naming B directly and listing group X.
        2. Submit as A, who belongs to group X and is not named directly.
        3. Wait for the workflow to finish.

        Expected:
        - Both responder lists are persisted as configured.
        - A's group membership allows submission and the consumer completes.
        """
        exec_id, prompt_id = _start(
            syntara_api,
            workflow_factory,
            responder_env,
            form_prompt_execution_cleanup,
            prefix="combined-responders-group-member",
            responder_users=[responder_env["user_b_name"]],
            responder_groups=[responder_env["group_x_name"]],
        )
        response = submit_form_prompt(responder_env["user_a_api"], prompt_id, _RESPONSE)
        assert response.status_code == HTTPStatus.OK
        assert_consumer_completed(syntara_api, exec_id)

    def test_user_matching_neither_responder_list_is_forbidden(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        responder_env: dict[str, Any],
        form_prompt_execution_cleanup: Callable[[UUID], None],
    ) -> None:
        """A submit-capable user matching neither list is rejected.

        Procedure:
        1. Start a prompt naming B directly and listing group X.
        2. Submit as D, who has submit permission but is neither named nor in X.
        3. Check the prompt remains pending, then submit as A through group X.

        Expected:
        - D receives 403 FORM_PROMPT_NOT_AUTHORIZED.
        - The rejection leaves the prompt live and A can complete it.
        """
        exec_id, prompt_id = _start(
            syntara_api,
            workflow_factory,
            responder_env,
            form_prompt_execution_cleanup,
            prefix="combined-responders-outsider",
            responder_users=[responder_env["user_b_name"]],
            responder_groups=[responder_env["group_x_name"]],
        )
        response = submit_form_prompt(responder_env["user_d_api"], prompt_id, _RESPONSE)
        assert_forbidden(response, expected_code="FORM_PROMPT_NOT_AUTHORIZED")
        assert_prompt_not_consumed(syntara_api, exec_id, prompt_id)

        response = submit_form_prompt(responder_env["user_a_api"], prompt_id, _RESPONSE)
        assert response.status_code == HTTPStatus.OK
        assert_consumer_completed(syntara_api, exec_id)


class TestEmptyResponderLists:
    """Empty responder lists preserve permission-only submission access."""

    def test_user_with_submit_permission_can_submit(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        responder_env: dict[str, Any],
        form_prompt_execution_cleanup: Callable[[UUID], None],
    ) -> None:
        """A user with submit permission can submit when responder lists are empty.

        Procedure:
        1. Start a prompt without responder restrictions.
        2. Submit a valid response as A.
        3. Wait for the workflow to finish.

        Expected:
        - Both persisted responder lists are empty.
        - The submit returns 200 and the consumer completes.
        """
        exec_id, prompt_id = _start(
            syntara_api,
            workflow_factory,
            responder_env,
            form_prompt_execution_cleanup,
            prefix="empty-responders-user-a",
        )
        response = submit_form_prompt(responder_env["user_a_api"], prompt_id, _RESPONSE)
        assert response.status_code == HTTPStatus.OK
        assert_consumer_completed(syntara_api, exec_id)

    def test_user_with_submit_permission_only_in_another_project_is_forbidden(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        responder_env: dict[str, Any],
        form_prompt_execution_cleanup: Callable[[UUID], None],
    ) -> None:
        """Submit permission assigned to another project does not authorize this prompt.

        Procedure:
        1. Start a prompt without responder restrictions.
        2. Submit as C, who has form_prompt:submit on another project but only read here.
        3. Confirm the prompt remains pending, then submit as A.

        Expected:
        - Both persisted responder lists are empty.
        - C receives 403 AUTHORIZATION_DENIED and A can still complete the prompt.
        """
        exec_id, prompt_id = _start(
            syntara_api,
            workflow_factory,
            responder_env,
            form_prompt_execution_cleanup,
            prefix="empty-responders-other-project-role",
        )
        response = submit_form_prompt(responder_env["user_c_api"], prompt_id, _RESPONSE)
        assert_forbidden(response, expected_code="AUTHORIZATION_DENIED")
        assert_prompt_not_consumed(syntara_api, exec_id, prompt_id)

        response = submit_form_prompt(responder_env["user_a_api"], prompt_id, _RESPONSE)
        assert response.status_code == HTTPStatus.OK
        assert_consumer_completed(syntara_api, exec_id)

    def test_user_without_submit_permission_is_forbidden(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        responder_env: dict[str, Any],
        form_prompt_execution_cleanup: Callable[[UUID], None],
    ) -> None:
        """An empty responder list does not grant submit permission by itself.

        Procedure:
        1. Start a prompt without responder restrictions.
        2. Submit as C, who has only read permission, and check the prompt remains pending.
        3. Submit as A to prove the prompt remains usable.

        Expected:
        - Both persisted responder lists are empty.
        - C receives 403 AUTHORIZATION_DENIED, then A completes the prompt.
        """
        exec_id, prompt_id = _start(
            syntara_api,
            workflow_factory,
            responder_env,
            form_prompt_execution_cleanup,
            prefix="empty-responders-no-permission",
        )
        response = submit_form_prompt(responder_env["user_c_api"], prompt_id, _RESPONSE)
        assert_forbidden(response, expected_code="AUTHORIZATION_DENIED")
        assert_prompt_not_consumed(syntara_api, exec_id, prompt_id)

        response = submit_form_prompt(responder_env["user_a_api"], prompt_id, _RESPONSE)
        assert response.status_code == HTTPStatus.OK
        assert_consumer_completed(syntara_api, exec_id)
