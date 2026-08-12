"""Helper factory for creating Integration test fixtures."""

from typing import assert_never
from uuid import uuid4

from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import (
    AAPConfiguration,
    IntegrationConfigurationTypes,
    LLMProviderConfiguration,
    MCPServerConfiguration,
)


class IntegrationFactory:
    """Factory for creating Integration DB records in tests."""

    def __init__(self, session: AsyncSession, user: User) -> None:
        """Initialize the factory with a DB session and the acting user."""
        self.session = session
        self.user = user

    async def create(
        self,
        name: str | None = None,
        *,
        enabled: bool = True,
        integration_type: IntegrationType = IntegrationType.MCP_SERVER,
        base_url: str = "https://example.com",
    ) -> Integration:
        """Create a single Integration directly in the DB.

        Args:
            name: Integration name (auto-generated if not provided)
            enabled: Whether the integration is enabled
            integration_type: Integration type enum value
            base_url: Base URL for the integration endpoint

        Returns:
            Flushed (but not committed) Integration instance.

        """
        if name is None:
            name = f"intg-{uuid4().hex[:8]}"

        configuration: IntegrationConfigurationTypes
        if integration_type == IntegrationType.MCP_SERVER:
            configuration = MCPServerConfiguration(
                integration_type="mcp_server",
                base_url=base_url,
            )
        elif integration_type == IntegrationType.LLM_PROVIDER:
            configuration = LLMProviderConfiguration(
                integration_type="llm_provider",
                base_url=base_url,
                provider_hint="openai",
            )
        elif integration_type == IntegrationType.ANSIBLE_AUTOMATION_PLATFORM:
            configuration = AAPConfiguration(
                integration_type="ansible_automation_platform",
                base_url=base_url,
            )
        else:
            assert_never(integration_type)

        integration = Integration(
            name=name,
            integration_type=integration_type,
            configuration=configuration,
            enabled=enabled,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(integration)
        await self.session.flush()
        return integration

    async def create_many(
        self,
        count: int,
        *,
        prefix: str = "intg",
        enabled: bool = True,
        integration_type: IntegrationType = IntegrationType.MCP_SERVER,
    ) -> list[Integration]:
        """Create multiple Integration records.

        Args:
            count: Number of integrations to create
            prefix: Name prefix for each integration
            enabled: Whether integrations are enabled
            integration_type: Integration type for all created integrations

        Returns:
            List of flushed (but not committed) Integration instances.

        """
        integrations = []
        for i in range(count):
            integration = await self.create(
                name=f"{prefix}-{uuid4().hex[:8]}-{i}",
                enabled=enabled,
                integration_type=integration_type,
            )
            integrations.append(integration)
        return integrations
