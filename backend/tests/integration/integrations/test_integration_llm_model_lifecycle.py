"""Tests for Integration ↔ LLM Model lifecycle.

Covers:
- create_integration(llm_provider) with discovered_models creates LLMModel records
- create_integration(llm_provider) without discovered_models creates no models
- delete_integration() hard-deletes linked LLMModel records
- refresh_resources() resolves credential and syncs LLMModel records
- _sync_llm_models creates, updates, and soft-disables missing models
- validate_integration() does NOT sync models
- discovered_models validation (wrong type, duplicates)
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
import pytest_asyncio
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.integrations.adapters.protocol import (
    DiscoveredLLMModel,
    DiscoverResult,
    ValidateResult,
)
from syntara.integrations.models.integration import (
    Integration,
    IntegrationCreate,
    IntegrationRefreshStatus,
    IntegrationType,
)
from syntara.integrations.models.llm_model import LLMModel, ModelCapabilityProfile
from syntara.integrations.services.integration_service import IntegrationService
from tests.integration.integrations.conftest import make_llm_create


def _make_discovered_model(model_id: str, name: str, description: str | None = None) -> DiscoveredLLMModel:
    return DiscoveredLLMModel(id=model_id, name=name, description=description)


@pytest_asyncio.fixture
async def llm_integration(
    test_db_session: AsyncSession,
    integration_service: IntegrationService,
    llm_credential_id: UUID,
) -> dict[str, Any]:
    """Create an llm_provider integration and return its id."""
    result = await integration_service.create_integration(
        make_llm_create("LLM Target", management_credential_id=llm_credential_id)
    )
    await test_db_session.flush()
    return {"integration_id": result.id}


# ---------------------------------------------------------------------------
# Create integration with models
# ---------------------------------------------------------------------------


class TestCreateIntegrationWithModels:
    """create_integration(llm_provider) with discovered_models."""

    @pytest.mark.asyncio
    async def test_create_without_models_creates_no_records(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        llm_credential_id: UUID,
    ) -> None:
        """Creating an LLM integration without discovered_models creates no LLMModel records."""
        result = await integration_service.create_integration(
            make_llm_create(management_credential_id=llm_credential_id)
        )
        await test_db_session.flush()

        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == result.id))).all()
        assert len(models) == 0

    @pytest.mark.asyncio
    async def test_create_with_discovered_models(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        llm_credential_id: UUID,
    ) -> None:
        """Creating with discovered_models creates LLMModel records with correct enabled states."""
        data = make_llm_create(
            name="LLM With Models",
            management_credential_id=llm_credential_id,
            discovered_models=[
                {"model_id": "gpt-4o", "name": "GPT-4o", "enabled": True},
                {"model_id": "gpt-4o-mini", "name": "GPT-4o Mini", "enabled": False},
            ],
        )
        result = await integration_service.create_integration(data)
        await test_db_session.flush()

        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == result.id))).all()
        assert len(models) == 2

        by_id = {m.model_id: m for m in models}
        assert by_id["gpt-4o"].enabled is True
        assert by_id["gpt-4o"].name == "GPT-4o"
        assert by_id["gpt-4o-mini"].enabled is False

    @pytest.mark.asyncio
    async def test_create_with_default_model(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        llm_credential_id: UUID,
    ) -> None:
        """Creating with is_default sets exactly one model as default."""
        data = make_llm_create(
            name="LLM Default",
            management_credential_id=llm_credential_id,
            discovered_models=[
                {"model_id": "gpt-4o", "name": "GPT-4o", "is_default": True},
                {"model_id": "gpt-4o-mini", "name": "GPT-4o Mini", "is_default": False},
            ],
        )
        result = await integration_service.create_integration(data)
        await test_db_session.flush()

        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == result.id))).all()
        by_id = {m.model_id: m for m in models}
        assert by_id["gpt-4o"].is_default is True
        assert by_id["gpt-4o-mini"].is_default is False

    @pytest.mark.asyncio
    async def test_create_with_models_sets_refresh_status(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        llm_credential_id: UUID,
    ) -> None:
        """Creating with discovered_models sets refresh_status=AVAILABLE."""
        data = make_llm_create(
            name="LLM Status",
            management_credential_id=llm_credential_id,
            discovered_models=[
                {"model_id": "gpt-4o", "name": "GPT-4o"},
            ],
        )
        result = await integration_service.create_integration(data)
        assert result.refresh_status == IntegrationRefreshStatus.AVAILABLE
        assert result.last_refreshed_at is not None

    @pytest.mark.asyncio
    async def test_create_with_models_populates_model_counts(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        llm_credential_id: UUID,
    ) -> None:
        """IntegrationRead includes model counts."""
        data = make_llm_create(
            name="LLM Counts",
            management_credential_id=llm_credential_id,
            discovered_models=[
                {"model_id": "gpt-4o", "name": "GPT-4o", "enabled": True},
                {"model_id": "gpt-3.5", "name": "GPT-3.5", "enabled": False},
            ],
        )
        result = await integration_service.create_integration(data)
        assert result.total_model_count == 2
        assert result.enabled_model_count == 1

    @pytest.mark.asyncio
    async def test_discovered_models_rejected_for_mcp(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        """discovered_models is only valid for llm_provider integrations."""
        with pytest.raises(ValueError, match="discovered_models is only supported for llm_provider"):
            IntegrationCreate(
                name="Bad MCP",
                integration_type=IntegrationType.MCP_SERVER,
                configuration={"integration_type": "mcp_server", "base_url": "https://mcp.example.com"},
                discovered_models=[{"model_id": "gpt-4o", "name": "GPT-4o"}],
            )

    @pytest.mark.asyncio
    async def test_discovered_models_rejects_duplicates(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        """Duplicate model IDs in discovered_models are rejected."""
        with pytest.raises(ValueError, match="duplicate model IDs"):
            make_llm_create(
                name="Dupes",
                discovered_models=[
                    {"model_id": "gpt-4o", "name": "GPT-4o"},
                    {"model_id": "gpt-4o", "name": "GPT-4o Copy"},
                ],
            )

    @pytest.mark.asyncio
    async def test_discovered_models_rejects_multiple_defaults(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        """Multiple default models in discovered_models are rejected."""
        with pytest.raises(ValueError, match="multiple default models"):
            make_llm_create(
                name="Multi Default",
                discovered_models=[
                    {"model_id": "gpt-4o", "name": "GPT-4o", "is_default": True},
                    {"model_id": "gpt-4o-mini", "name": "GPT-4o Mini", "is_default": True},
                ],
            )


# ---------------------------------------------------------------------------
# Delete integration cascades to models
# ---------------------------------------------------------------------------


class TestDeleteIntegrationCascadesToModels:
    """delete_integration() must hard-delete the linked LLMModel records."""

    @pytest.mark.asyncio
    async def test_deletes_linked_models(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        llm_credential_id: UUID,
    ) -> None:
        """Deleting an LLM integration hard-deletes its models."""
        data = make_llm_create(
            name="To Delete",
            management_credential_id=llm_credential_id,
            discovered_models=[
                {"model_id": "gpt-4o", "name": "GPT-4o"},
                {"model_id": "gpt-4o-mini", "name": "GPT-4o Mini"},
            ],
        )
        created = await integration_service.create_integration(data)
        await test_db_session.flush()
        integration_id = created.id

        # Verify models exist
        models_before = (
            await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))
        ).all()
        assert len(models_before) == 2

        await integration_service.delete_integration(integration_id)
        await test_db_session.flush()

        # Models are hard-deleted (not soft-deleted)
        models_after = (
            await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))
        ).all()
        assert len(models_after) == 0

    @pytest.mark.asyncio
    async def test_delete_without_models_is_safe(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        llm_credential_id: UUID,
    ) -> None:
        """Deleting an integration with no models does not raise."""
        created = await integration_service.create_integration(
            make_llm_create("No Models", management_credential_id=llm_credential_id)
        )
        await test_db_session.flush()
        await integration_service.delete_integration(created.id)


# ---------------------------------------------------------------------------
# Refresh integration resources (models)
# ---------------------------------------------------------------------------


class TestRefreshLLMModels:
    """refresh_resources() for llm_provider calls discover and syncs LLMModel records."""

    @pytest.mark.asyncio
    async def test_refresh_creates_model_records(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        llm_integration: dict[str, Any],
        mock_secret_service: AsyncMock,
    ) -> None:
        """refresh_resources creates LLMModel records on success."""
        integration_id = llm_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user, secret_service=mock_secret_service)

        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[
                _make_discovered_model("gpt-4o", "GPT-4o"),
                _make_discovered_model("gpt-4o-mini", "GPT-4o Mini"),
            ],
        )

        with (
            patch(
                "syntara.integrations.services.integration_service.create_health_check_adapter"
            ) as mock_adapter_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=discover_result)
            mock_adapter_factory.return_value = mock_adapter

            result = await service.refresh_resources(integration_id)

        assert result.synced_count == 2
        assert result.updated_count == 0
        assert result.missing_count == 0

        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        assert len(models) == 2
        assert {m.model_id for m in models} == {"gpt-4o", "gpt-4o-mini"}

    @pytest.mark.asyncio
    async def test_refresh_updates_existing_models(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        llm_integration: dict[str, Any],
        mock_secret_service: AsyncMock,
    ) -> None:
        """refresh_resources updates name/description of existing models, preserves enabled state."""
        integration_id = llm_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user, secret_service=mock_secret_service)

        # First refresh: create models
        first_discover = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[_make_discovered_model("gpt-4o", "GPT-4o", "Original")],
        )

        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=first_discover)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(integration_id)

        # Disable the model
        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        models[0].enabled = False
        await test_db_session.flush()

        # Second refresh: update name/description
        second_discover = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[_make_discovered_model("gpt-4o", "GPT-4o Updated", "New description")],
        )

        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=second_discover)
            mock_factory.return_value = mock_adapter
            result = await service.refresh_resources(integration_id)

        assert result.synced_count == 0
        assert result.updated_count == 1

        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        assert len(models) == 1
        assert models[0].name == "GPT-4o Updated"
        assert models[0].description == "New description"
        assert models[0].enabled is False  # preserved

    @pytest.mark.asyncio
    async def test_refresh_preserves_mixed_enabled_states(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        llm_integration: dict[str, Any],
        mock_secret_service: AsyncMock,
    ) -> None:
        """Refresh preserves per-model enabled state when descriptions change."""
        integration_id = llm_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user, secret_service=mock_secret_service)

        # First refresh: create two models (both enabled by default)
        first_discover = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[
                _make_discovered_model("model-a", "Model A", "Original A"),
                _make_discovered_model("model-b", "Model B", "Original B"),
            ],
        )

        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=first_discover)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(integration_id)

        # User disables model-b, keeps model-a enabled
        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        by_id = {m.model_id: m for m in models}
        by_id["model-b"].enabled = False
        await test_db_session.flush()

        # Second refresh: same models, updated descriptions
        second_discover = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[
                _make_discovered_model("model-a", "Model A Updated", "New desc A"),
                _make_discovered_model("model-b", "Model B Updated", "New desc B"),
            ],
        )

        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=second_discover)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(integration_id)

        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        by_id = {m.model_id: m for m in models}
        assert by_id["model-a"].enabled is True
        assert by_id["model-a"].description == "New desc A"
        assert by_id["model-b"].enabled is False  # user's choice preserved
        assert by_id["model-b"].description == "New desc B"  # description still updated

    @pytest.mark.asyncio
    async def test_refresh_preserves_is_default(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        llm_integration: dict[str, Any],
        mock_secret_service: AsyncMock,
    ) -> None:
        """refresh_resources preserves the user's is_default selection."""
        integration_id = llm_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user, secret_service=mock_secret_service)

        # First refresh: create two models
        first_discover = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[
                _make_discovered_model("model-a", "Model A"),
                _make_discovered_model("model-b", "Model B"),
            ],
        )

        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=first_discover)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(integration_id)

        # User sets model-b as default
        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        by_id = {m.model_id: m for m in models}
        by_id["model-b"].is_default = True
        await test_db_session.flush()

        # Second refresh: same models, no default_model_id
        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=first_discover)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(integration_id)

        # is_default should be preserved
        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        by_id = {m.model_id: m for m in models}
        assert by_id["model-b"].is_default is True
        assert by_id["model-a"].is_default is False

    @pytest.mark.asyncio
    async def test_refresh_keeps_missing_models_enabled(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        llm_integration: dict[str, Any],
        mock_secret_service: AsyncMock,
    ) -> None:
        """Models no longer returned by the provider are kept with enabled unchanged."""
        integration_id = llm_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user, secret_service=mock_secret_service)

        # First refresh: create two models
        first_discover = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[
                _make_discovered_model("model-a", "Model A"),
                _make_discovered_model("model-b", "Model B"),
            ],
        )

        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=first_discover)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(integration_id)

        # Second refresh: only model-a returned
        second_discover = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[_make_discovered_model("model-a", "Model A")],
        )

        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=second_discover)
            mock_factory.return_value = mock_adapter
            result = await service.refresh_resources(integration_id)

        assert result.missing_count == 1  # model-b missing

        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        by_id = {m.model_id: m for m in models}
        assert set(by_id) == {"model-a", "model-b"}  # both rows preserved
        assert by_id["model-a"].enabled is True
        assert by_id["model-b"].enabled is True  # enabled is admin-controlled, not changed by discovery

    @pytest.mark.asyncio
    async def test_refresh_warns_when_default_model_missing(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        llm_integration: dict[str, Any],
        mock_secret_service: AsyncMock,
    ) -> None:
        """When the default model disappears, WARNING status is set but enabled is unchanged."""
        integration_id = llm_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user, secret_service=mock_secret_service)

        first_discover = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[
                _make_discovered_model("model-a", "A"),
                _make_discovered_model("model-b", "B"),
            ],
        )

        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=first_discover)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(integration_id)

        # Set model-b as default
        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        by_id = {m.model_id: m for m in models}
        by_id["model-b"].is_default = True
        await test_db_session.flush()

        # Refresh without model-b — default model disappears
        second_discover = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[_make_discovered_model("model-a", "A")],
        )

        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=second_discover)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(integration_id)

        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        by_id = {m.model_id: m for m in models}
        assert set(by_id) == {"model-a", "model-b"}  # both rows preserved
        assert by_id["model-b"].enabled is True  # enabled is admin-controlled, not changed by discovery

        integration = (await test_db_session.exec(select(Integration).where(Integration.id == integration_id))).one()
        assert integration.refresh_status == IntegrationRefreshStatus.WARNING
        assert "model-b" in (integration.refresh_error or "")

    @pytest.mark.asyncio
    async def test_refresh_preserves_last_successful_on_failure(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        llm_integration: dict[str, Any],
        mock_secret_service: AsyncMock,
    ) -> None:
        """A failed refresh advances last_refreshed_at but leaves last_successful_refresh_at intact."""
        integration_id = llm_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user, secret_service=mock_secret_service)

        good = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[_make_discovered_model("model-a", "A")],
        )
        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=good)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(integration_id)

        integration = (await test_db_session.exec(select(Integration).where(Integration.id == integration_id))).one()
        last_success = integration.last_successful_refresh_at
        assert last_success is not None

        bad = DiscoverResult(success=False, checked_at=datetime.now(UTC), error="upstream down")
        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=bad)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(integration_id)

        integration = (await test_db_session.exec(select(Integration).where(Integration.id == integration_id))).one()
        assert integration.refresh_status == IntegrationRefreshStatus.ERROR
        assert integration.last_successful_refresh_at == last_success  # unchanged by the failure
        assert integration.last_refreshed_at is not None
        assert integration.last_refreshed_at >= last_success  # attempt timestamp advanced

    @pytest.mark.asyncio
    async def test_refresh_populates_profile_for_openai_models(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        llm_integration: dict[str, Any],
        mock_secret_service: AsyncMock,
    ) -> None:
        """refresh_resources populates profile from langchain registry for known OpenAI models."""
        integration_id = llm_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user, secret_service=mock_secret_service)

        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[
                _make_discovered_model("gpt-4o", "GPT-4o"),
                _make_discovered_model("unknown-custom-model", "Custom Model"),
            ],
        )

        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=discover_result)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(integration_id)

        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        by_id = {m.model_id: m for m in models}

        assert by_id["gpt-4o"].profile is not None
        assert by_id["gpt-4o"].profile["max_input_tokens"] == 128000
        assert "tool_calling" in by_id["gpt-4o"].profile

        assert by_id["unknown-custom-model"].profile is None

    @pytest.mark.asyncio
    async def test_capability_profile_accessor_after_db_round_trip(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        llm_integration: dict[str, Any],
        mock_secret_service: AsyncMock,
    ) -> None:
        """capability_profile property returns typed data after a DB round-trip."""
        integration_id = llm_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user, secret_service=mock_secret_service)

        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[_make_discovered_model("gpt-4o", "GPT-4o")],
        )

        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=discover_result)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(integration_id)

        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        assert len(models) == 1

        cap = models[0].capability_profile
        assert isinstance(cap, ModelCapabilityProfile)
        assert cap.max_input_tokens == 128000
        assert cap.max_output_tokens == 16384
        assert cap.tool_calling is True

    @pytest.mark.asyncio
    async def test_capability_profile_none_for_unknown_model(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        llm_integration: dict[str, Any],
        mock_secret_service: AsyncMock,
    ) -> None:
        """capability_profile returns None for models without a profile."""
        integration_id = llm_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user, secret_service=mock_secret_service)

        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[_make_discovered_model("unknown-custom-model", "Custom")],
        )

        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=discover_result)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(integration_id)

        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        assert len(models) == 1
        assert models[0].capability_profile is None

    @pytest.mark.asyncio
    async def test_refresh_populates_profile_for_anthropic_provider(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        mock_secret_service: AsyncMock,
        llm_credential_id: UUID,
    ) -> None:
        """Profile is populated for Anthropic models via the langchain-anthropic registry."""
        anthropic_create = make_llm_create(
            name="Anthropic Provider",
            management_credential_id=llm_credential_id,
            configuration={
                "integration_type": "llm_provider",
                "base_url": "https://api.anthropic.com",
                "provider_hint": "anthropic",
            },
        )
        result = await IntegrationService(
            test_db_session, test_user, secret_service=mock_secret_service
        ).create_integration(anthropic_create)
        await test_db_session.flush()

        service = IntegrationService(test_db_session, test_user, secret_service=mock_secret_service)
        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[
                _make_discovered_model("claude-sonnet-4-20250514", "Claude Sonnet 4"),
                _make_discovered_model("unknown-custom-llm", "Custom LLM"),
            ],
        )

        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=discover_result)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(result.id)

        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == result.id))).all()
        by_id = {m.model_id: m for m in models}
        assert len(models) == 2

        assert by_id["claude-sonnet-4-20250514"].profile is not None
        assert by_id["claude-sonnet-4-20250514"].profile["max_input_tokens"] == 200000
        assert by_id["unknown-custom-llm"].profile is None

    @pytest.mark.asyncio
    async def test_refresh_updates_profile_on_existing_models(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        llm_integration: dict[str, Any],
        mock_secret_service: AsyncMock,
    ) -> None:
        """Profile is updated on refresh even for existing models."""
        integration_id = llm_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user, secret_service=mock_secret_service)

        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[_make_discovered_model("gpt-4o", "GPT-4o")],
        )

        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=discover_result)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(integration_id)

        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        assert models[0].profile is not None
        assert models[0].profile["max_input_tokens"] == 128000

        # Second refresh should also populate profile
        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=discover_result)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(integration_id)

        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        assert models[0].profile is not None

    @pytest.mark.asyncio
    async def test_refresh_sets_status_available(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        llm_integration: dict[str, Any],
        mock_secret_service: AsyncMock,
    ) -> None:
        """Successful refresh sets refresh_status=AVAILABLE."""
        integration_id = llm_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user, secret_service=mock_secret_service)

        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[],
        )

        with (
            patch(
                "syntara.integrations.services.integration_service.create_health_check_adapter"
            ) as mock_adapter_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=discover_result)
            mock_adapter_factory.return_value = mock_adapter

            await service.refresh_resources(integration_id)

        integration = (await test_db_session.exec(select(Integration).where(Integration.id == integration_id))).one()
        assert integration.refresh_status == IntegrationRefreshStatus.AVAILABLE
        assert integration.last_refreshed_at is not None

    @pytest.mark.asyncio
    async def test_refresh_failed_discover_sets_error(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        llm_integration: dict[str, Any],
        mock_secret_service: AsyncMock,
    ) -> None:
        """Failed discover sets refresh_status=ERROR."""
        integration_id = llm_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user, secret_service=mock_secret_service)

        discover_result = DiscoverResult(
            success=False,
            checked_at=datetime.now(UTC),
            error="Authentication failed",
        )

        with (
            patch(
                "syntara.integrations.services.integration_service.create_health_check_adapter"
            ) as mock_adapter_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=discover_result)
            mock_adapter_factory.return_value = mock_adapter

            result = await service.refresh_resources(integration_id)

        assert result.synced_count == 0

    @pytest.mark.asyncio
    async def test_create_with_partial_enabled_map(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        llm_credential_id: UUID,
    ) -> None:
        """Models not in enabled_map default to enabled=True."""
        data = make_llm_create(
            name="LLM Partial Map",
            management_credential_id=llm_credential_id,
            discovered_models=[
                {"model_id": "gpt-4o", "name": "GPT-4o", "enabled": False},
                {"model_id": "gpt-4o-mini", "name": "GPT-4o Mini"},
            ],
        )
        result = await integration_service.create_integration(data)
        await test_db_session.flush()

        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == result.id))).all()
        by_id = {m.model_id: m for m in models}
        assert by_id["gpt-4o"].enabled is False
        assert by_id["gpt-4o-mini"].enabled is True

    @pytest.mark.asyncio
    async def test_refresh_preserves_existing_default(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        llm_integration: dict[str, Any],
        mock_secret_service: AsyncMock,
    ) -> None:
        """Refresh without default_model_id preserves existing is_default state."""
        integration_id = llm_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user, secret_service=mock_secret_service)

        first_discover = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[
                _make_discovered_model("model-a", "A"),
                _make_discovered_model("model-b", "B"),
            ],
        )

        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=first_discover)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(integration_id)

        # Set model-a as default manually
        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        by_id = {m.model_id: m for m in models}
        by_id["model-a"].is_default = True
        await test_db_session.flush()

        # Refresh again — no default_model_id, so existing default should be preserved
        with (
            patch("syntara.integrations.services.integration_service.create_health_check_adapter") as mock_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.discover = AsyncMock(return_value=first_discover)
            mock_factory.return_value = mock_adapter
            await service.refresh_resources(integration_id)

        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        by_id = {m.model_id: m for m in models}
        assert by_id["model-a"].is_default is True
        assert by_id["model-b"].is_default is False


# ---------------------------------------------------------------------------
# Validate does NOT sync models
# ---------------------------------------------------------------------------


class TestValidateDoesNotSyncModels:
    """validate_integration() must NOT create or update LLMModel records."""

    @pytest.mark.asyncio
    async def test_validate_does_not_create_models(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        llm_integration: dict[str, Any],
        mock_secret_service: AsyncMock,
    ) -> None:
        integration_id = llm_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user, secret_service=mock_secret_service)

        success_result = ValidateResult(success=True, checked_at=datetime.now(UTC))

        with (
            patch(
                "syntara.integrations.services.integration_service.create_health_check_adapter"
            ) as mock_adapter_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
        ):
            mock_settings.return_value.get = AsyncMock(return_value=10)
            mock_adapter = AsyncMock()
            mock_adapter.validate = AsyncMock(return_value=success_result)
            mock_adapter_factory.return_value = mock_adapter

            result = await service.validate_integration(integration_id)

        assert result.success is True

        models = (await test_db_session.exec(select(LLMModel).where(LLMModel.integration_id == integration_id))).all()
        assert len(models) == 0
