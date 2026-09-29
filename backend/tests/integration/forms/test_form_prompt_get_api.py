"""Integration tests for fetching one form prompt."""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.engine import AuthzRequest, AuthzResult
from syntara.authz.evaluator import AuthzEvaluator
from syntara.authz.models.project import Project
from syntara.core.models import Group, User
from syntara.forms.models.form_prompt import FormPrompt
from syntara.forms.models.form_prompt_responders import FormPromptResponderGroup, FormPromptResponderUser

FORM_PROMPTS_URL = "/api/v1/form_prompts"
_FORM_DEFINITION = {"fields": [{"value_name": "reason", "type": "text", "label": "Reason", "required": True}]}


async def _create_prompt(
    session: AsyncSession,
    project_id: UUID,
    *,
    name: str = "Test form",
) -> FormPrompt:
    """Persist a form prompt for endpoint tests."""
    prompt = FormPrompt(
        project_id=project_id,
        execution_id=uuid4(),
        prompt_node_id=f"form-{uuid4().hex[:8]}",
        temporal_activity_id="form-activity",
        name=name,
        form_definition=_FORM_DEFINITION,
    )
    session.add(prompt)
    await session.commit()
    await session.refresh(prompt)
    return prompt


def _controlled_authorizer(monkeypatch: pytest.MonkeyPatch, allowed_projects: set[str]) -> None:
    """Authorize prompt operations only for the given project names."""

    async def authorize(_db: AsyncSession, _evaluator: AuthzEvaluator, request: AuthzRequest) -> AuthzResult:
        allowed = (
            request.resource_type != "form_prompt"
            or "*" in allowed_projects
            or request.resource_project in allowed_projects
        )
        return AuthzResult(
            allowed=allowed,
            denied=not allowed,
            matched_policy="test-project-policy" if allowed else "",
            denial_reason="" if allowed else "Project is not in the test allow-list",
            denied_by="test-evaluator",
            effective_policies=[],
        )

    monkeypatch.setattr("syntara.authz.dependencies.authorize", authorize)


@pytest.mark.integration
@pytest.mark.asyncio
class TestFormPromptGetAPI:
    """Route-level tests for the GET detail endpoint."""

    async def test_get_form_prompt_returns_200(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_project_id: UUID
    ) -> None:
        prompt = await _create_prompt(test_db_session, test_project_id)

        response = await auth_client.get(f"{FORM_PROMPTS_URL}/{prompt.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(prompt.id)
        assert data["name"] == prompt.name
        assert data["status"] == "pending"
        field = data["form_definition"]["fields"][0]
        assert {key: field[key] for key in ("value_name", "type", "label", "required")} == {
            "value_name": "reason",
            "type": "text",
            "label": "Reason",
            "required": True,
        }
        assert data["responder_users"] == []
        assert data["responder_groups"] == []

    async def test_get_form_prompt_not_found(self, auth_client: AsyncClient) -> None:
        response = await auth_client.get(f"{FORM_PROMPTS_URL}/{uuid4()}")

        assert response.status_code == 404
        assert response.json()["code"] == "FORM_NOT_FOUND"

    async def test_get_form_prompt_invalid_uuid(self, auth_client: AsyncClient) -> None:
        response = await auth_client.get(f"{FORM_PROMPTS_URL}/not-a-uuid")

        assert response.status_code == 422

    async def test_get_form_prompt_unauthenticated(self, base_client: AsyncClient) -> None:
        response = await base_client.get(f"{FORM_PROMPTS_URL}/{uuid4()}")

        assert response.status_code == 401

    async def test_get_form_prompt_forbidden_other_project(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: UUID,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        allowed_project = await test_db_session.get(Project, test_project_id)
        assert allowed_project is not None
        foreign_project = Project(name=f"foreign-{uuid4().hex[:8]}", description="Foreign project")
        test_db_session.add(foreign_project)
        await test_db_session.commit()
        prompt = await _create_prompt(test_db_session, foreign_project.id)
        _controlled_authorizer(monkeypatch, {allowed_project.name})

        response = await auth_client.get(f"{FORM_PROMPTS_URL}/{prompt.id}")

        assert response.status_code == 403

    async def test_get_form_prompt_includes_responder_configuration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: UUID,
        test_user: User,
        test_group: Group,
    ) -> None:
        prompt = await _create_prompt(test_db_session, test_project_id)
        test_db_session.add_all(
            [
                FormPromptResponderUser(form_prompt_id=prompt.id, user_id=test_user.id),
                FormPromptResponderGroup(form_prompt_id=prompt.id, group_id=test_group.id),
            ]
        )
        await test_db_session.commit()

        response = await auth_client.get(f"{FORM_PROMPTS_URL}/{prompt.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["responder_users"] == [{"id": str(test_user.id), "username": test_user.username}]
        assert data["responder_groups"] == [{"id": str(test_group.id), "name": test_group.name}]
        assert data["signal_delivery_error"] is None

    async def test_get_form_prompt_with_read_permission(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: UUID,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prompt = await _create_prompt(test_db_session, test_project_id)
        _controlled_authorizer(monkeypatch, {"*"})

        response = await auth_client.get(f"{FORM_PROMPTS_URL}/{prompt.id}")

        assert response.status_code == 200
