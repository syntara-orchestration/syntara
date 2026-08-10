"""Tests for LLMModelService.

Covers:
- get_model: success, not found
- list_models: filtered by integration_id, empty list
- update_model: enable/disable, not found
- bulk_update_models: success, partial match, empty
"""

from datetime import datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.integrations.exceptions import LLMModelNotFoundError
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.llm_model import LLMModel, LLMModelUpdate
from syntara.integrations.services.llm_model_service import LLMModelService


@pytest.fixture
def model_service(test_db_session: AsyncSession, test_user: User) -> LLMModelService:
    """Create an LLMModelService for testing."""
    return LLMModelService(test_db_session, test_user)


@pytest_asyncio.fixture
async def llm_integration(test_db_session: AsyncSession, test_user: User) -> Integration:
    """Create an LLM provider integration for testing."""
    integration = Integration(
        name="Test LLM Provider",
        integration_type=IntegrationType.LLM_PROVIDER,
        configuration={
            "integration_type": "llm_provider",
            "base_url": "https://api.openai.com",
            "provider_hint": "openai",
        },
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    test_db_session.add(integration)
    await test_db_session.flush()
    return integration


@pytest_asyncio.fixture
async def test_model(test_db_session: AsyncSession, llm_integration: Integration) -> LLMModel:
    """Create a test LLM model."""
    model = LLMModel(
        integration_id=llm_integration.id,
        model_id="gpt-4o",
        name="GPT-4o",
        description="Latest GPT model",
        enabled=True,
    )
    test_db_session.add(model)
    await test_db_session.flush()
    return model


# ---------------------------------------------------------------------------
# get_model
# ---------------------------------------------------------------------------


class TestGetModel:
    """Tests for LLMModelService.get_model."""

    @pytest.mark.asyncio
    async def test_get_success(
        self, model_service: LLMModelService, llm_integration: Integration, test_model: LLMModel
    ) -> None:
        """Get a model by ID."""
        result = await model_service.get_model_detail(llm_integration.id, test_model.id)
        assert result.id == test_model.id
        assert result.model_id == "gpt-4o"
        assert result.name == "GPT-4o"

    @pytest.mark.asyncio
    async def test_get_not_found(self, model_service: LLMModelService, llm_integration: Integration) -> None:
        """Get a non-existent model raises."""
        fake_model_id = uuid4()
        with pytest.raises(LLMModelNotFoundError):
            await model_service.get_model_detail(llm_integration.id, fake_model_id)

    @pytest.mark.asyncio
    async def test_get_wrong_integration(self, model_service: LLMModelService, test_model: LLMModel) -> None:
        """Get a model with wrong integration_id raises."""
        fake_integration_id = uuid4()
        with pytest.raises(LLMModelNotFoundError):
            await model_service.get_model_detail(fake_integration_id, test_model.id)


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------


class TestListModels:
    """Tests for LLMModelService.list_models."""

    @pytest.mark.asyncio
    async def test_list_returns_models_for_integration(
        self,
        test_db_session: AsyncSession,
        model_service: LLMModelService,
        llm_integration: Integration,
    ) -> None:
        """List returns all models for the given integration, ordered by model_id."""
        model_b = LLMModel(integration_id=llm_integration.id, model_id="gpt-4o-mini", name="GPT-4o Mini")
        model_a = LLMModel(integration_id=llm_integration.id, model_id="gpt-4o", name="GPT-4o")
        test_db_session.add_all([model_b, model_a])  # add in reverse order
        await test_db_session.flush()

        result = await model_service.list_models(
            query_params_items=[("integration_id", str(llm_integration.id))],
        )
        assert len(result.resources) == 2
        assert {m.model_id for m in result.resources} == {"gpt-4o", "gpt-4o-mini"}

    @pytest.mark.asyncio
    async def test_list_empty(self, model_service: LLMModelService, llm_integration: Integration) -> None:
        """List returns empty when no models exist."""
        result = await model_service.list_models(
            query_params_items=[("integration_id", str(llm_integration.id))],
        )
        assert len(result.resources) == 0

    @pytest.mark.asyncio
    async def test_list_does_not_return_other_integration_models(
        self,
        test_db_session: AsyncSession,
        model_service: LLMModelService,
        llm_integration: Integration,
        test_user: User,
    ) -> None:
        """List only returns models for the specified integration."""
        other_integration = Integration(
            name="Other Provider",
            integration_type=IntegrationType.LLM_PROVIDER,
            configuration={
                "integration_type": "llm_provider",
                "base_url": "https://api.anthropic.com",
                "provider_hint": "anthropic",
            },
            created_by=test_user.id,
            updated_by=test_user.id,
        )
        test_db_session.add(other_integration)
        await test_db_session.flush()

        test_db_session.add(LLMModel(integration_id=llm_integration.id, model_id="gpt-4o", name="GPT-4o"))
        test_db_session.add(LLMModel(integration_id=other_integration.id, model_id="claude-4", name="Claude 4"))
        await test_db_session.flush()

        result = await model_service.list_models(
            query_params_items=[("integration_id", str(llm_integration.id))],
        )
        assert len(result.resources) == 1
        assert result.resources[0].model_id == "gpt-4o"


# ---------------------------------------------------------------------------
# update_model
# ---------------------------------------------------------------------------


class TestUpdateModel:
    """Tests for LLMModelService.update_model."""

    def test_update_empty_payload_raises_validation_error(self) -> None:
        """Empty update payload is rejected by model validator."""
        with pytest.raises(ValidationError, match="At least one field must be provided"):
            LLMModelUpdate()

    @pytest.mark.asyncio
    async def test_disable_model(
        self, model_service: LLMModelService, llm_integration: Integration, test_model: LLMModel
    ) -> None:
        """Disable a model."""
        result = await model_service.update_model(llm_integration.id, test_model.id, LLMModelUpdate(enabled=False))
        assert result.enabled is False

    @pytest.mark.asyncio
    async def test_enable_model(
        self,
        test_db_session: AsyncSession,
        model_service: LLMModelService,
        llm_integration: Integration,
        test_model: LLMModel,
    ) -> None:
        """Enable a disabled model."""
        test_model.enabled = False
        await test_db_session.flush()

        result = await model_service.update_model(llm_integration.id, test_model.id, LLMModelUpdate(enabled=True))
        assert result.enabled is True

    @pytest.mark.asyncio
    async def test_set_default(
        self, model_service: LLMModelService, llm_integration: Integration, test_model: LLMModel
    ) -> None:
        """Set a model as default."""
        result = await model_service.update_model(llm_integration.id, test_model.id, LLMModelUpdate(is_default=True))
        assert result.is_default is True

    @pytest.mark.asyncio
    async def test_set_default_clears_previous(
        self,
        test_db_session: AsyncSession,
        model_service: LLMModelService,
        llm_integration: Integration,
    ) -> None:
        """Setting a new default clears the previous default in the same integration."""
        model_a = LLMModel(integration_id=llm_integration.id, model_id="a", name="A", is_default=True)
        model_b = LLMModel(integration_id=llm_integration.id, model_id="b", name="B", is_default=False)
        test_db_session.add_all([model_a, model_b])
        await test_db_session.flush()

        await model_service.update_model(llm_integration.id, model_b.id, LLMModelUpdate(is_default=True))

        await test_db_session.refresh(model_a)
        await test_db_session.refresh(model_b)
        assert model_a.is_default is False
        assert model_b.is_default is True

    @pytest.mark.asyncio
    async def test_unset_default(
        self, model_service: LLMModelService, llm_integration: Integration, test_model: LLMModel
    ) -> None:
        """Explicitly set is_default=False to unset a default."""
        await model_service.update_model(llm_integration.id, test_model.id, LLMModelUpdate(is_default=True))
        result = await model_service.update_model(llm_integration.id, test_model.id, LLMModelUpdate(is_default=False))
        assert result.is_default is False

    @pytest.mark.asyncio
    async def test_update_not_found(self, model_service: LLMModelService, llm_integration: Integration) -> None:
        """Update a non-existent model raises."""
        fake_model_id = uuid4()
        update = LLMModelUpdate(enabled=False)
        with pytest.raises(LLMModelNotFoundError):
            await model_service.update_model(llm_integration.id, fake_model_id, update)

    @pytest.mark.asyncio
    async def test_update_wrong_integration(self, model_service: LLMModelService, test_model: LLMModel) -> None:
        """Update a model with wrong integration_id raises."""
        fake_integration_id = uuid4()
        update = LLMModelUpdate(enabled=False)
        with pytest.raises(LLMModelNotFoundError):
            await model_service.update_model(fake_integration_id, test_model.id, update)

    @pytest.mark.asyncio
    async def test_set_default_on_disabled_model_raises(
        self,
        test_db_session: AsyncSession,
        model_service: LLMModelService,
        llm_integration: Integration,
        test_model: LLMModel,
    ) -> None:
        """Cannot set a disabled model as default."""
        test_model.enabled = False
        await test_db_session.flush()

        update = LLMModelUpdate(is_default=True)
        with pytest.raises(SafeValueError, match="Cannot set a disabled model as default"):
            await model_service.update_model(llm_integration.id, test_model.id, update)

    @pytest.mark.asyncio
    async def test_disable_and_set_default_simultaneously_raises(
        self,
        model_service: LLMModelService,
        llm_integration: Integration,
        test_model: LLMModel,
    ) -> None:
        """Sending enabled=False and is_default=True in one request raises."""
        update = LLMModelUpdate(enabled=False, is_default=True)
        with pytest.raises(SafeValueError, match="Cannot set a disabled model as default"):
            await model_service.update_model(llm_integration.id, test_model.id, update)

    @pytest.mark.asyncio
    async def test_disable_default_model_clears_default_flag(
        self,
        test_db_session: AsyncSession,
        model_service: LLMModelService,
        llm_integration: Integration,
        test_model: LLMModel,
    ) -> None:
        """Disabling the current default model auto-clears is_default."""
        test_model.is_default = True
        await test_db_session.flush()

        result = await model_service.update_model(llm_integration.id, test_model.id, LLMModelUpdate(enabled=False))
        assert result.enabled is False
        assert result.is_default is False

    @pytest.mark.asyncio
    async def test_disable_non_default_model_leaves_default_unchanged(
        self,
        test_db_session: AsyncSession,
        model_service: LLMModelService,
        llm_integration: Integration,
    ) -> None:
        """Disabling a non-default model does not affect the default model."""
        default_model = LLMModel(
            integration_id=llm_integration.id, model_id="a", name="A", enabled=True, is_default=True
        )
        other_model = LLMModel(
            integration_id=llm_integration.id, model_id="b", name="B", enabled=True, is_default=False
        )
        test_db_session.add_all([default_model, other_model])
        await test_db_session.flush()

        await model_service.update_model(llm_integration.id, other_model.id, LLMModelUpdate(enabled=False))

        await test_db_session.refresh(default_model)
        await test_db_session.refresh(other_model)
        assert default_model.is_default is True
        assert other_model.enabled is False
        assert other_model.is_default is False

    @pytest.mark.asyncio
    async def test_enable_and_set_default_simultaneously(
        self,
        test_db_session: AsyncSession,
        model_service: LLMModelService,
        llm_integration: Integration,
        test_model: LLMModel,
    ) -> None:
        """Sending enabled=True and is_default=True together succeeds."""
        test_model.enabled = False
        await test_db_session.flush()

        result = await model_service.update_model(
            llm_integration.id,
            test_model.id,
            LLMModelUpdate(enabled=True, is_default=True),
        )
        assert result.enabled is True
        assert result.is_default is True


# ---------------------------------------------------------------------------
# bulk_update_models
# ---------------------------------------------------------------------------


class TestBulkUpdateModels:
    """Tests for LLMModelService.bulk_update_models."""

    @pytest.mark.asyncio
    async def test_bulk_disable(
        self,
        test_db_session: AsyncSession,
        model_service: LLMModelService,
        llm_integration: Integration,
    ) -> None:
        """Bulk disable multiple models."""
        model_a = LLMModel(integration_id=llm_integration.id, model_id="a", name="A", enabled=True)
        model_b = LLMModel(integration_id=llm_integration.id, model_id="b", name="B", enabled=True)
        test_db_session.add_all([model_a, model_b])
        await test_db_session.flush()

        result = await model_service.bulk_update_models(llm_integration.id, [model_a.id, model_b.id], enabled=False)
        assert result.updated_count == 2
        assert result.skipped_count == 0
        assert isinstance(result.updated_at, datetime)

        await test_db_session.refresh(model_a)
        await test_db_session.refresh(model_b)
        assert model_a.enabled is False
        assert model_b.enabled is False

    @pytest.mark.asyncio
    async def test_bulk_partial_match(
        self,
        test_db_session: AsyncSession,
        model_service: LLMModelService,
        llm_integration: Integration,
    ) -> None:
        """Bulk update with some non-existent IDs reports skipped count."""
        model = LLMModel(integration_id=llm_integration.id, model_id="a", name="A", enabled=True)
        test_db_session.add(model)
        await test_db_session.flush()

        result = await model_service.bulk_update_models(llm_integration.id, [model.id, uuid4()], enabled=False)
        assert result.updated_count == 1
        assert result.skipped_count == 1

    @pytest.mark.asyncio
    async def test_bulk_empty_list(self, model_service: LLMModelService, llm_integration: Integration) -> None:
        """Bulk update with empty list returns zero counts."""
        result = await model_service.bulk_update_models(llm_integration.id, [], enabled=False)
        assert result.updated_count == 0
        assert result.skipped_count == 0

    @pytest.mark.asyncio
    async def test_bulk_disable_clears_default_flag(
        self,
        test_db_session: AsyncSession,
        model_service: LLMModelService,
        llm_integration: Integration,
    ) -> None:
        """Bulk-disabling a default model auto-clears its is_default flag."""
        model = LLMModel(integration_id=llm_integration.id, model_id="a", name="A", enabled=True, is_default=True)
        test_db_session.add(model)
        await test_db_session.flush()

        await model_service.bulk_update_models(llm_integration.id, [model.id], enabled=False)

        await test_db_session.refresh(model)
        assert model.enabled is False
        assert model.is_default is False

    @pytest.mark.asyncio
    async def test_bulk_disable_only_clears_default_on_affected_models(
        self,
        test_db_session: AsyncSession,
        model_service: LLMModelService,
        llm_integration: Integration,
    ) -> None:
        """Bulk-disabling non-default models leaves the default model untouched."""
        default_model = LLMModel(
            integration_id=llm_integration.id, model_id="a", name="A", enabled=True, is_default=True
        )
        other_model = LLMModel(
            integration_id=llm_integration.id, model_id="b", name="B", enabled=True, is_default=False
        )
        test_db_session.add_all([default_model, other_model])
        await test_db_session.flush()

        await model_service.bulk_update_models(llm_integration.id, [other_model.id], enabled=False)

        await test_db_session.refresh(default_model)
        await test_db_session.refresh(other_model)
        assert default_model.is_default is True
        assert default_model.enabled is True
        assert other_model.enabled is False

    @pytest.mark.asyncio
    async def test_bulk_enable_does_not_touch_default_flag(
        self,
        test_db_session: AsyncSession,
        model_service: LLMModelService,
        llm_integration: Integration,
    ) -> None:
        """Bulk-enabling models does not alter is_default."""
        model = LLMModel(integration_id=llm_integration.id, model_id="a", name="A", enabled=False, is_default=False)
        test_db_session.add(model)
        await test_db_session.flush()

        await model_service.bulk_update_models(llm_integration.id, [model.id], enabled=True)

        await test_db_session.refresh(model)
        assert model.enabled is True
        assert model.is_default is False
