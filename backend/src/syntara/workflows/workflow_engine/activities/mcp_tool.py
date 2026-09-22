"""MCP tool activity for v2 workflows.

Executes a single named tool on an ``mcp_server`` integration. The integration
record (base URL, TLS settings, management credential) is resolved from the
database at execution time, then the call is made through the same
:class:`~syntara.tool_manager.lib.providers.mcp.mcp_provider.MCPProvider`
used by integration discovery and the agentic node's tool manager — no
separate MCP protocol client.
"""

import asyncio
from typing import Any
from uuid import UUID

import structlog
from langchain_core.tools import BaseTool, ToolException
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.core.database.session import AsyncSessionLocal
from syntara.core.services.secret_service import create_secret_service
from syntara.integrations.lib.credential_resolver import resolve_mcp_bearer_token
from syntara.integrations.lib.url_validation import validate_integration_configuration_no_ssrf
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import MCPServerConfigurationInput
from syntara.tool_manager.lib.providers.mcp.mcp_provider import MCPProvider
from syntara.workflows.workflow_engine.constants import (
    DEFAULT_ACTIVITY_TIMEOUT_SECONDS,
    ENGINE_TIMEOUT_SECONDS_KEY,
)
from syntara.workflows.workflow_engine.models.workflow_definition import (
    MCP_TOOL_MAX_TIMEOUT_SECONDS,
    ActivityName,
    MCPToolExecutorParameters,
    MCPToolOutput,
)

from .common import HEARTBEAT_STOP_MONITOR

logger = structlog.stdlib.get_logger(__name__)

# Module-level session factory — defaults to production AsyncSessionLocal.
# Tests can override this to use a test database session factory.
_session_factory = AsyncSessionLocal

_ERROR_TYPE_CONFIG = "ConfigurationError"
_ERROR_TYPE_TOOL = "MCPToolError"


class _MCPConnection:
    """Resolved connection parameters for one mcp_server integration."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        integration_name: str,
        *,
        insecure_skip_tls_verify: bool,
        ca_certificate: str | None,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.integration_name = integration_name
        self.insecure_skip_tls_verify = insecure_skip_tls_verify
        self.ca_certificate = ca_certificate


async def _load_mcp_integration(session: AsyncSession, integration_id: UUID) -> _MCPConnection:
    """Load an mcp_server integration and resolve its connection parameters.

    Raises:
        ApplicationError: Non-retryable when the integration is missing, is not
            an ``mcp_server``, is disabled, has an invalid configuration, or its
            base URL is rejected by the integration SSRF policy.

    """
    integration = await session.get(Integration, integration_id)
    if not integration:
        msg = f"Integration '{integration_id}' not found"
        raise ApplicationError(msg, type=_ERROR_TYPE_CONFIG, non_retryable=True)

    if integration.integration_type != IntegrationType.MCP_SERVER:
        msg = f"Integration '{integration_id}' is type '{integration.integration_type}', expected 'mcp_server'"
        raise ApplicationError(msg, type=_ERROR_TYPE_CONFIG, non_retryable=True)

    if not integration.enabled:
        msg = f"Integration '{integration.name}' is disabled"
        raise ApplicationError(msg, type=_ERROR_TYPE_CONFIG, non_retryable=True)

    config = integration.configuration
    if not isinstance(config, MCPServerConfigurationInput):
        msg = f"Integration '{integration_id}' has invalid configuration type"
        raise ApplicationError(msg, type=_ERROR_TYPE_CONFIG, non_retryable=True)

    # Re-run the integration SSRF policy at call time: the stored base_url may
    # have been re-pointed at a private/metadata address since write time.
    try:
        validate_integration_configuration_no_ssrf(config)
    except ValueError as exc:
        msg = f"Integration '{integration_id}' base_url is not permitted by SSRF policy"
        raise ApplicationError(msg, type=_ERROR_TYPE_CONFIG, non_retryable=True) from exc

    api_key: str | None = None
    if integration.management_credential_id:
        secret_service = create_secret_service(session)
        try:
            api_key = await resolve_mcp_bearer_token(session, secret_service, integration_id)
        except Exception as exc:
            msg = f"Failed to resolve credential for integration '{integration.name}': {type(exc).__name__}"
            raise ApplicationError(msg, type=_ERROR_TYPE_CONFIG, non_retryable=True) from exc

    return _MCPConnection(
        base_url=config.base_url,
        api_key=api_key,
        integration_name=integration.name,
        insecure_skip_tls_verify=config.insecure_skip_tls_verify,
        ca_certificate=config.ca_certificate,
    )


async def _resolve_connection(integration_id: UUID) -> _MCPConnection:
    """Open a session and resolve the integration's connection parameters."""
    try:
        async with _session_factory() as session:
            return await _load_mcp_integration(session, integration_id)
    except ApplicationError:
        raise
    except OperationalError as exc:
        msg = f"Transient database error during MCP integration resolution: {type(exc).__name__}"
        raise ApplicationError(msg, non_retryable=False) from exc
    except Exception as exc:
        msg = f"Database error during MCP integration resolution: {type(exc).__name__}"
        raise ApplicationError(msg, non_retryable=True) from exc


def _select_tool(tools: list[BaseTool], tool_name: str) -> BaseTool:
    """Return the tool with the given name, or raise a non-retryable error."""
    for tool in tools:
        if tool.name == tool_name:
            return tool
    available = sorted(tool.name for tool in tools)
    msg = f"Tool '{tool_name}' is not available on this MCP server. Available tools: {available}"
    raise ApplicationError(msg, type=_ERROR_TYPE_CONFIG, non_retryable=True)


async def _invoke_tool(
    connection: _MCPConnection,
    tool_name: str,
    arguments: dict[str, Any],
    timeout_seconds: int,
) -> Any:  # noqa: ANN401
    """Connect to the MCP server and invoke ``tool_name`` with ``arguments``.

    The whole round trip (session setup, tool listing, tool call) shares one
    deadline so the activity always finishes before Temporal cancels the attempt.
    """
    provider = MCPProvider(
        base_url=connection.base_url,
        api_key=connection.api_key,
        integration_name=connection.integration_name,
        insecure_skip_tls_verify=connection.insecure_skip_tls_verify,
        ca_certificate=connection.ca_certificate,
    )
    try:
        async with asyncio.timeout(timeout_seconds):
            tools = await provider.get_base_tools()
            tool = _select_tool(tools, tool_name)
            return await tool.ainvoke(arguments)
    finally:
        await provider.close()


@activity.defn(name=ActivityName.MCP_TOOL)
async def execute_mcp_tool_activity(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
) -> dict[str, Any]:
    """Execute an MCP tool node for v2 workflows.

    Args:
        input_config: Resolved node configuration (templates already resolved).
        output_config: Output mapping configuration (field_name -> template expression).
            None = return full result, {} = suppress all, {...} = extract specific fields.

    Returns:
        ``{"output": {"tool_name": ..., "integration_id": ..., "result": ..., "is_error": False}}``

    Raises:
        ApplicationError: On configuration problems (non-retryable), tool errors
            reported by the MCP server (non-retryable, with the output attached),
            or transport failures (retryable).

    """
    activity.heartbeat({HEARTBEAT_STOP_MONITOR: True})

    try:
        config = MCPToolExecutorParameters.model_validate(input_config)
    except ValidationError as exc:
        logger.warning("MCP tool activity config validation failed", error_count=exc.error_count())
        fields = [str(e["loc"]) for e in exc.errors()]
        msg = f"Invalid configuration: {exc.error_count()} error(s) in fields {fields}"
        raise ApplicationError(msg, type="ValidationError", non_retryable=True) from None

    try:
        integration_id = UUID(config.integration_id)
    except ValueError:
        msg = f"integration_id '{config.integration_id}' is not a valid UUID"
        raise ApplicationError(msg, type=_ERROR_TYPE_CONFIG, non_retryable=True) from None

    engine_timeout = int(input_config.get(ENGINE_TIMEOUT_SECONDS_KEY, DEFAULT_ACTIVITY_TIMEOUT_SECONDS))
    timeout_seconds = min(config.timeout_seconds or engine_timeout, MCP_TOOL_MAX_TIMEOUT_SECONDS)

    connection = await _resolve_connection(integration_id)

    def build_output(result: Any, *, is_error: bool) -> dict[str, Any]:  # noqa: ANN401
        output = MCPToolOutput(
            tool_name=config.tool_name,
            integration_id=str(integration_id),
            result=result,
            is_error=is_error,
        )
        return output.dump(output_config)

    try:
        result = await _invoke_tool(connection, config.tool_name, config.arguments, timeout_seconds)
    except ApplicationError:
        raise
    except ToolException as exc:
        msg = f"MCP tool '{config.tool_name}' returned an error"
        logger.warning("MCP tool returned an error", tool_name=config.tool_name)
        raise ApplicationError(
            msg,
            {"output": build_output(str(exc), is_error=True)},
            type=_ERROR_TYPE_TOOL,
            non_retryable=True,
        ) from None
    except (TimeoutError, ConnectionError) as exc:
        msg = f"MCP tool call failed: {type(exc).__name__}"
        logger.warning("MCP tool call transport failure", tool_name=config.tool_name, error_type=type(exc).__name__)
        raise ApplicationError(msg, type=type(exc).__name__, non_retryable=False) from None
    except Exception as exc:  # noqa: BLE001
        msg = f"MCP tool call failed: {type(exc).__name__}"
        logger.warning("MCP tool call failed", tool_name=config.tool_name, error_type=type(exc).__name__)
        raise ApplicationError(msg, type=type(exc).__name__, non_retryable=True) from None

    logger.info(
        "MCP tool executed",
        tool_name=config.tool_name,
        integration_id=str(integration_id),
    )
    return {"output": build_output(result, is_error=False)}
