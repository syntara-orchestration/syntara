"""Tests for integration credential type and discovered resource validation."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.integrations.exceptions import IntegrationCredentialTypeMismatchError
from syntara.integrations.models.integration import IntegrationCreate, IntegrationType
from syntara.integrations.services.integration_service import IntegrationService


@pytest.fixture
def integration_service(test_db_session: AsyncSession, test_user: User) -> IntegrationService:
    """Create an IntegrationService without bypassing credential validation."""
    return IntegrationService(test_db_session, test_user)


class TestCredentialTypeValidation:
    """Tests for _validate_credential_type — NOT bypassed by _skip_credential_validation."""

    @pytest.mark.asyncio
    async def test_mcp_with_bearer_token_succeeds(self, integration_service: IntegrationService) -> None:
        mock_type = type("MockType", (), {"name": "HTTP Bearer Token"})()
        with patch(
            "syntara.integrations.services.integration_service.fetch_credential_with_type",
            new_callable=AsyncMock,
            return_value=(None, mock_type),
        ):
            await integration_service._validate_credential_type(IntegrationType.MCP_SERVER, uuid4())

    @pytest.mark.asyncio
    async def test_mcp_with_wrong_type_raises(self, integration_service: IntegrationService) -> None:
        mock_type = type("MockType", (), {"name": "SSH"})()
        credential_id = uuid4()
        with (
            patch(
                "syntara.integrations.services.integration_service.fetch_credential_with_type",
                new_callable=AsyncMock,
                return_value=(None, mock_type),
            ),
            pytest.raises(IntegrationCredentialTypeMismatchError),
        ):
            await integration_service._validate_credential_type(IntegrationType.MCP_SERVER, credential_id)

    @pytest.mark.asyncio
    async def test_llm_with_llm_provider_succeeds(self, integration_service: IntegrationService) -> None:
        mock_type = type("MockType", (), {"name": "LLM Provider"})()
        with patch(
            "syntara.integrations.services.integration_service.fetch_credential_with_type",
            new_callable=AsyncMock,
            return_value=(None, mock_type),
        ):
            await integration_service._validate_credential_type(IntegrationType.LLM_PROVIDER, uuid4())

    @pytest.mark.asyncio
    async def test_llm_with_wrong_type_raises(self, integration_service: IntegrationService) -> None:
        mock_type = type("MockType", (), {"name": "HTTP Bearer Token"})()
        credential_id = uuid4()
        with (
            patch(
                "syntara.integrations.services.integration_service.fetch_credential_with_type",
                new_callable=AsyncMock,
                return_value=(None, mock_type),
            ),
            pytest.raises(IntegrationCredentialTypeMismatchError),
        ):
            await integration_service._validate_credential_type(IntegrationType.LLM_PROVIDER, credential_id)

    @pytest.mark.asyncio
    async def test_aap_with_aap_credential_succeeds(self, integration_service: IntegrationService) -> None:
        mock_type = type("MockType", (), {"name": "Ansible Automation Platform"})()
        with patch(
            "syntara.integrations.services.integration_service.fetch_credential_with_type",
            new_callable=AsyncMock,
            return_value=(None, mock_type),
        ):
            await integration_service._validate_credential_type(IntegrationType.ANSIBLE_AUTOMATION_PLATFORM, uuid4())

    @pytest.mark.asyncio
    async def test_error_message_includes_allowed_types(self, integration_service: IntegrationService) -> None:
        mock_type = type("MockType", (), {"name": "SSH"})()
        credential_id = uuid4()
        with (
            patch(
                "syntara.integrations.services.integration_service.fetch_credential_with_type",
                new_callable=AsyncMock,
                return_value=(None, mock_type),
            ),
            pytest.raises(IntegrationCredentialTypeMismatchError, match="HTTP Bearer Token"),
        ):
            await integration_service._validate_credential_type(IntegrationType.MCP_SERVER, credential_id)


def _fake_tool() -> object:
    return type("Tool", (), {"name": "t1", "description": None, "parameters": None, "enabled": True})()


def _fake_model() -> object:
    return type(
        "Model",
        (),
        {
            "model_id": "m1",
            "name": "M1",
            "description": None,
            "enabled": True,
            "is_default": False,
        },
    )()


_MCP_CONFIG: dict[str, str] = {"integration_type": "mcp_server", "base_url": "https://test.com"}
_LLM_CONFIG: dict[str, str] = {
    "integration_type": "llm_provider",
    "base_url": "https://test.com",
    "provider_hint": "custom",
}


class TestDiscoveredResourcesValidation:
    """Tests for _validate_discovered_resources."""

    def test_mcp_with_discovered_models_raises(self) -> None:
        data = IntegrationCreate(
            name="test",
            integration_type=IntegrationType.MCP_SERVER,
            configuration=_MCP_CONFIG,
        )
        data.discovered_models = [_fake_model()]  # type: ignore[list-item]
        with pytest.raises(ValueError, match="discovered_models is not valid"):
            IntegrationService._validate_discovered_resources(data)

    def test_llm_with_discovered_tools_raises(self) -> None:
        data = IntegrationCreate(
            name="test",
            integration_type=IntegrationType.LLM_PROVIDER,
            configuration=_LLM_CONFIG,
        )
        data.discovered_tools = [_fake_tool()]  # type: ignore[list-item]
        with pytest.raises(ValueError, match="discovered_tools is not valid"):
            IntegrationService._validate_discovered_resources(data)

    def test_mcp_with_discovered_tools_passes(self) -> None:
        data = IntegrationCreate(
            name="test",
            integration_type=IntegrationType.MCP_SERVER,
            configuration=_MCP_CONFIG,
            discovered_tools=[_fake_tool()],
        )
        IntegrationService._validate_discovered_resources(data)

    def test_no_discovered_resources_passes(self) -> None:
        data = IntegrationCreate(
            name="test",
            integration_type=IntegrationType.MCP_SERVER,
            configuration=_MCP_CONFIG,
        )
        IntegrationService._validate_discovered_resources(data)
