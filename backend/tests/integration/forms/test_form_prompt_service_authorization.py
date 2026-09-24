"""Integration tests for form prompt permissions and responder authorization."""

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
    ("admin", "foreign", 200),
    ("auditor", "same", 200),
    ("auditor", "foreign", 200),
    ("project-admin", "same", 200),
    ("project-admin", "foreign", 403),
    ("project-user", "same", 200),
    ("project-user", "foreign", 403),
    ("project-auditor", "same", 200),
    ("project-auditor", "foreign", 403),
]
_SUBMIT_PERMISSION_CASES = [
    ("admin", "same", 200),
    ("admin", "foreign", 200),
    ("auditor", "same", 403),
    ("project-admin", "same", 200),
    ("project-admin", "foreign", 403),
    ("project-user", "same", 200),
    ("project-user", "foreign", 403),
    ("project-auditor", "same", 403),
]


class _RealPolicyEvaluator:
    """Use the production Rego policy for route authorization in these tests."""

    def evaluate(self, authz_input: dict[str, Any]) -> dict[str, Any]:
        """Evaluate one authorization request with the production Rego policy."""
        return evaluate_policy_input(authz_input)


def _use_real_policy_evaluator(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make API authorization use the repository's Rego policy in this integration test."""
    clear_authz_cache()
    evaluator = _RealPolicyEvaluator()
    monkeypatch.setattr("syntara.authz.dependencies.get_authz_evaluator", lambda _request: evaluator)


async def _assign_role(
    session: AsyncSession,
    user: User,
    role_name: str,
    project_id: UUID | None = None,
) -> None:
    """Assign a built-in role directly to a user, optionally within a project."""
    session.add(RoleAssignment(principal_id=user.id, role_name=role_name, project_id=project_id))
    await session.commit()


async def _create_project(session: AsyncSession, *, name_prefix: str = "form-prompt-authz") -> Project:
    """Create a project for cross-project access cases."""
    project = Project(name=f"{name_prefix}-{uuid4().hex[:8]}", description="Authorization test project")
    session.add(project)
    await session.commit()
    return project


async def _create_prompt(session: AsyncSession, project_id: UUID) -> FormPrompt:
    """Persist a pending prompt with a valid minimal response schema."""
    prompt = FormPrompt(
        project_id=project_id,
        execution_id=uuid4(),
        prompt_node_id=f"form-{uuid4().hex[:8]}",
        temporal_activity_id="form-activity",
        name="Test form",
        form_definition=_FORM_DEFINITION,
        status=FormPromptStatus.PENDING,
    )
    session.add(prompt)
    await session.commit()
    await session.refresh(prompt)
    return prompt


async def _configure_responders(
    session: AsyncSession,
    prompt: FormPrompt,
    current_user: User,
    mode: str,
    group: Group,
    other_users: list[User],
) -> None:
    """Configure the requested responder case and persist real membership rows."""
    if mode == "user":
        session.add(FormPromptResponderUser(form_prompt_id=prompt.id, user_id=current_user.id))
    elif mode == "group":
        session.add(FormPromptResponderGroup(form_prompt_id=prompt.id, group_id=group.id))
        await session.exec(insert(user_groups).values(user_id=current_user.id, group_id=group.id))
    elif mode == "group_nonmember":
        session.add(FormPromptResponderGroup(form_prompt_id=prompt.id, group_id=group.id))
    elif mode == "neither":
        session.add(FormPromptResponderUser(form_prompt_id=prompt.id, user_id=other_users[0].id))
    elif mode != "empty":
        msg = f"Unknown responder test mode: {mode}"
        raise ValueError(msg)
    await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(("role_name", "project_relation", "expected_status"), _GET_SINGLE_CASES)
async def test_get_single_prompt_role_scope(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id: UUID,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    role_name: str,
    project_relation: str,
    expected_status: int,
) -> None:
    """Single-prompt reads follow system-wide or assigned-project read policies."""
    _use_real_policy_evaluator(monkeypatch)
    target_project_id = test_project_id
    if project_relation == "foreign":
        target_project_id = (await _create_project(test_db_session)).id
    await _assign_role(
        test_db_session,
        test_user,
        role_name,
        test_project_id if role_name in _PROJECT_ROLES else None,
    )
    prompt = await _create_prompt(test_db_session, target_project_id)

    response = await auth_client.get(f"{FORM_PROMPTS_URL}/{prompt.id}")

    assert response.status_code == expected_status
    if expected_status == 200:
        assert response.json()["id"] == str(prompt.id)
    else:
        assert response.json()["code"] == "AUTHORIZATION_DENIED"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role_name", "expected_visibility"),
    [
        ("admin", "all"),
        ("auditor", "all"),
        ("project-admin", "assigned"),
        ("project-user", "assigned"),
        ("project-auditor", "assigned"),
    ],
)
async def test_list_prompts_role_visibility(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id: UUID,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    role_name: str,
    expected_visibility: str,
) -> None:
    """List reads expose all prompts to system readers and assigned-project prompts to project readers."""
    _use_real_policy_evaluator(monkeypatch)
    foreign_project = await _create_project(test_db_session)
    await _assign_role(
        test_db_session,
        test_user,
        role_name,
        test_project_id if role_name in _PROJECT_ROLES else None,
    )
    own_prompt = await _create_prompt(test_db_session, test_project_id)
    foreign_prompt = await _create_prompt(test_db_session, foreign_project.id)

    response = await auth_client.get(FORM_PROMPTS_URL)

    assert response.status_code == 200
    visible_ids = {resource["id"] for resource in response.json()["resources"]}
    expected_ids = {str(own_prompt.id)}
    if expected_visibility == "all":
        expected_ids.add(str(foreign_prompt.id))
    assert visible_ids == expected_ids


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(("role_name", "project_relation", "expected_status"), _SUBMIT_PERMISSION_CASES)
async def test_submit_role_and_project_permission(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id: UUID,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    role_name: str,
    project_relation: str,
    expected_status: int,
) -> None:
    """Submit permission is checked before the empty-responder fallback."""
    _use_real_policy_evaluator(monkeypatch)
    target_project_id = test_project_id
    if project_relation == "foreign":
        target_project_id = (await _create_project(test_db_session)).id
    await _assign_role(
        test_db_session,
        test_user,
        role_name,
        test_project_id if role_name in _PROJECT_ROLES else None,
    )
    prompt = await _create_prompt(test_db_session, target_project_id)

    with patch("syntara.forms.clients.workflow_client.WorkflowApiClient") as client_class:
        client = client_class.return_value.__aenter__.return_value
        client.send_form_signal = AsyncMock()
        response = await auth_client.post(
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


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("role_name", ["admin", "project-admin", "project-user"])
@pytest.mark.parametrize("responder_mode", ["user", "group", "neither", "group_nonmember", "empty"])
async def test_submit_responder_membership_for_roles_with_submit_permission(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id: UUID,
    test_user: User,
    multiple_local_users: list[User],
    test_group: Group,
    monkeypatch: pytest.MonkeyPatch,
    role_name: str,
    responder_mode: str,
) -> None:
    """Direct responders and group members may submit; configured nonresponders may not."""
    _use_real_policy_evaluator(monkeypatch)
    await _assign_role(
        test_db_session,
        test_user,
        role_name,
        test_project_id if role_name in _PROJECT_ROLES else None,
    )
    prompt = await _create_prompt(test_db_session, test_project_id)
    await _configure_responders(test_db_session, prompt, test_user, responder_mode, test_group, multiple_local_users)

    with patch("syntara.forms.clients.workflow_client.WorkflowApiClient") as client_class:
        client = client_class.return_value.__aenter__.return_value
        client.send_form_signal = AsyncMock()
        response = await auth_client.post(
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


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("role_name", ["auditor", "project-auditor"])
@pytest.mark.parametrize("responder_mode", ["user", "group"])
async def test_submit_responder_membership_does_not_grant_submit_permission(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id: UUID,
    test_user: User,
    multiple_local_users: list[User],
    test_group: Group,
    monkeypatch: pytest.MonkeyPatch,
    role_name: str,
    responder_mode: str,
) -> None:
    """A responder assignment cannot replace the required submit policy."""
    _use_real_policy_evaluator(monkeypatch)
    await _assign_role(
        test_db_session,
        test_user,
        role_name,
        test_project_id if role_name in _PROJECT_ROLES else None,
    )
    prompt = await _create_prompt(test_db_session, test_project_id)
    await _configure_responders(test_db_session, prompt, test_user, responder_mode, test_group, multiple_local_users)

    response = await auth_client.post(
        f"{FORM_PROMPTS_URL}/{prompt.id}/submit",
        json={"response_data": {"reason": "role denied"}},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "AUTHORIZATION_DENIED"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("role_name", ["admin", "auditor", "project-admin", "project-user", "project-auditor"])
async def test_batch_update_permission_is_admin_only(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id: UUID,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    role_name: str,
) -> None:
    """The batch endpoint's form_prompt:create permission is currently admin-only."""
    _use_real_policy_evaluator(monkeypatch)
    await _assign_role(
        test_db_session,
        test_user,
        role_name,
        test_project_id if role_name in _PROJECT_ROLES else None,
    )
    prompt = await _create_prompt(test_db_session, test_project_id)

    response = await auth_client.post(
        f"{FORM_PROMPTS_URL}/batch",
        json={"updates": [{"prompt_id": str(prompt.id), "status": "expired"}]},
    )

    if role_name == "admin":
        assert response.status_code == 200
        assert response.json()["total_success"] == 1
    else:
        assert response.status_code == 403
        assert response.json()["code"] == "AUTHORIZATION_DENIED"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("responder_mode", ["user", "group"])
async def test_service_submit_raises_not_authorized_for_nonresponder(
    test_db_session: AsyncSession,
    test_project_id: UUID,
    test_user: User,
    multiple_local_users: list[User],
    test_group: Group,
    responder_mode: str,
) -> None:
    """FormPromptService raises its domain exception when neither responder rule matches."""
    prompt = await _create_prompt(test_db_session, test_project_id)
    if responder_mode == "group":
        await _configure_responders(
            test_db_session,
            prompt,
            test_user,
            "group_nonmember",
            test_group,
            multiple_local_users,
        )
    else:
        await _configure_responders(test_db_session, prompt, test_user, "neither", test_group, multiple_local_users)

    service = FormPromptService(session=test_db_session, user=test_user)
    with pytest.raises(FormPromptNotAuthorizedError) as exc_info:
        await service.submit(prompt.id, {})

    assert exc_info.value.form_prompt_id == prompt.id
    assert exc_info.value.user_id == test_user.id
