"""Integration-scoped visibility tests for LLM model endpoints.

Verifies that models inherit visibility from their parent integration:
  - Admin can list models from any integration
  - User (no project role) can list models from global integrations only
  - Project-user can list models from assigned project integrations
  - Authenticated user with no roles gets 403
"""

from collections.abc import Awaitable, Callable
from uuid import uuid4

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import Project
from syntara.core.models import User
from syntara.integrations.models.integration import (
    Integration,
    IntegrationProjectAssignment,
    IntegrationScope,
    IntegrationType,
)
from syntara.integrations.models.integration_configuration import LLMProviderConfiguration
from syntara.integrations.models.llm_model import LLMModel
from tests.integration.api.conftest import (
    make_admin,
    make_project_user,
    make_user_role,
)


async def _create_llm_integration_with_model(
    session: AsyncSession,
    user: User,
    *,
    scope: IntegrationScope = IntegrationScope.GLOBAL,
) -> tuple[Integration, LLMModel]:
    """Create an LLM provider integration with one model and return both."""
    suffix = uuid4().hex[:8]
    integration = Integration(
        name=f"vis-llm-{suffix}",
        integration_type=IntegrationType.LLM_PROVIDER,
        scope=scope,
        configuration=LLMProviderConfiguration(
            integration_type="llm_provider",
            base_url="https://api.example.com",
            provider_hint="custom",
        ),
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(integration)
    await session.flush()

    model = LLMModel(
        integration_id=integration.id,
        model_id=f"vis-model-{suffix}",
        name=f"Vis Model {suffix}",
        created_by=user.id,
    )
    session.add(model)
    await session.commit()
    return integration, model


def _models_url(integration_id: str) -> str:
    return f"/api/v1/integrations/{integration_id}/models"


class TestNoRoleModelAccess:
    """Authenticated user with no roles gets 403 on model endpoints."""

    async def test_no_role_cannot_list_models(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        integration, _ = await _create_llm_integration_with_model(test_db_session, test_user)

        user = await user_factory(username=f"mv-nr-{uuid4().hex[:6]}", email=f"mv-nr-{uuid4().hex[:6]}@test.com")
        auth_as(user)

        resp = await auth_client.get(_models_url(str(integration.id)))
        assert resp.status_code == 403

    async def test_no_role_cannot_get_model(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        integration, model = await _create_llm_integration_with_model(test_db_session, test_user)

        user = await user_factory(username=f"mv-nrg-{uuid4().hex[:6]}", email=f"mv-nrg-{uuid4().hex[:6]}@test.com")
        auth_as(user)

        resp = await auth_client.get(f"{_models_url(str(integration.id))}/{model.id}")
        assert resp.status_code == 403


class TestAdminModelVisibility:
    """Admin can access models from any integration."""

    async def test_admin_can_list_models_from_any_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        integration, model = await _create_llm_integration_with_model(
            test_db_session, test_user, scope=IntegrationScope.PROJECT
        )

        admin = await user_factory(username=f"mv-adm-{uuid4().hex[:6]}", email=f"mv-adm-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.get(_models_url(str(integration.id)))
        assert resp.status_code == 200
        model_ids = {r["id"] for r in resp.json()["resources"]}
        assert str(model.id) in model_ids


class TestUserModelVisibility:
    """User role (no project assignments) can only access models from global integrations."""

    async def test_user_can_list_models_from_global_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        integration, model = await _create_llm_integration_with_model(test_db_session, test_user)

        user = await user_factory(username=f"mv-ug-{uuid4().hex[:6]}", email=f"mv-ug-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.get(_models_url(str(integration.id)))
        assert resp.status_code == 200
        model_ids = {r["id"] for r in resp.json()["resources"]}
        assert str(model.id) in model_ids

    async def test_user_cannot_list_models_from_project_scoped_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        integration, _ = await _create_llm_integration_with_model(
            test_db_session, test_user, scope=IntegrationScope.PROJECT
        )

        user = await user_factory(username=f"mv-up-{uuid4().hex[:6]}", email=f"mv-up-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.get(_models_url(str(integration.id)))
        assert resp.status_code == 404


class TestProjectUserModelVisibility:
    """Project-user sees models from assigned integrations only."""

    async def test_project_user_can_list_models_from_assigned_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        project = Project(name=f"mv-proj-{uuid4().hex[:8]}")
        test_db_session.add(project)
        await test_db_session.commit()
        await test_db_session.refresh(project)

        integration, model = await _create_llm_integration_with_model(
            test_db_session, test_user, scope=IntegrationScope.PROJECT
        )
        test_db_session.add(IntegrationProjectAssignment(integration_id=integration.id, project_id=project.id))
        await test_db_session.commit()

        user = await user_factory(username=f"mv-pua-{uuid4().hex[:6]}", email=f"mv-pua-{uuid4().hex[:6]}@test.com")
        await make_project_user(test_db_session, user, project)
        auth_as(user)

        resp = await auth_client.get(_models_url(str(integration.id)))
        assert resp.status_code == 200
        model_ids = {r["id"] for r in resp.json()["resources"]}
        assert str(model.id) in model_ids

    async def test_project_user_cannot_list_models_from_unassigned_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        project_a = Project(name=f"mv-pa-{uuid4().hex[:8]}")
        project_b = Project(name=f"mv-pb-{uuid4().hex[:8]}")
        test_db_session.add(project_a)
        test_db_session.add(project_b)
        await test_db_session.commit()
        await test_db_session.refresh(project_a)
        await test_db_session.refresh(project_b)

        integration, _ = await _create_llm_integration_with_model(
            test_db_session, test_user, scope=IntegrationScope.PROJECT
        )
        test_db_session.add(IntegrationProjectAssignment(integration_id=integration.id, project_id=project_b.id))
        await test_db_session.commit()

        user = await user_factory(username=f"mv-pun-{uuid4().hex[:6]}", email=f"mv-pun-{uuid4().hex[:6]}@test.com")
        await make_project_user(test_db_session, user, project_a)
        auth_as(user)

        resp = await auth_client.get(_models_url(str(integration.id)))
        assert resp.status_code == 404
