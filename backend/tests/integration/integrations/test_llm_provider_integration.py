"""Integration tests for LLM provider validate, refresh, and model sync.

Tests exercise the full HTTP → service → database stack with mocked
provider HTTP responses. Verifies that integration status, timestamps,
and model records are persisted correctly for each outcome.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.integrations.adapters.protocol import (
    DiscoveredLLMModel,
    DiscoverResult,
    HealthCheckErrorType,
    ValidateResult,
)
from syntara.integrations.models.integration import (
    IntegrationCreate,
    IntegrationRefreshStatus,
    IntegrationStatus,
    IntegrationType,
)
from syntara.integrations.models.llm_model import LLMModel
from syntara.integrations.services.integration_service import IntegrationService

BASE_URL = "/api/v1/integrations"

LLM_VALIDATE_PATCH = "syntara.integrations.adapters.llm_provider.LLMProviderAdapter.validate"
LLM_DISCOVER_PATCH = "syntara.integrations.adapters.llm_provider.LLMProviderAdapter.discover"


async def _create_llm_integration(
    session: AsyncSession,
    user: User,
    name_prefix: str,
) -> str:
    """Create an llm_provider integration with a minimal fake credential attached."""
    from sqlmodel import select as sql_select

    from syntara.authz.models import Project
    from syntara.core.services.secret_service import create_secret_service

    project = Project(name=f"{name_prefix}-proj-{uuid4().hex[:8]}")
    session.add(project)
    await session.flush()

    cred_type = (
        await session.exec(sql_select(CredentialType).where(CredentialType.name == "LLM Provider"))
    ).one_or_none()
    if not cred_type:
        cred_type = CredentialType(
            name="LLM Provider",
            description="LLM API key",
            inputs={
                "fields": [{"id": "api_key", "type": "string", "secret": True, "label": "API Key"}],
                "required": ["api_key"],
            },
            injectors={"extra_vars": {"llm_api_key": "{{api_key}}"}},
            managed=True,
        )
        session.add(cred_type)
        await session.flush()

    secret_service = create_secret_service(session)
    secret_id = await secret_service.create_secret({"api_key": "sk-test-key"})

    credential = Credential(
        name=f"{name_prefix}-cred-{uuid4().hex[:8]}",
        credential_type_id=cred_type.id,
        secret_id=secret_id,
        enabled=True,
        project_id=project.id,
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(credential)
    await session.flush()

    service = IntegrationService(session, user)
    created = await service.create_integration(
        IntegrationCreate(
            name=f"{name_prefix}-{uuid4().hex[:8]}",
            integration_type=IntegrationType.LLM_PROVIDER,
            configuration={
                "integration_type": "llm_provider",
                "base_url": "https://api.openai.com",
                "provider_hint": "openai",
            },
            management_credential_id=credential.id,
        )
    )
    await session.commit()
    return str(created.id)


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLLMProviderValidateIntegration:
    """Integration tests for POST /integrations/{id}/validate with LLM providers."""

    async def test_validate_success_updates_status_to_available(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Successful validate sets validation_status=AVAILABLE."""
        integration_id = await _create_llm_integration(test_db_session, test_user, "llm-val-ok")
        result = ValidateResult(success=True, checked_at=datetime.now(UTC))

        with patch(LLM_VALIDATE_PATCH, new=AsyncMock(return_value=result)):
            response = await auth_client.post(f"{BASE_URL}/{integration_id}/validate")

        assert response.status_code == 200
        assert response.json()["success"] is True

        get_resp = await auth_client.get(f"{BASE_URL}/{integration_id}")
        assert get_resp.json()["validation_status"] == IntegrationStatus.AVAILABLE.value

    async def test_validate_failure_updates_status_to_error(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Failed validate sets validation_status=ERROR and persists error message."""
        integration_id = await _create_llm_integration(test_db_session, test_user, "llm-val-err")
        result = ValidateResult(
            success=False,
            checked_at=datetime.now(UTC),
            error="Authentication failed: HTTP 401",
            error_type=HealthCheckErrorType.AUTH_FAILURE,
        )

        with patch(LLM_VALIDATE_PATCH, new=AsyncMock(return_value=result)):
            response = await auth_client.post(f"{BASE_URL}/{integration_id}/validate")

        assert response.status_code == 200
        assert response.json()["success"] is False

        get_resp = await auth_client.get(f"{BASE_URL}/{integration_id}")
        data = get_resp.json()
        assert data["validation_status"] == IntegrationStatus.ERROR.value
        assert "401" in (data.get("validation_error") or "")

    async def test_validate_sets_last_validated_at(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """last_validated_at is populated after validate."""
        integration_id = await _create_llm_integration(test_db_session, test_user, "llm-val-ts")
        result = ValidateResult(success=True, checked_at=datetime.now(UTC))

        with patch(LLM_VALIDATE_PATCH, new=AsyncMock(return_value=result)):
            await auth_client.post(f"{BASE_URL}/{integration_id}/validate")

        get_resp = await auth_client.get(f"{BASE_URL}/{integration_id}")
        assert get_resp.json().get("last_validated_at") is not None

    async def test_validate_does_not_sync_models(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Validate does NOT create LLMModel records."""
        integration_id = await _create_llm_integration(test_db_session, test_user, "llm-val-nosync")
        result = ValidateResult(success=True, checked_at=datetime.now(UTC))

        with patch(LLM_VALIDATE_PATCH, new=AsyncMock(return_value=result)):
            await auth_client.post(f"{BASE_URL}/{integration_id}/validate")

        models = (
            await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == UUID(integration_id)))
        ).all()
        assert len(models) == 0


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLLMProviderRefreshIntegration:
    """Integration tests for POST /integrations/{id}/refresh with LLM providers."""

    async def test_refresh_success_creates_models(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Successful refresh creates LLMModel records and returns counts."""
        integration_id = await _create_llm_integration(test_db_session, test_user, "llm-ref-ok")
        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[
                DiscoveredLLMModel(id="gpt-4o", name="GPT-4o"),
                DiscoveredLLMModel(id="gpt-4o-mini", name="GPT-4o Mini"),
            ],
        )

        with patch(LLM_DISCOVER_PATCH, new=AsyncMock(return_value=discover_result)):
            response = await auth_client.post(f"{BASE_URL}/{integration_id}/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["synced_count"] == 2
        assert data["updated_count"] == 0

        models = (
            await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == UUID(integration_id)))
        ).all()
        assert len(models) == 2
        assert {m.model_id for m in models} == {"gpt-4o", "gpt-4o-mini"}

    async def test_refresh_sets_status_available(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Successful refresh sets refresh_status=AVAILABLE and last_refreshed_at."""
        integration_id = await _create_llm_integration(test_db_session, test_user, "llm-ref-status")
        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[],
        )

        with patch(LLM_DISCOVER_PATCH, new=AsyncMock(return_value=discover_result)):
            await auth_client.post(f"{BASE_URL}/{integration_id}/refresh")

        get_resp = await auth_client.get(f"{BASE_URL}/{integration_id}")
        data = get_resp.json()
        assert data["refresh_status"] == IntegrationRefreshStatus.AVAILABLE.value
        assert data["last_refreshed_at"] is not None

    async def test_refresh_failure_sets_error_status(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Failed discover sets refresh_status=ERROR and persists error message."""
        integration_id = await _create_llm_integration(test_db_session, test_user, "llm-ref-err")
        discover_result = DiscoverResult(
            success=False,
            checked_at=datetime.now(UTC),
            error="Connection timed out after 10s",
            error_type=HealthCheckErrorType.TIMEOUT,
        )

        with patch(LLM_DISCOVER_PATCH, new=AsyncMock(return_value=discover_result)):
            response = await auth_client.post(f"{BASE_URL}/{integration_id}/refresh")

        assert response.status_code == 200
        assert response.json()["synced_count"] == 0

        get_resp = await auth_client.get(f"{BASE_URL}/{integration_id}")
        data = get_resp.json()
        assert data["refresh_status"] == IntegrationRefreshStatus.ERROR.value
        assert "timed out" in (data.get("refresh_error") or "")

    async def test_refresh_keeps_missing_models_enabled(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Models no longer returned by the provider are kept with enabled unchanged."""
        integration_id = await _create_llm_integration(test_db_session, test_user, "llm-ref-del")

        # First refresh: create two models
        first_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[
                DiscoveredLLMModel(id="model-a", name="A"),
                DiscoveredLLMModel(id="model-b", name="B"),
            ],
        )
        with patch(LLM_DISCOVER_PATCH, new=AsyncMock(return_value=first_result)):
            await auth_client.post(f"{BASE_URL}/{integration_id}/refresh")

        # Second refresh: only model-a returned
        second_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[DiscoveredLLMModel(id="model-a", name="A")],
        )
        with patch(LLM_DISCOVER_PATCH, new=AsyncMock(return_value=second_result)):
            response = await auth_client.post(f"{BASE_URL}/{integration_id}/refresh")

        assert response.json()["missing_count"] == 1

        models = (
            await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == UUID(integration_id)))
        ).all()
        by_id = {m.model_id: m for m in models}
        assert set(by_id) == {"model-a", "model-b"}  # both rows preserved
        assert by_id["model-a"].enabled is True
        assert by_id["model-b"].enabled is True  # enabled is admin-controlled, not changed by discovery

    async def test_refresh_auth_failure_persists_error_type(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Auth failure (401/403) is persisted as refresh error."""
        integration_id = await _create_llm_integration(test_db_session, test_user, "llm-ref-auth")
        discover_result = DiscoverResult(
            success=False,
            checked_at=datetime.now(UTC),
            error="Authentication failed: HTTP 401",
            error_type=HealthCheckErrorType.AUTH_FAILURE,
        )

        with patch(LLM_DISCOVER_PATCH, new=AsyncMock(return_value=discover_result)):
            await auth_client.post(f"{BASE_URL}/{integration_id}/refresh")

        get_resp = await auth_client.get(f"{BASE_URL}/{integration_id}")
        data = get_resp.json()
        assert data["refresh_status"] == IntegrationRefreshStatus.ERROR.value
        assert "401" in (data.get("refresh_error") or "")


# ---------------------------------------------------------------------------
# Credential resolution failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLLMProviderCredentialResolution:
    """Integration tests for credential resolution failures during validate/refresh."""

    async def test_validate_with_deleted_credential(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Integration whose credential was deleted after creation fails on validate."""
        integration_id = await _create_llm_integration(test_db_session, test_user, "llm-cred-del")

        # Delete the credential out from under the integration
        from syntara.integrations.models.integration import Integration

        integration = (
            await test_db_session.exec(select(Integration).where(Integration.id == UUID(integration_id)))
        ).one()
        cred_id = integration.management_credential_id
        credential = await test_db_session.get(Credential, cred_id)
        if credential:
            await test_db_session.delete(credential)
            await test_db_session.commit()

        response = await auth_client.post(f"{BASE_URL}/{integration_id}/validate")
        assert response.status_code in (404, 422, 500)

    async def test_refresh_with_deleted_credential(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Integration whose credential was deleted after creation fails on refresh."""
        integration_id = await _create_llm_integration(test_db_session, test_user, "llm-ref-cred-del")

        from syntara.integrations.models.integration import Integration

        integration = (
            await test_db_session.exec(select(Integration).where(Integration.id == UUID(integration_id)))
        ).one()
        cred_id = integration.management_credential_id
        credential = await test_db_session.get(Credential, cred_id)
        if credential:
            await test_db_session.delete(credential)
            await test_db_session.commit()

        response = await auth_client.post(f"{BASE_URL}/{integration_id}/refresh")
        assert response.status_code in (404, 422, 500)

    async def test_create_without_credential_raises(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Creating an LLM integration without a credential raises IntegrationCredentialRequiredError."""
        from syntara.integrations.exceptions import IntegrationCredentialRequiredError

        service = IntegrationService(test_db_session, test_user)
        create_req = IntegrationCreate(
            name=f"llm-no-cred-{uuid4().hex[:8]}",
            integration_type=IntegrationType.LLM_PROVIDER,
            configuration={
                "integration_type": "llm_provider",
                "base_url": "https://api.openai.com",
                "provider_hint": "openai",
            },
        )
        with pytest.raises(IntegrationCredentialRequiredError):
            await service.create_integration(create_req)

    async def test_refresh_with_incomplete_credential(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        """Credential without llm_api_key in extra_vars results in auth failure from adapter."""
        from syntara.authz.models import Project
        from syntara.core.services.secret_service import create_secret_service

        project = Project(name=f"llm-incomplete-proj-{uuid4().hex[:8]}")
        test_db_session.add(project)
        await test_db_session.flush()

        cred_type = (
            await test_db_session.exec(select(CredentialType).where(CredentialType.name == "LLM Provider"))
        ).one_or_none()
        if not cred_type:
            cred_type = CredentialType(
                name="LLM Provider",
                description="LLM API key",
                inputs={
                    "fields": [{"id": "api_key", "type": "string", "secret": True, "label": "API Key"}],
                    "required": ["api_key"],
                },
                injectors={"extra_vars": {"llm_api_key": "{{api_key}}"}},
                managed=True,
            )
            test_db_session.add(cred_type)
            await test_db_session.flush()

        # Create credential with empty secret (no api_key value)
        secret_service = create_secret_service(test_db_session)
        secret_id = await secret_service.create_secret({"other_field": "not-an-api-key"})

        credential = Credential(
            name=f"llm-incomplete-cred-{uuid4().hex[:8]}",
            credential_type_id=cred_type.id,
            secret_id=secret_id,
            enabled=True,
            project_id=project.id,
            created_by=test_user.id,
            updated_by=test_user.id,
        )
        test_db_session.add(credential)
        await test_db_session.flush()

        service = IntegrationService(test_db_session, test_user)
        created = await service.create_integration(
            IntegrationCreate(
                name=f"llm-incomplete-{uuid4().hex[:8]}",
                integration_type=IntegrationType.LLM_PROVIDER,
                configuration={
                    "integration_type": "llm_provider",
                    "base_url": "https://api.openai.com",
                    "provider_hint": "openai",
                },
                management_credential_id=credential.id,
            )
        )
        await test_db_session.commit()

        # The adapter should receive empty llm_api_key and return auth failure
        response = await auth_client.post(f"{BASE_URL}/{created.id}/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Authentication configuration is incomplete" in (data.get("error") or "")


# ---------------------------------------------------------------------------
# Model CRUD endpoints
# ---------------------------------------------------------------------------


async def _create_llm_with_models(session: AsyncSession, user: User, models: list[DiscoveredLLMModel]) -> str:
    """Create an LLM integration and populate it with models via refresh."""
    integration_id = await _create_llm_integration(session, user, "llm-model-ep")

    discover_result = DiscoverResult(
        success=True,
        checked_at=datetime.now(UTC),
        discovered_models=models,
    )

    with patch(LLM_DISCOVER_PATCH, new=AsyncMock(return_value=discover_result)):
        from syntara.core.services.secret_service import create_secret_service

        service = IntegrationService(session, user, secret_service=create_secret_service(session))
        await service.refresh_resources(UUID(integration_id))
        await session.commit()

    return integration_id


@pytest.mark.asyncio
class TestModelEndpoints:
    """Integration tests for model CRUD endpoints under /integrations/{id}/models."""

    async def test_list_models_returns_200(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        integration_id = await _create_llm_with_models(
            test_db_session,
            test_user,
            [DiscoveredLLMModel(id="gpt-4o", name="GPT-4o")],
        )
        resp = await auth_client.get(f"{BASE_URL}/{integration_id}/models")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["resources"]) == 1
        assert data["resources"][0]["model_id"] == "gpt-4o"

    async def test_get_model_returns_200(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        integration_id = await _create_llm_with_models(
            test_db_session,
            test_user,
            [DiscoveredLLMModel(id="gpt-4o", name="GPT-4o")],
        )
        models = (
            await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == UUID(integration_id)))
        ).all()
        model_id = str(models[0].id)

        resp = await auth_client.get(f"{BASE_URL}/{integration_id}/models/{model_id}")
        assert resp.status_code == 200
        assert resp.json()["model_id"] == "gpt-4o"

    async def test_get_model_wrong_integration_returns_404(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        integration_id = await _create_llm_with_models(
            test_db_session,
            test_user,
            [DiscoveredLLMModel(id="gpt-4o", name="GPT-4o")],
        )
        models = (
            await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == UUID(integration_id)))
        ).all()
        model_id = str(models[0].id)

        # Use a random integration_id — model exists but doesn't belong to it
        resp = await auth_client.get(f"{BASE_URL}/{uuid4()}/models/{model_id}")
        assert resp.status_code == 404

    async def test_update_model_returns_200(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        integration_id = await _create_llm_with_models(
            test_db_session,
            test_user,
            [DiscoveredLLMModel(id="gpt-4o", name="GPT-4o")],
        )
        models = (
            await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == UUID(integration_id)))
        ).all()
        model_id = str(models[0].id)

        resp = await auth_client.patch(
            f"{BASE_URL}/{integration_id}/models/{model_id}",
            json={"enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    async def test_bulk_update_returns_counts(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        integration_id = await _create_llm_with_models(
            test_db_session,
            test_user,
            [
                DiscoveredLLMModel(id="gpt-4o", name="GPT-4o"),
                DiscoveredLLMModel(id="gpt-4o-mini", name="GPT-4o Mini"),
            ],
        )
        models = (
            await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == UUID(integration_id)))
        ).all()
        model_ids = [str(m.id) for m in models]

        resp = await auth_client.patch(
            f"{BASE_URL}/{integration_id}/models/bulk_update",
            json={"model_ids": model_ids, "enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 2

    async def test_get_nonexistent_model_returns_404(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        integration_id = await _create_llm_with_models(test_db_session, test_user, [])
        resp = await auth_client.get(f"{BASE_URL}/{integration_id}/models/{uuid4()}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Integration type guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestModelEndpointTypeMismatch:
    """Model endpoints reject non-LLM integrations with 422."""

    async def _create_mcp_integration(
        self,
        session: AsyncSession,
        user: User,
    ) -> str:
        from syntara.authz.models import Project

        project = Project(name=f"mcp-proj-{uuid4().hex[:8]}")
        session.add(project)
        await session.flush()

        service = IntegrationService(session, user)
        created = await service.create_integration(
            IntegrationCreate(
                name=f"mcp-{uuid4().hex[:8]}",
                integration_type=IntegrationType.MCP_SERVER,
                configuration={
                    "integration_type": "mcp_server",
                    "base_url": "https://mcp.example.com",
                },
            )
        )
        await session.commit()
        return str(created.id)

    async def test_list_models_on_mcp_integration_returns_422(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        mcp_id = await self._create_mcp_integration(test_db_session, test_user)
        resp = await auth_client.get(f"{BASE_URL}/{mcp_id}/models")
        assert resp.status_code == 422
        assert resp.json()["code"] == "INTEGRATION_TYPE_MISMATCH"

    async def test_get_model_on_mcp_integration_returns_422(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        mcp_id = await self._create_mcp_integration(test_db_session, test_user)
        resp = await auth_client.get(f"{BASE_URL}/{mcp_id}/models/{uuid4()}")
        assert resp.status_code == 422
        assert resp.json()["code"] == "INTEGRATION_TYPE_MISMATCH"

    async def test_bulk_update_on_mcp_integration_returns_422(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
    ) -> None:
        mcp_id = await self._create_mcp_integration(test_db_session, test_user)
        resp = await auth_client.patch(
            f"{BASE_URL}/{mcp_id}/models/bulk_update",
            json={"model_ids": [str(uuid4())], "enabled": False},
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "INTEGRATION_TYPE_MISMATCH"
