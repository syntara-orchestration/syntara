"""Tool manager fixtures shared across unit and integration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest_asyncio

from syntara.tool_manager.models import Tool

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User
    from syntara.integrations.models.integration import Integration


@pytest_asyncio.fixture
async def test_tool(test_db_session: AsyncSession, test_mcp_integration: Integration, test_user: User) -> Tool:
    """Create a test Tool linked to an Integration."""
    unique_suffix = uuid4().hex[:8]
    tool = Tool(
        name=f"mock-tool-{unique_suffix}",
        integration_id=test_mcp_integration.id,
        namespaced_name=f"mock-{unique_suffix}::tool",
        created_by=test_user.id,
    )
    test_db_session.add(tool)
    await test_db_session.commit()
    return tool
