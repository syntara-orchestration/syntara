"""Integration tests for responding to a form prompt."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth.dependencies import get_current_user
from syntara.authz.engine import AuthzRequest, AuthzResult
from syntara.authz.evaluator import AuthzEvaluator
from syntara.authz.models.project import Project
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.forms.models.api_models import FormPromptStatus
from syntara.forms.models.form_prompt import FormPrompt

FORM_PROMPTS_URL = "/api/v1/form_prompts"
_FORM_DEFINITION = {"fields": [{"value_name": "reason", "type": "text", "label": "Reason", "required": True}]}


async def _create_prompt(
    session: AsyncSession,
    project_id: UUID,
    *,
    status: FormPromptStatus = FormPromptStatus.PENDING,
    timeout_at: datetime | None = None,
    form_definition: dict[str, Any] | None = None,
) -> FormPrompt:
    """Persist a prompt with the requested status and deadline."""
    prompt = FormPrompt(
        project_id=project_id,
        execution_id=uuid4(),
        prompt_node_id=f"form-{uuid4().hex[:8]}",
        temporal_activity_id="form-activity",
        name="Test form",
        form_definition=form_definition or _FORM_DEFINITION,
        status=status,
        timeout_at=timeout_at,
        responded_by=None,
        responded_at=datetime.now(UTC) if status == FormPromptStatus.SUBMITTED else None,
    )
    session.add(prompt)
    await session.commit()
    await session.refresh(prompt)
    return prompt


def _controlled_authorizer(
    monkeypatch: pytest.MonkeyPatch,
    *,
    deny_action: str | None = None,
    allowed_projects: set[str] | None = None,
) -> None:
    """Mock prompt permissions for role and project scope route tests."""

    async def authorize(_db: AsyncSession, _evaluator: AuthzEvaluator, request: AuthzRequest) -> AuthzResult:
        allowed = True
        if request.resource_type == "form_prompt":
            allowed = request.action != deny_action
            if allowed_projects is not None:
                allowed = allowed and ("*" in allowed_projects or request.resource_project in allowed_projects)
        return AuthzResult(
            allowed=allowed,
            denied=not allowed,
            matched_policy="test-policy" if allowed else "",
            denial_reason="No matching test policy" if not allowed else "",
            denied_by="test-evaluator",
            effective_policies=[],
        )

    monkeypatch.setattr("syntara.authz.dependencies.authorize", authorize)


@pytest.mark.integration
@pytest.mark.asyncio
class TestFormPromptSubmitAPI:
    """Route-level tests for the response action."""

    async def test_submit_success_returns_200(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: UUID,
        test_user: User,
    ) -> None:
        prompt = await _create_prompt(test_db_session, test_project_id)
        submitted = {"reason": "Approved"}

        with patch("syntara.forms.clients.workflow_client.WorkflowApiClient") as client_class:
            client = client_class.return_value.__aenter__.return_value
            client.send_form_signal = AsyncMock()
            response = await auth_client.post(
                f"{FORM_PROMPTS_URL}/{prompt.id}/submit",
                json={"response_data": submitted},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "submitted"
        assert data["response_data"] == submitted
        assert data["responded_by"] == {"id": str(test_user.id), "name": test_user.display_name}
        assert data["responded_at"] is not None
        assert data["signal_delivery_error"] is None

    async def test_submit_persists_response(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: UUID,
    ) -> None:
        prompt = await _create_prompt(test_db_session, test_project_id)

        with patch("syntara.forms.clients.workflow_client.WorkflowApiClient") as client_class:
            client_class.return_value.__aenter__.return_value.send_form_signal = AsyncMock()
            response = await auth_client.post(
                f"{FORM_PROMPTS_URL}/{prompt.id}/submit",
                json={"response_data": {"reason": "saved"}},
            )

        assert response.status_code == 200
        reread = await auth_client.get(f"{FORM_PROMPTS_URL}/{prompt.id}")
        assert reread.status_code == 200
        assert reread.json()["status"] == "submitted"
        assert reread.json()["response_data"] == {"reason": "saved"}

    async def test_submit_sends_workflow_signal(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: UUID,
        test_user: User,
    ) -> None:
        prompt = await _create_prompt(test_db_session, test_project_id)
        submitted = {"reason": "signal me"}

        with patch("syntara.forms.clients.workflow_client.WorkflowApiClient") as client_class:
            client = client_class.return_value.__aenter__.return_value
            client.send_form_signal = AsyncMock()
            response = await auth_client.post(
                f"{FORM_PROMPTS_URL}/{prompt.id}/submit",
                json={"response_data": submitted},
            )

        assert response.status_code == 200
        client.send_form_signal.assert_awaited_once()
        call = client.send_form_signal.await_args.kwargs
        assert call["execution_id"] == prompt.execution_id
        assert call["form_prompt_id"] == prompt.prompt_node_id
        assert call["temporal_activity_id"] == prompt.temporal_activity_id
        assert call["form_response"]["outcome"] == "submitted"
        assert call["form_response"]["response_data"] == submitted
        assert call["form_response"]["responded_by"] == test_user.username
        assert call["form_response"]["prompt_id"] == str(prompt.id)
        assert "responded_at" in call["form_response"]

    async def test_submit_signal_failure_still_returns_submitted_prompt(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: UUID,
    ) -> None:
        prompt = await _create_prompt(test_db_session, test_project_id)

        with patch("syntara.forms.clients.workflow_client.WorkflowApiClient") as client_class:
            client = client_class.return_value.__aenter__.return_value
            client.send_form_signal = AsyncMock(side_effect=RuntimeError("signal unavailable"))
            response = await auth_client.post(
                f"{FORM_PROMPTS_URL}/{prompt.id}/submit",
                json={"response_data": {"reason": "stored"}},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "submitted"
        assert response.json()["signal_delivery_error"] == "Workflow signal delivery failed"
        refreshed = await test_db_session.get(FormPrompt, prompt.id)
        assert refreshed is not None
        assert refreshed.status == FormPromptStatus.SUBMITTED

    async def test_submit_pending_prompt_past_deadline_returns_409(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: UUID,
    ) -> None:
        prompt = await _create_prompt(
            test_db_session,
            test_project_id,
            status=FormPromptStatus.PENDING,
            timeout_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        assert prompt.status == FormPromptStatus.PENDING

        response = await auth_client.post(
            f"{FORM_PROMPTS_URL}/{prompt.id}/submit",
            json={"response_data": {"reason": "too late"}},
        )

        assert response.status_code == 409
        assert response.json()["code"] == "FORM_EXPIRED"
        await test_db_session.refresh(prompt)
        assert prompt.status == FormPromptStatus.PENDING

    @pytest.mark.parametrize(
        ("status", "expected_code"),
        [
            (FormPromptStatus.SUBMITTED, "FORM_ALREADY_RESPONDED"),
            (FormPromptStatus.EXPIRED, "FORM_EXPIRED"),
            (FormPromptStatus.CANCELLED, "FORM_CANCELLED"),
        ],
    )
    async def test_submit_to_terminal_prompt_returns_409(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: UUID,
        status: FormPromptStatus,
        expected_code: str,
    ) -> None:
        prompt = await _create_prompt(test_db_session, test_project_id, status=status)

        response = await auth_client.post(
            f"{FORM_PROMPTS_URL}/{prompt.id}/submit",
            json={"response_data": {"reason": "too late"}},
        )

        assert response.status_code == 409
        assert response.json()["code"] == expected_code

    async def test_submit_missing_required_field_returns_422_detail(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: UUID,
    ) -> None:
        prompt = await _create_prompt(test_db_session, test_project_id)

        response = await auth_client.post(f"{FORM_PROMPTS_URL}/{prompt.id}/submit", json={"response_data": {}})

        assert response.status_code == 422
        assert response.json()["detail"] == "Form validation failed: reason: This field is required"
        assert "errors" not in response.json()

    async def test_submit_wrong_field_type_returns_422(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: UUID,
    ) -> None:
        prompt = await _create_prompt(test_db_session, test_project_id)

        response = await auth_client.post(
            f"{FORM_PROMPTS_URL}/{prompt.id}/submit",
            json={"response_data": {"reason": 3}},
        )

        assert response.status_code == 422
        assert response.json()["detail"].startswith("Form validation failed: reason:")
        assert "errors" not in response.json()

    async def test_submit_invalid_option_returns_422(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: UUID,
    ) -> None:
        definition = {
            "fields": [
                {
                    "value_name": "decision",
                    "type": "dropdown",
                    "label": "Decision",
                    "required": True,
                    "options": {
                        "source": "static",
                        "values": [{"display_label": "Accept", "value": "accept"}],
                    },
                }
            ]
        }
        prompt = await _create_prompt(test_db_session, test_project_id, form_definition=definition)

        response = await auth_client.post(
            f"{FORM_PROMPTS_URL}/{prompt.id}/submit",
            json={"response_data": {"decision": "reject"}},
        )

        assert response.status_code == 422
        assert response.json()["detail"].startswith("Form validation failed: decision:")
        assert "errors" not in response.json()

    async def test_submit_not_found_returns_404(self, auth_client: AsyncClient) -> None:
        response = await auth_client.post(
            f"{FORM_PROMPTS_URL}/{uuid4()}/submit",
            json={"response_data": {"reason": "no prompt"}},
        )

        assert response.status_code == 404
        assert response.json()["code"] == "FORM_NOT_FOUND"

    async def test_submit_unauthenticated_returns_401(self, base_client: AsyncClient) -> None:
        response = await base_client.post(
            f"{FORM_PROMPTS_URL}/{uuid4()}/submit",
            json={"response_data": {"reason": "unauthenticated"}},
        )

        assert response.status_code == 401

    async def test_submit_without_submit_permission_returns_403(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: UUID,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prompt = await _create_prompt(test_db_session, test_project_id)
        _controlled_authorizer(monkeypatch, deny_action="submit")

        response = await auth_client.post(
            f"{FORM_PROMPTS_URL}/{prompt.id}/submit",
            json={"response_data": {"reason": "denied"}},
        )

        assert response.status_code == 403

    async def test_submit_forbidden_other_project(
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
        _controlled_authorizer(monkeypatch, allowed_projects={allowed_project.name})

        response = await auth_client.post(
            f"{FORM_PROMPTS_URL}/{prompt.id}/submit",
            json={"response_data": {"reason": "denied"}},
        )

        assert response.status_code == 403

    async def test_submit_concurrent_submissions_exactly_one_wins(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        test_project_id: UUID,
        test_user: User,
        session_app: FastAPI,
    ) -> None:
        prompt = await _create_prompt(test_db_session, test_project_id)

        async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
            async with test_db_session_factory() as session:
                yield session

        async def override_get_current_user() -> User:
            return test_user

        session_app.dependency_overrides[get_db] = override_get_db
        session_app.dependency_overrides[get_current_user] = override_get_current_user
        client = AsyncClient(transport=ASGITransport(app=session_app), base_url="http://test")
        try:
            with patch("syntara.forms.clients.workflow_client.WorkflowApiClient") as client_class:
                mock_client = client_class.return_value.__aenter__.return_value
                mock_client.send_form_signal = AsyncMock()
                responses = await asyncio.gather(
                    client.post(
                        f"{FORM_PROMPTS_URL}/{prompt.id}/submit",
                        json={"response_data": {"reason": "first"}},
                    ),
                    client.post(
                        f"{FORM_PROMPTS_URL}/{prompt.id}/submit",
                        json={"response_data": {"reason": "second"}},
                    ),
                )
        finally:
            await client.aclose()

        assert sorted(response.status_code for response in responses) == [200, 409]
