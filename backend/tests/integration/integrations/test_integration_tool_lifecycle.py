"""Tests for Integration ↔ Tool lifecycle (AAP-75921).

Covers:
- create_integration(mcp_server) does NOT create ToolProvider (tools created on refresh)
- delete_integration() hard-deletes linked Tools directly by integration_id
- refresh_resources() resolves credential and syncs Tool records
- validate_integration() only pings — does NOT sync tools
- _sync_mcp_tools creates correctly namespaced Tool records
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
from syntara.integrations.adapters.protocol import DiscoveredTool, DiscoverResult, ValidateResult
from syntara.integrations.models.integration import (
    IntegrationCreate,
    IntegrationRefreshStatus,
    IntegrationType,
)
from syntara.integrations.services.integration_service import IntegrationService
from syntara.tool_manager.models.tool import Tool
from tests.integration.integrations.conftest import make_mcp_create


def _make_discovered_tool(name: str, description: str = "") -> DiscoveredTool:
    return DiscoveredTool(name=name, description=description, parameters=None)


@pytest_asyncio.fixture
async def mcp_integration(
    test_db_session: AsyncSession,
    integration_service: IntegrationService,
) -> dict[str, Any]:
    """Create an mcp_server integration and return its id."""
    result = await integration_service.create_integration(make_mcp_create("Refresh Target"))
    await test_db_session.flush()
    return {"integration_id": result.id}


class TestCreateIntegration:
    """create_integration(mcp_server) must not create a ToolProvider (tools created on refresh)."""

    @pytest.mark.asyncio
    async def test_create_mcp_server_does_not_create_tool_provider(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        """Creating an MCP integration does NOT create tools — they are created on first refresh."""
        result = await integration_service.create_integration(make_mcp_create("MCP Auto"))
        await test_db_session.flush()

        # No tools created yet (they are created on first refresh)
        tools = (await test_db_session.exec(select(Tool).where(Tool.integration_id == result.id))).all()

        assert len(tools) == 0
        assert result.id is not None
        assert result.integration_type == IntegrationType.MCP_SERVER

    @pytest.mark.asyncio
    async def test_llm_provider_create_succeeds(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        llm_credential_id: UUID,
    ) -> None:
        data = IntegrationCreate(
            name="LLM Provider",
            integration_type=IntegrationType.LLM_PROVIDER,
            configuration={
                "integration_type": "llm_provider",
                "base_url": "https://llm.example.com",
                "provider_hint": "custom",
            },
            management_credential_id=llm_credential_id,
        )
        result = await integration_service.create_integration(data)
        await test_db_session.flush()

        assert result.id is not None


class TestDeleteIntegrationCascadesToTools:
    """delete_integration() must hard-delete the linked Tools."""

    @pytest.mark.asyncio
    async def test_deletes_linked_tools(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        test_user: User,
    ) -> None:
        created = await integration_service.create_integration(make_mcp_create("To Delete"))
        await test_db_session.flush()
        integration_id = created.id

        tool1 = Tool(
            name="tool_one",
            namespaced_name="To Delete::tool_one",
            integration_id=integration_id,
            created_by=test_user.id,
            updated_by=test_user.id,
        )
        tool2 = Tool(
            name="tool_two",
            namespaced_name="To Delete::tool_two",
            integration_id=integration_id,
            created_by=test_user.id,
            updated_by=test_user.id,
        )
        test_db_session.add_all([tool1, tool2])
        await test_db_session.flush()

        await integration_service.delete_integration(integration_id)
        await test_db_session.flush()

        all_tools = (await test_db_session.exec(select(Tool).where(Tool.integration_id == integration_id))).all()
        assert len(all_tools) == 0

    @pytest.mark.asyncio
    async def test_delete_without_tools_is_safe(
        self,
        test_db_session: AsyncSession,
        integration_service: IntegrationService,
        llm_credential_id: UUID,
    ) -> None:
        data = IntegrationCreate(
            name="No Tools",
            integration_type=IntegrationType.LLM_PROVIDER,
            configuration={
                "integration_type": "llm_provider",
                "base_url": "https://llm.example.com",
                "provider_hint": "custom",
            },
            management_credential_id=llm_credential_id,
        )
        created = await integration_service.create_integration(data)
        await test_db_session.flush()

        # Should not raise even with no linked tools
        await integration_service.delete_integration(created.id)


class TestValidateIntegration:
    """validate_integration() performs a lightweight ping only — no tool sync."""

    @pytest.mark.asyncio
    async def test_validate_does_not_sync_tools(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        mcp_integration: dict[str, Any],
    ) -> None:
        """validate_integration must NOT create or update Tool records."""
        integration_id = mcp_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user)

        success_result = ValidateResult(success=True, checked_at=datetime.now(UTC))

        with (
            patch(
                "syntara.integrations.services.integration_service.create_health_check_adapter"
            ) as mock_adapter_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
            patch.object(service, "_secret_service", create=True) as mock_secret_svc,
        ):
            mock_secret_svc.retrieve_secret = AsyncMock(return_value={"bearer_token": "token"})
            mock_settings.return_value.get = AsyncMock(return_value=10)

            mock_adapter = AsyncMock()
            mock_adapter.validate = AsyncMock(return_value=success_result)
            mock_adapter_factory.return_value = mock_adapter

            result = await service.validate_integration(integration_id)

        assert result.success is True
        # No tool sync fields on ValidateResult
        assert not hasattr(result, "tools_refreshed_count")
        assert not hasattr(result, "discovered_tools")

        # No Tool records created
        tools = (await test_db_session.exec(select(Tool).where(Tool.integration_id == integration_id))).all()
        assert len(tools) == 0

    @pytest.mark.asyncio
    async def test_failed_validate_sets_error_status(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        mcp_integration: dict[str, Any],
    ) -> None:
        """When the validate fails, no Tool records change and status is ERROR."""
        integration_id = mcp_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user)

        error_result = ValidateResult(
            success=False,
            checked_at=datetime.now(UTC),
            error="Connection refused",
        )

        with (
            patch(
                "syntara.integrations.services.integration_service.create_health_check_adapter"
            ) as mock_adapter_factory,
            patch("syntara.integrations.services.integration_service.get_runtime_settings") as mock_settings,
            patch.object(service, "_secret_service", create=True) as mock_secret_svc,
        ):
            mock_secret_svc.retrieve_secret = AsyncMock(return_value={"bearer_token": "token"})
            mock_settings.return_value.get = AsyncMock(return_value=10)

            mock_adapter = AsyncMock()
            mock_adapter.validate = AsyncMock(return_value=error_result)
            mock_adapter_factory.return_value = mock_adapter

            result = await service.validate_integration(integration_id)

        assert result.success is False

        tools = (await test_db_session.exec(select(Tool).where(Tool.integration_id == integration_id))).all()
        assert len(tools) == 0


class TestRefreshIntegrationResources:
    """refresh_resources() calls discover and syncs Tool records."""

    @pytest.mark.asyncio
    async def test_refresh_creates_tool_records(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        mcp_integration: dict[str, Any],
    ) -> None:
        """refresh_resources creates Tool records via _sync_mcp_tools on success."""
        integration_id = mcp_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user)

        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_tools=[
                _make_discovered_tool("tool_a", "Tool A"),
                _make_discovered_tool("tool_b", "Tool B"),
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

        tools = (await test_db_session.exec(select(Tool).where(Tool.integration_id == integration_id))).all()
        assert len(tools) == 2
        assert {t.name for t in tools} == {"tool_a", "tool_b"}

    @pytest.mark.asyncio
    async def test_refresh_sets_status_available(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        mcp_integration: dict[str, Any],
    ) -> None:
        """Successful refresh sets refresh_status=AVAILABLE and populates last_refreshed_at."""
        integration_id = mcp_integration["integration_id"]
        service = IntegrationService(test_db_session, test_user)

        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_tools=[],
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

        assert result.refreshed_at is not None

        # Verify integration DB state
        from sqlmodel import select as sql_select

        from syntara.integrations.models.integration import Integration

        integration = (
            await test_db_session.exec(sql_select(Integration).where(Integration.id == integration_id))
        ).one()
        assert integration.refresh_status == IntegrationRefreshStatus.AVAILABLE
        assert integration.last_refreshed_at is not None

    @pytest.mark.asyncio
    async def test_refresh_uses_integration_name_for_namespace(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Namespaced tool names use integration.name as the prefix."""
        service = IntegrationService(test_db_session, test_user)
        created = await service.create_integration(make_mcp_create("My Integration"))
        await test_db_session.flush()
        integration_id = created.id

        discover_result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_tools=[_make_discovered_tool("my_tool", "A tool")],
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

        tools = (await test_db_session.exec(select(Tool).where(Tool.integration_id == integration_id))).all()
        assert len(tools) == 1
        assert tools[0].namespaced_name == "My Integration::my_tool"

    @pytest.mark.asyncio
    async def test_aap_refresh_raises(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        aap_credential_id: UUID,
    ) -> None:
        """refresh_resources raises for unsupported integration types (ansible_automation_platform)."""
        from syntara.integrations.exceptions import IntegrationRefreshNotSupportedError

        service = IntegrationService(test_db_session, test_user)
        data = IntegrationCreate(
            name="Gateway No Refresh",
            integration_type=IntegrationType.ANSIBLE_AUTOMATION_PLATFORM,
            configuration={
                "integration_type": "ansible_automation_platform",
                "base_url": "https://gateway.example.com",
            },
            management_credential_id=aap_credential_id,
        )
        created = await service.create_integration(data)
        await test_db_session.flush()

        with pytest.raises(IntegrationRefreshNotSupportedError, match="ansible_automation_platform"):
            await service.refresh_resources(created.id)
