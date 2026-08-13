"""Tool Manager HTTP Client for Agent Orchestrator integration."""

import types
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx
import structlog

from syntara.core.exceptions import SafeValueError
from syntara.core.tls.http_client import build_internal_http_client
from syntara.core.utils.retry import retry_with_backoff
from syntara.integrations.models.integration import IntegrationRead, IntegrationType
from syntara.tool_manager.models.tool import ToolStatus, ToolWithParameters

logger = structlog.stdlib.get_logger(__name__)


def _validate_url(url: str) -> None:
    """Validate URL format."""
    try:
        parsed = urlparse(url)
    except Exception as e:
        msg = "Invalid base URL"
        raise SafeValueError(msg) from e

    if not parsed.scheme or not parsed.netloc:
        msg = "Invalid base URL: must include scheme and host"
        raise SafeValueError(msg)


def _validate_timeout(timeout_val: float) -> None:
    """Validate timeout value."""
    if timeout_val <= 0:
        msg = "Timeout must be positive"
        raise SafeValueError(msg)


def _validate_limit(limit_val: int | None) -> None:
    """Validate limit value."""
    if limit_val is not None and limit_val <= 0:
        msg = "Limit must be positive"
        raise SafeValueError(msg)


def _validate_max_connections(max_conn: int) -> None:
    """Validate max_connections value."""
    if max_conn <= 0:
        msg = "max_connections must be positive"
        raise SafeValueError(msg)


def _validate_max_keepalive_connections(max_keepalive: int, max_conn: int) -> None:
    """Validate max_keepalive_connections value."""
    if max_keepalive < 0:
        msg = "max_keepalive_connections must be non-negative"
        raise SafeValueError(msg)
    if max_keepalive > max_conn:
        msg = "max_keepalive_connections cannot exceed max_connections"
        raise SafeValueError(msg)


class ToolManagerClient:
    """HTTP client for Tool Manager REST API integration.

    This client provides methods to discover all MCP server integrations,
    retrieve all tools, and report tool execution status back to
    the Tool Manager service.

    Attributes:
        base_url: Tool Manager API base URL
        timeout: Request timeout in seconds
        session: HTTP client session for connection pooling

    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        limit: int | None = None,
        max_connections: int = 10,
        max_keepalive_connections: int = 5,
    ) -> None:
        """Initialize Tool Manager client.

        Args:
            base_url: Tool Manager API base URL (e.g., "http://localhost:8000")
            timeout: Request timeout in seconds (default: 30.0)
            limit: Optional page size limit for API requests (default: None, uses server default)
            max_connections: Maximum number of connections to maintain (default: 10)
            max_keepalive_connections: Maximum number of keepalive connections (default: 5)

        Raises:
            ValueError: If base_url is invalid, timeout is negative, limit is invalid,
                       or connection parameters are invalid

        """
        # Validate inputs
        _validate_url(base_url)
        _validate_timeout(timeout)
        _validate_limit(limit)
        _validate_max_connections(max_connections)
        _validate_max_keepalive_connections(max_keepalive_connections, max_connections)

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.limit = limit
        self.max_connections = max_connections
        self.max_keepalive_connections = max_keepalive_connections

        self.session = build_internal_http_client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(
                max_connections=self.max_connections, max_keepalive_connections=self.max_keepalive_connections
            ),
            follow_redirects=True,
        )

    async def close(self) -> None:
        """Close the HTTP session and cleanup resources."""
        if hasattr(self, "session") and self.session:
            await self.session.aclose()

    async def __aenter__(self) -> "ToolManagerClient":
        """Support for async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Support for async context manager."""
        await self.close()

    @retry_with_backoff
    async def _get_mcp_integrations_page(self, params: dict[str, str]) -> dict[str, Any]:
        """Get a single page of mcp_server integrations with retry logic.

        Args:
            params: Query parameters for the API request

        Returns:
            JSON response data from the API

        Raises:
            httpx.HTTPStatusError: On API error responses
            httpx.TimeoutException: On request timeout
            httpx.ConnectError: On network connectivity issues

        """
        logger.debug("Fetching MCP integrations from Integrations API", params=params)
        response = await self.session.get("/integrations", params=params)
        response.raise_for_status()
        return dict(response.json())

    async def get_all_mcp_integrations(self) -> list[IntegrationRead]:
        """Retrieve all mcp_server integrations.

        Fetches all integrations of type mcp_server regardless of enabled status.
        Handles pagination automatically to return all results.

        Returns:
            List of all IntegrationRead objects for mcp_server integrations

        Raises:
            httpx.HTTPStatusError: On API error responses
            httpx.TimeoutException: On request timeout
            httpx.ConnectError: On network connectivity issues

        """
        integrations: list[IntegrationRead] = []
        cursor: str | None = None

        while True:
            # Build query parameters — filter to mcp_server type only
            params: dict[str, str] = {"integration_type": IntegrationType.MCP_SERVER.value}
            if cursor:
                params["cursor"] = cursor
            if self.limit is not None:
                params["limit"] = str(self.limit)

            # Make API request with retry logic
            data = await self._get_mcp_integrations_page(params)

            # Parse integrations from response
            for integration_data in data.get("resources", []):
                integration = IntegrationRead.model_validate(integration_data)
                integrations.append(integration)

            # Check for next page
            cursor = data.get("next")
            if not cursor:
                break

        logger.info("Retrieved total MCP integrations", integration_count=len(integrations))
        return integrations

    @retry_with_backoff
    async def _get_tools_page(self, params: dict[str, str]) -> dict[str, Any]:
        """Get a single page of tools with retry logic.

        Args:
            params: Query parameters for the API request

        Returns:
            JSON response data from the API

        Raises:
            httpx.HTTPStatusError: On API error responses
            httpx.TimeoutException: On request timeout
            httpx.ConnectError: On network connectivity issues

        """
        logger.debug("Fetching tools from Tool Manager API", params=params)
        response = await self.session.get("/tools", params=params)
        response.raise_for_status()
        return dict(response.json())

    async def get_all_tools(self) -> list[ToolWithParameters]:
        """Retrieve all tools from Tool Manager.

        Fetches all tools regardless of their enabled status or current status.
        Status filtering and enabled filtering is handled at the service layer.
        Handles pagination automatically to return all results.

        Returns:
            List of all ToolWithParameters objects

        Raises:
            httpx.HTTPStatusError: On API error responses
            httpx.TimeoutException: On request timeout
            httpx.ConnectError: On network connectivity issues

        """
        tools: list[ToolWithParameters] = []
        cursor: str | None = None

        while True:
            # Build query parameters
            params: dict[str, str] = {}
            if cursor:
                params["cursor"] = cursor
            if self.limit is not None:
                params["limit"] = str(self.limit)

            # Make API request with retry logic
            data = await self._get_tools_page(params)

            # Parse tools from response
            for tool_data in data.get("resources", []):
                tool = ToolWithParameters.model_validate(tool_data)
                tools.append(tool)

            # Check for next page
            cursor = data.get("next")
            if not cursor:
                break

        logger.info("Retrieved total tools", tool_count=len(tools))
        return tools

    @retry_with_backoff
    async def update_tool_status(self, tool_id: UUID, status: ToolStatus, refresh_error: str | None = None) -> None:
        """Report tool ``ERROR`` status and optional ``refresh_error`` to Tool Manager.

        Production callers use this after execution failures. Records ``status`` /
        ``refresh_error`` only; the ``enabled`` flag is administrator-owned and is
        never modified here.

        Args:
            tool_id: UUID of the tool to update
            status: New status for the tool
            refresh_error: Error message to set in refresh_error field (optional)

        Raises:
            ValueError: If tool_id is None
            httpx.HTTPStatusError: On API error responses (404, 409, etc.)
            httpx.TimeoutException: On request timeout
            httpx.ConnectError: On network connectivity issues

        """
        if not tool_id:
            msg = "Tool ID cannot be None"
            raise SafeValueError(msg)

        update_data: dict[str, str | None] = {"status": status.value, "refresh_error": refresh_error}

        logger.debug(
            "Updating tool status",
            tool_id=tool_id,
            status=status.value,
            refresh_error=refresh_error,
        )

        # Make API request
        response = await self.session.patch(f"/tools/{tool_id}", json=update_data)
        response.raise_for_status()

        logger.info("Updated tool status", tool_id=tool_id, status=status.value)
