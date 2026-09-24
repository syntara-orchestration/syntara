"""Integration test executing the mcp_tool activity against a live MCP test server.

Starts an in-process ``ExampleMCPServer`` (the same FastMCP server image used by
the ``syntara-mcp`` container and the E2E stack), points a real ``mcp_server``
integration row at it, and runs ``execute_mcp_tool_activity`` end to end — no
MCP client mocking, so the langchain/MCP protocol path is genuinely exercised.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from syntara.integrations.models.integration import Integration, IntegrationScope, IntegrationType
from syntara.integrations.models.integration_configuration import MCPServerConfigurationInput
from syntara.workflows.workflow_engine.activities import mcp_tool as mcp_tool_module
from syntara.workflows.workflow_engine.activities.mcp_tool import execute_mcp_tool_activity

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator, Generator

    from orchestrator_test_sdk.app.mcp_servers import ExampleMCPServer
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User

pytestmark = [pytest.mark.integration, pytest.mark.mcp]


@pytest.fixture(autouse=True)
def _mock_heartbeat() -> Generator[None, None, None]:
    """Auto-mock activity.heartbeat() so the activity runs outside a Temporal worker."""
    with patch("temporalio.activity.heartbeat"):
        yield


@pytest.fixture
async def mcp_server() -> AsyncGenerator[ExampleMCPServer, None]:
    """Start an in-process MCP test server on an ephemeral port."""
    # Imported lazily: fastmcp installs a beartype import hook that breaks
    # Temporal sandbox validation for other tests collected in the same process.
    from orchestrator_test_sdk.app.mcp_servers import ExampleMCPServer

    server = ExampleMCPServer(host="127.0.0.1", port=0)
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


@pytest.fixture
def patched_session_factory(test_db_session: AsyncSession) -> Generator[None, None, None]:
    """Point the activity's module-level session factory at the test session."""

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        yield test_db_session

    with patch.object(mcp_tool_module, "_session_factory", factory):
        yield


async def _create_integration(session: AsyncSession, user: User, base_url: str) -> UUID:
    integration = Integration(
        name=f"mcp-live-{uuid4().hex[:8]}",
        integration_type=IntegrationType.MCP_SERVER,
        configuration=MCPServerConfigurationInput(base_url=base_url, allow_http=True),
        scope=IntegrationScope.GLOBAL,
        enabled=True,
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(integration)
    await session.flush()
    return integration.id


@pytest.mark.asyncio
@pytest.mark.usefixtures("patched_session_factory")
async def test_activity_calls_tool_on_live_mcp_server(
    test_db_session: AsyncSession,
    test_user: User,
    mcp_server: ExampleMCPServer,
) -> None:
    """The activity resolves the integration and returns the real tool result."""
    integration_id = await _create_integration(test_db_session, test_user, mcp_server.base_url)

    config: dict[str, Any] = {
        "integration_id": str(integration_id),
        "tool_name": "calculate_sum",
        "arguments": {"a": 2, "b": 3},
    }
    result = await execute_mcp_tool_activity(config, None)

    output = result["output"]
    assert output["tool_name"] == "calculate_sum"
    assert output["integration_id"] == str(integration_id)
    assert output["is_error"] is False
    assert "5" in str(output["result"])


@pytest.mark.asyncio
@pytest.mark.usefixtures("patched_session_factory")
async def test_activity_rejects_tool_missing_from_live_server(
    test_db_session: AsyncSession,
    test_user: User,
    mcp_server: ExampleMCPServer,
) -> None:
    """A tool name the server does not advertise fails non-retryably."""
    from temporalio.exceptions import ApplicationError

    integration_id = await _create_integration(test_db_session, test_user, mcp_server.base_url)

    config: dict[str, Any] = {
        "integration_id": str(integration_id),
        "tool_name": "no_such_tool",
        "arguments": {},
    }
    with pytest.raises(ApplicationError) as exc_info:
        await execute_mcp_tool_activity(config, None)

    assert exc_info.value.non_retryable is True
    assert "no_such_tool" in str(exc_info.value)
