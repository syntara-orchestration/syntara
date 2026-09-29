"""Tests for execute_mcp_tool_activity and its integration-resolution helpers."""

from collections.abc import Generator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.tools import ToolException
from temporalio.exceptions import ApplicationError

from syntara.integrations.models.integration import IntegrationType
from syntara.integrations.models.integration_configuration import MCPServerConfigurationInput
from syntara.workflows.workflow_engine.activities import mcp_tool as mcp_tool_module
from syntara.workflows.workflow_engine.activities.mcp_tool import (
    _load_mcp_integration,
    _select_tool,
    execute_mcp_tool_activity,
)

MODULE = "syntara.workflows.workflow_engine.activities.mcp_tool"


@pytest.fixture(autouse=True)
def _mock_heartbeat() -> Generator[None, None, None]:
    """Auto-mock activity.heartbeat() so tests can run outside a Temporal worker."""
    with patch("temporalio.activity.heartbeat"):
        yield


def _config(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    base: dict[str, Any] = {
        "integration_id": str(uuid4()),
        "tool_name": "echo",
        "arguments": {"msg": "hello"},
    }
    base.update(overrides)
    return base


def _integration(
    *,
    integration_type: IntegrationType = IntegrationType.MCP_SERVER,
    enabled: bool = True,
    credential_id: Any = None,  # noqa: ANN401
    base_url: str = "https://mcp.example.com/mcp",
) -> MagicMock:
    integration = MagicMock()
    integration.integration_type = integration_type
    integration.enabled = enabled
    integration.name = "mcp-1"
    integration.management_credential_id = credential_id
    integration.configuration = MCPServerConfigurationInput(base_url=base_url)
    return integration


def _session(integration: Any) -> AsyncMock:  # noqa: ANN401
    session = AsyncMock()
    session.get.return_value = integration
    return session


def _session_factory(session: Any) -> Any:  # noqa: ANN401
    @asynccontextmanager
    async def factory() -> Any:  # noqa: ANN401
        yield session

    return factory


def _tool(name: str, return_value: Any = "ok") -> MagicMock:  # noqa: ANN401
    tool = MagicMock()
    tool.name = name
    tool.ainvoke = AsyncMock(return_value=return_value)
    return tool


@asynccontextmanager
async def _patched_provider(tools: list[Any]) -> Any:  # noqa: ANN401
    provider = MagicMock()
    provider.get_base_tools = AsyncMock(return_value=tools)
    provider.close = AsyncMock()
    with patch(f"{MODULE}.MCPProvider", return_value=provider) as factory:
        yield provider, factory


# ---------------------------------------------------------------------------
# _select_tool
# ---------------------------------------------------------------------------


class TestSelectTool:
    """Tool lookup by name."""

    def test_returns_matching_tool(self) -> None:
        wanted = _tool("echo")
        assert _select_tool([_tool("other"), wanted], "echo") is wanted

    def test_raises_non_retryable_when_missing(self) -> None:
        with pytest.raises(ApplicationError) as exc_info:
            _select_tool([_tool("other")], "echo")
        assert exc_info.value.non_retryable is True
        assert "echo" in str(exc_info.value)


# ---------------------------------------------------------------------------
# _load_mcp_integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLoadMCPIntegration:
    """Integration lookup and connection resolution."""

    async def test_returns_connection_for_valid_integration(self) -> None:
        session = _session(_integration())
        connection = await _load_mcp_integration(session, uuid4())
        assert connection.base_url == "https://mcp.example.com/mcp"
        assert connection.api_key is None
        assert connection.integration_name == "mcp-1"

    async def test_missing_integration_raises_non_retryable(self) -> None:
        session = _session(None)
        with pytest.raises(ApplicationError) as exc_info:
            await _load_mcp_integration(session, uuid4())
        assert exc_info.value.non_retryable is True
        assert "not found" in str(exc_info.value)

    async def test_wrong_integration_type_raises(self) -> None:
        session = _session(_integration(integration_type=IntegrationType.LLM_PROVIDER))
        with pytest.raises(ApplicationError) as exc_info:
            await _load_mcp_integration(session, uuid4())
        assert "expected 'mcp_server'" in str(exc_info.value)

    async def test_disabled_integration_raises(self) -> None:
        session = _session(_integration(enabled=False))
        with pytest.raises(ApplicationError) as exc_info:
            await _load_mcp_integration(session, uuid4())
        assert "disabled" in str(exc_info.value)

    async def test_resolves_bearer_token_when_credential_present(self) -> None:
        session = _session(_integration(credential_id=uuid4()))
        with (
            patch(f"{MODULE}.create_secret_service", return_value=MagicMock()),
            patch(f"{MODULE}.resolve_mcp_bearer_token", AsyncMock(return_value="tok123")),
        ):
            connection = await _load_mcp_integration(session, uuid4())
        assert connection.api_key == "tok123"

    async def test_credential_failure_raises_non_retryable(self) -> None:
        session = _session(_integration(credential_id=uuid4()))
        with (
            patch(f"{MODULE}.create_secret_service", return_value=MagicMock()),
            patch(f"{MODULE}.resolve_mcp_bearer_token", AsyncMock(side_effect=RuntimeError("boom"))),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await _load_mcp_integration(session, uuid4())
        assert exc_info.value.non_retryable is True
        assert "Failed to resolve credential" in str(exc_info.value)

    async def test_ssrf_rejection_raises_non_retryable(self) -> None:
        session = _session(_integration())
        with (
            patch(f"{MODULE}.validate_integration_configuration_no_ssrf", side_effect=ValueError("blocked")),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await _load_mcp_integration(session, uuid4())
        assert exc_info.value.non_retryable is True
        assert "SSRF" in str(exc_info.value)


# ---------------------------------------------------------------------------
# execute_mcp_tool_activity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestExecuteMCPToolActivity:
    """End-to-end activity behaviour with a mocked MCP client."""

    @pytest.fixture(autouse=True)
    def _patch_session_factory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mcp_tool_module, "_session_factory", _session_factory(_session(_integration())))

    async def test_returns_tool_result_as_node_output(self) -> None:
        config = _config()
        async with _patched_provider([_tool("echo", return_value="hello back")]) as (provider, _):
            result = await execute_mcp_tool_activity(config, None)
        output = result["output"]
        assert output["tool_name"] == "echo"
        assert output["integration_id"] == config["integration_id"]
        assert output["result"] == "hello back"
        assert output["is_error"] is False
        provider.close.assert_awaited_once()

    async def test_passes_resolved_arguments_to_the_tool(self) -> None:
        tool = _tool("echo")
        async with _patched_provider([tool]):
            await execute_mcp_tool_activity(_config(arguments={"msg": "resolved"}), None)
        tool.ainvoke.assert_awaited_once_with({"msg": "resolved"})

    async def test_applies_output_mapping(self) -> None:
        async with _patched_provider([_tool("echo", return_value={"n": 1})]):
            result = await execute_mcp_tool_activity(_config(), {"answer": "${result.result}"})
        assert result["output"] == {"answer": {"n": 1}}

    async def test_invalid_config_raises_non_retryable_validation_error(self) -> None:
        with pytest.raises(ApplicationError) as exc_info:
            await execute_mcp_tool_activity({"integration_id": str(uuid4())}, None)
        assert exc_info.value.type == "ValidationError"
        assert exc_info.value.non_retryable is True

    async def test_unknown_tool_raises_non_retryable(self) -> None:
        async with _patched_provider([_tool("other")]):
            with pytest.raises(ApplicationError) as exc_info:
                await execute_mcp_tool_activity(_config(), None)
        assert exc_info.value.non_retryable is True

    async def test_tool_error_raises_with_output_attached(self) -> None:
        tool = _tool("echo")
        tool.ainvoke = AsyncMock(side_effect=ToolException("tool blew up"))
        async with _patched_provider([tool]):
            with pytest.raises(ApplicationError) as exc_info:
                await execute_mcp_tool_activity(_config(), None)
        error = exc_info.value
        assert error.type == "MCPToolError"
        assert error.non_retryable is True
        output = error.details[0]["output"]
        assert output["is_error"] is True
        assert output["result"] == "tool blew up"
        assert output["tool_name"] == "echo"

    async def test_connection_error_is_retryable(self) -> None:
        provider = MagicMock()
        provider.get_base_tools = AsyncMock(side_effect=ConnectionError("no route"))
        provider.close = AsyncMock()
        with patch(f"{MODULE}.MCPProvider", return_value=provider):
            with pytest.raises(ApplicationError) as exc_info:
                await execute_mcp_tool_activity(_config(), None)
        assert exc_info.value.non_retryable is False
        assert exc_info.value.type == "ConnectionError"

    async def test_timeout_is_retryable(self) -> None:
        provider = MagicMock()
        provider.get_base_tools = AsyncMock(side_effect=TimeoutError())
        provider.close = AsyncMock()
        with patch(f"{MODULE}.MCPProvider", return_value=provider):
            with pytest.raises(ApplicationError) as exc_info:
                await execute_mcp_tool_activity(_config(), None)
        assert exc_info.value.non_retryable is False

    async def test_unexpected_error_is_non_retryable(self) -> None:
        tool = _tool("echo")
        tool.ainvoke = AsyncMock(side_effect=RuntimeError("weird"))
        async with _patched_provider([tool]):
            with pytest.raises(ApplicationError) as exc_info:
                await execute_mcp_tool_activity(_config(), None)
        assert exc_info.value.non_retryable is True

    async def test_template_integration_id_raises_configuration_error(self) -> None:
        with pytest.raises(ApplicationError) as exc_info:
            await execute_mcp_tool_activity(_config(integration_id="${trigger.integration_id}"), None)
        assert exc_info.value.type == "ConfigurationError"
        assert exc_info.value.non_retryable is True
