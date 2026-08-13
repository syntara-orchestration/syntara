"""Tool manager fixtures specific to unit tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest_asyncio

from syntara.tool_manager.lib.providers.factory import ProviderFactory
from syntara.tool_manager.services.tool_service import ToolService
from tests.unit.fixtures.mock_mcp_provider import MockMCPProvider

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User


@pytest_asyncio.fixture
async def test_provider_factory() -> ProviderFactory:
    """Create a ProviderFactory with MockMCPProvider registered for testing."""
    provider_factory = ProviderFactory()
    provider_factory.register_provider_type("mcp", MockMCPProvider)
    return provider_factory


@pytest_asyncio.fixture
async def test_tool_service(test_db_session: AsyncSession, test_user: User) -> ToolService:
    """Create a ToolService for testing."""
    return ToolService(test_db_session, test_user)
