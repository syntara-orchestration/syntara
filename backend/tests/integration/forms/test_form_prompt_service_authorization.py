"""Integration tests for form prompt permissions and responder authorization.

Test boundaries:
- ``auth_client`` injects the fixture user, so login and token validation are not exercised.
- The API tests replace the suite's allow-all evaluator getter with a wrapper around the production
  ``evaluate_policy_input``; policy decisions run through the real Rego policy.
- Submit tests that reach workflow signaling mock ``WorkflowApiClient.send_form_signal`` to avoid
  contacting Temporal and verify whether a signal would be sent.

The API routes, service, database records, role assignments, and responder memberships use the real
integration test setup.
"""

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import insert
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.engine import clear_authz_cache
from syntara.authz.evaluator import evaluate_policy_input
from syntara.authz.models import RoleAssignment
from syntara.authz.models.project import Project
from syntara.core.models import Group, User
from syntara.core.models.group import user_groups
from syntara.forms.exceptions import FormPromptNotAuthorizedError
from syntara.forms.models.api_models import FormPromptStatus
from syntara.forms.models.form_prompt import FormPrompt
from syntara.forms.models.form_prompt_responders import FormPromptResponderGroup, FormPromptResponderUser
from syntara.forms.services.form_prompt_service import FormPromptService

FORM_PROMPTS_URL = "/api/v1/form_prompts"
_FORM_DEFINITION = {"fields": [{"value_name": "reason", "type": "text", "label": "Reason", "required": True}]}
_PROJECT_ROLES = {"project-admin", "project-user", "project-auditor"}
_GET_SINGLE_CASES = [
    ("admin", "same", 200),
    ("admin", "other", 200),
    ("auditor", "same", 200),
    ("auditor", "other", 200),
    ("project-admin", "same", 200),
    ("project-admin", "other", 403),
    ("project-user", "same", 200),
    ("project-user", "other", 403),
    ("project-auditor", "same", 200),
    ("project-auditor", "other", 403),
    ("user", "same", 403),
    ("user", "other", 403),
]
_SUBMIT_PERMISSION_CASES = [
    ("admin", "same", 200),
    ("admin", "other", 200),
    ("auditor", "same", 403),
    ("project-admin", "same", 200),
    ("project-admin", "other", 403),
    ("project-user", "same", 200),
    ("project-user", "other", 403),
    ("project-auditor", "same", 403),
    ("user", "same", 403),
    ("user", "other", 403),
]


class _RealPolicyEvaluator:
    """Use the production Rego policy for route authorization in these tests."""

    def evaluate(self, authz_input: dict[str, Any]) -> dict[str, Any]:
        """Evaluate one authorization request with the production Rego policy."""
        return evaluate_policy_input(authz_input)


class _FormPromptAuthorizationSetup:
    """Create the common policy, role, project, prompt, and responder test state."""

    client: AsyncClient

    def __init__(self, session: AsyncSession, project_id: UUID, user: User) -> None:
        self.session = session
        self.project_id = project_id
        self.user = user

    def configure_api(self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
        """Use the production policy evaluator for route authorization tests."""
        self.client = client
        clear_authz_cache()
        evaluator = _RealPolicyEvaluator()
        monkeypatch.setattr("syntara.authz.dependencies.get_authz_evaluator", lambda _request: evaluator)

    async def assign_role(self, role_name: str) -> None:
        """Assign a built-in role globally or to this setup's project."""
        project_id = self.project_id if role_name in _PROJECT_ROLES else None
        self.session.add(RoleAssignment(principal_id=self.user.id, role_name=role_name, project_id=project_id))
        await self.session.commit()

    async def create_project(self, *, name_prefix: str = "form-prompt-authz") -> Project:
        """Create a project for a cross-project access case."""
        project = Project(name=f"{name_prefix}-{uuid4().hex[:8]}", description="Authorization test project")
        self.session.add(project)
        await self.session.commit()
        return project

    async def create_prompt(self, project_id: UUID | None = None) -> FormPrompt:
        """Persist a pending prompt in the selected or default test project."""
        prompt = FormPrompt(
            project_id=project_id if project_id is not None else self.project_id,
            execution_id=uuid4(),
            prompt_node_id=f"form-{uuid4().hex[:8]}",
            temporal_activity_id="form-activity",
            name="Test form",
            form_definition=_FORM_DEFINITION,
            status=FormPromptStatus.PENDING,
        )
        self.session.add(prompt)
        await self.session.commit()
        await self.session.refresh(prompt)
        return prompt

    async def create_role_prompt(self, role_name: str, project_relation: str = "same") -> FormPrompt:
        """Assign a role and create its target prompt in the requested project relation."""
        await self.assign_role(role_name)
        project_id = self.project_id
        if project_relation == "other":
            project_id = (await self.create_project()).id
        elif project_relation != "same":
            msg = f"Unknown project relation: {project_relation}"
            raise ValueError(msg)
        return await self.create_prompt(project_id)

    async def configure_responders(
        self,
        prompt: FormPrompt,
        mode: str,
        group: Group,
        other_users: list[User],
    ) -> None:
        """Persist responder rules and group membership for the selected case."""
        if mode == "user":
            self.session.add(FormPromptResponderUser(form_prompt_id=prompt.id, user_id=self.user.id))
        elif mode == "group":
            self.session.add(FormPromptResponderGroup(form_prompt_id=prompt.id, group_id=group.id))
            await self.session.exec(insert(user_groups).values(user_id=self.user.id, group_id=group.id))
        elif mode == "group_nonmember":
            self.session.add(FormPromptResponderGroup(form_prompt_id=prompt.id, group_id=group.id))
        elif mode == "neither":
            self.session.add(FormPromptResponderUser(form_prompt_id=prompt.id, user_id=other_users[0].id))
        elif mode != "empty":
            msg = f"Unknown responder test mode: {mode}"
            raise ValueError(msg)
        await self.session.commit()


@pytest.fixture
def form_prompt_setup(
    test_db_session: AsyncSession,
    test_project_id: UUID,
    test_user: User,
) -> _FormPromptAuthorizationSetup:
    """Provide reusable prompt authorization setup backed by this test's fixtures."""
    return _FormPromptAuthorizationSetup(test_db_session, test_project_id, test_user)


@pytest.mark.integration
@pytest.mark.asyncio
class TestFormPromptServiceAuthorizationAPI:
    """Integration tests for form prompt permissions and responder authorization."""

    setup: _FormPromptAuthorizationSetup

    @pytest.fixture(autouse=True)
    def _create_setup(
        self,
        form_prompt_setup: _FormPromptAuthorizationSetup,
        auth_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        form_prompt_setup.configure_api(auth_client, monkeypatch)
        self.setup = form_prompt_setup

    @pytest.mark.parametrize(("role_name", "project_relation", "expected_status"), _GET_SINGLE_CASES)
    async def test_get_single_prompt_role_scope(
        self,
        role_name: str,
        project_relation: str,
        expected_status: int,
    ) -> None:
        """Single-prompt reads follow system-wide or assigned-project read policies."""
        prompt = await self.setup.create_role_prompt(role_name, project_relation)

        response = await self.setup.client.get(f"{FORM_PROMPTS_URL}/{prompt.id}")

        assert response.status_code == expected_status
        if expected_status == 200:
            assert response.json()["id"] == str(prompt.id)
        else:
            assert response.json()["code"] == "AUTHORIZATION_DENIED"

    @pytest.mark.parametrize(
        ("role_name", "expected_visibility"),
        [
            ("admin", "all"),
            ("auditor", "all"),
            ("project-admin", "assigned"),
            ("project-user", "assigned"),
            ("project-auditor", "assigned"),
            ("user", "none"),
        ],
    )
    async def test_list_prompts_role_visibility(self, role_name: str, expected_visibility: str) -> None:
        """List reads follow system/project visibility and hide prompts from roles without read permission."""
        other_project = await self.setup.create_project()
        await self.setup.assign_role(role_name)
        own_prompt = await self.setup.create_prompt()
        other_prompt = await self.setup.create_prompt(other_project.id)

        response = await self.setup.client.get(FORM_PROMPTS_URL)

        assert response.status_code == 200
        visible_ids = {resource["id"] for resource in response.json()["resources"]}
        if expected_visibility == "all":
            expected_ids = {str(own_prompt.id), str(other_prompt.id)}
        elif expected_visibility == "none":
            expected_ids = set()
        else:
            expected_ids = {str(own_prompt.id)}
        assert visible_ids == expected_ids

    @pytest.mark.parametrize(("role_name", "project_relation", "expected_status"), _SUBMIT_PERMISSION_CASES)
    async def test_submit_role_and_project_permission(
        self,
        role_name: str,
        project_relation: str,
        expected_status: int,
    ) -> None:
        """Submit permission is checked before the empty-responder fallback."""
        prompt = await self.setup.create_role_prompt(role_name, project_relation)

        with patch("syntara.forms.clients.workflow_client.WorkflowApiClient") as client_class:
            client = client_class.return_value.__aenter__.return_value
            client.send_form_signal = AsyncMock()
            response = await self.setup.client.post(
                f"{FORM_PROMPTS_URL}/{prompt.id}/submit",
                json={"response_data": {"reason": "authorized by role"}},
            )

        assert response.status_code == expected_status
        if expected_status == 200:
            assert response.json()["status"] == "submitted"
            client.send_form_signal.assert_awaited_once()
        else:
            assert response.json()["code"] == "AUTHORIZATION_DENIED"
            client.send_form_signal.assert_not_awaited()

    @pytest.mark.parametrize("role_name", ["admin", "project-admin", "project-user"])
    @pytest.mark.parametrize("responder_mode", ["user", "group", "neither", "group_nonmember", "empty"])
    async def test_submit_responder_membership_for_roles_with_submit_permission(
        self,
        multiple_local_users: list[User],
        test_group: Group,
        role_name: str,
        responder_mode: str,
    ) -> None:
        """Direct responders and group members may submit; configured nonresponders may not."""
        await self.setup.assign_role(role_name)
        prompt = await self.setup.create_prompt()
        await self.setup.configure_responders(prompt, responder_mode, test_group, multiple_local_users)

        with patch("syntara.forms.clients.workflow_client.WorkflowApiClient") as client_class:
            client = client_class.return_value.__aenter__.return_value
            client.send_form_signal = AsyncMock()
            response = await self.setup.client.post(
                f"{FORM_PROMPTS_URL}/{prompt.id}/submit",
                json={"response_data": {"reason": "responder authorization"}},
            )

        if responder_mode in {"neither", "group_nonmember"}:
            assert response.status_code == 403
            assert response.json()["code"] == "FORM_PROMPT_NOT_AUTHORIZED"
            client.send_form_signal.assert_not_awaited()
        else:
            assert response.status_code == 200
            assert response.json()["status"] == "submitted"
            client.send_form_signal.assert_awaited_once()

    @pytest.mark.parametrize("role_name", ["auditor", "project-auditor"])
    @pytest.mark.parametrize("responder_mode", ["user", "group"])
    async def test_submit_responder_membership_does_not_grant_submit_permission(
        self,
        multiple_local_users: list[User],
        test_group: Group,
        role_name: str,
        responder_mode: str,
    ) -> None:
        """A responder assignment cannot replace the required submit policy."""
        await self.setup.assign_role(role_name)
        prompt = await self.setup.create_prompt()
        await self.setup.configure_responders(prompt, responder_mode, test_group, multiple_local_users)

        response = await self.setup.client.post(
            f"{FORM_PROMPTS_URL}/{prompt.id}/submit",
            json={"response_data": {"reason": "role denied"}},
        )

        assert response.status_code == 403
        assert response.json()["code"] == "AUTHORIZATION_DENIED"

    @pytest.mark.parametrize(
        "role_name", ["admin", "auditor", "project-admin", "project-user", "project-auditor", "user"]
    )
    async def test_batch_update_permission_is_admin_only(self, role_name: str) -> None:
        """The batch endpoint's form_prompt:create permission is currently admin-only."""
        await self.setup.assign_role(role_name)
        prompt = await self.setup.create_prompt()

        response = await self.setup.client.post(
            f"{FORM_PROMPTS_URL}/batch",
            json={"updates": [{"prompt_id": str(prompt.id), "status": "expired"}]},
        )

        if role_name == "admin":
            assert response.status_code == 200
            assert response.json()["total_success"] == 1
        else:
            assert response.status_code == 403
            assert response.json()["code"] == "AUTHORIZATION_DENIED"

    async def test_create_permission_denied_for_user_role(self) -> None:
        """The built-in user role cannot create form prompts."""
        await self.setup.assign_role("user")

        response = await self.setup.client.post(
            FORM_PROMPTS_URL,
            json={
                "execution_id": str(uuid4()),
                "project_id": str(self.setup.project_id),
                "prompt_node_id": "form-prompt-authz-test",
                "name": "Authorization test form",
                "temporal_activity_id": "form-activity",
                "form_definition": _FORM_DEFINITION,
            },
        )

        assert response.status_code == 403
        assert response.json()["code"] == "AUTHORIZATION_DENIED"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("responder_mode", ["user", "group"])
async def test_service_submit_raises_not_authorized_for_nonresponder(
    form_prompt_setup: _FormPromptAuthorizationSetup,
    multiple_local_users: list[User],
    test_group: Group,
    responder_mode: str,
) -> None:
    """FormPromptService raises its domain exception when neither responder rule matches."""
    prompt = await form_prompt_setup.create_prompt()
    configured_mode = "group_nonmember" if responder_mode == "group" else "neither"
    await form_prompt_setup.configure_responders(prompt, configured_mode, test_group, multiple_local_users)

    service = FormPromptService(session=form_prompt_setup.session, user=form_prompt_setup.user)
    with pytest.raises(FormPromptNotAuthorizedError) as exc_info:
        await service.submit(prompt.id, {})

    assert exc_info.value.form_prompt_id == prompt.id
    assert exc_info.value.user_id == form_prompt_setup.user.id
