"""Tool manager fixtures for integration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest_asyncio

from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import MCPServerConfiguration
from tests.integration.helpers.tool_manager import ToolFactory

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User


@pytest_asyncio.fixture
async def test_mcp_integration(test_db_session: AsyncSession, test_user: User) -> Integration:
    """Create a test MCP server Integration."""
    unique_suffix = uuid4().hex[:8]
    integration = Integration(
        name=f"mock-provider-{unique_suffix}",
        integration_type=IntegrationType.MCP_SERVER,
        configuration=MCPServerConfiguration(
            integration_type="mcp_server",
            base_url="http://localhost:8080",
        ),
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    test_db_session.add(integration)
    await test_db_session.commit()
    return integration


@pytest_asyncio.fixture
async def tool_factory(
    test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User
) -> ToolFactory:
    """Create a factory fixture for multiple test tools with configurable properties."""
    return ToolFactory(test_db_session, test_mcp_integration, test_user)
