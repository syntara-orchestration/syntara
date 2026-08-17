"""Tests for the MCP server adapter — validate() and discover() methods.

validate() uses the MCP SDK's ClientSession with streamable-http transport for
spec-compliant JSON-RPC 2.0 ping with session handling and response parsing.
"""

from __future__ import annotations

import ssl
from typing import Any, Literal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import structlog
from httpx import HTTPStatusError, Response
from httpx_sse import SSEError
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from syntara.integrations.adapters.mcp_server import MCPServerAdapter
from syntara.integrations.adapters.protocol import (
    HealthCheckErrorType,
    IntegrationAdapter,
)
from syntara.integrations.models.integration_configuration import MCPServerConfiguration


@pytest.fixture
def mcp_config() -> MCPServerConfiguration:
    """Create a test MCP server configuration."""
    return MCPServerConfiguration(base_url="http://localhost:8080/mcp", allow_http=True)


def _mock_mcp_provider(side_effect: Exception | None = None, tools: list[Any] | None = None) -> MagicMock:
    """Create a mock MCPProvider for use in discover() tests."""
    provider = MagicMock()
    provider.close = AsyncMock()
    if side_effect:
        provider.refresh_tools = AsyncMock(side_effect=side_effect)
    else:
        provider.refresh_tools = AsyncMock(return_value=tools or [])
    return provider


def _mock_http_error(status_code: int) -> HTTPStatusError:
    """Create a mock HTTPStatusError with the given status code."""
    response = Response(status_code=status_code)
    return HTTPStatusError(
        message=f"HTTP {status_code}",
        request=httpx.Request("GET", "http://localhost:8080"),
        response=response,
    )


class MockMCPSDK:
    """Context manager that mocks MCP SDK components for validate() tests.

    Usage:
        async with MockMCPSDK() as (mock_streamable_client, mock_session):
            result = await adapter.validate(...)

        # Or with error injection:
        async with MockMCPSDK(init_error=TimeoutError("timeout")) as (mock_streamable_client, mock_session):
            result = await adapter.validate(...)
    """

    def __init__(self, init_error: Exception | None = None) -> None:
        """Initialize mock SDK.

        Args:
            init_error: Optional exception to raise from session.initialize()

        """
        self.init_error = init_error
        self.mock_streamable_client_patch: Any = None
        self.mock_client_session_patch: Any = None
        self.mock_streamable_client: MagicMock | None = None
        self.mock_session: AsyncMock | None = None

    def __enter__(self) -> tuple[MagicMock, AsyncMock]:
        """Set up SDK mocks."""
        # Create mock session
        self.mock_session = AsyncMock()
        if self.init_error:
            self.mock_session.initialize = AsyncMock(side_effect=self.init_error)
        else:
            self.mock_session.initialize = AsyncMock()
        self.mock_session.send_ping = AsyncMock()
        self.mock_session.__aenter__ = AsyncMock(return_value=self.mock_session)
        self.mock_session.__aexit__ = AsyncMock(return_value=None)

        # Create mock streams (read, write, get_session_id) for streamable_http_client
        mock_streams = (AsyncMock(), AsyncMock(), MagicMock())

        # Start patches
        self.mock_streamable_client_patch = patch("syntara.integrations.adapters.mcp_server.streamable_http_client")
        self.mock_client_session_patch = patch("syntara.integrations.adapters.mcp_server.ClientSession")

        self.mock_streamable_client = self.mock_streamable_client_patch.__enter__()
        mock_client_session_cls = self.mock_client_session_patch.__enter__()

        self.mock_streamable_client.return_value.__aenter__ = AsyncMock(return_value=mock_streams)
        self.mock_streamable_client.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client_session_cls.return_value = self.mock_session

        return (self.mock_streamable_client, self.mock_session)

    def __exit__(self, exc_type, exc_val, exc_tb) -> Literal[False]:
        """Clean up patches."""
        if self.mock_client_session_patch:
            self.mock_client_session_patch.__exit__(exc_type, exc_val, exc_tb)
        if self.mock_streamable_client_patch:
            self.mock_streamable_client_patch.__exit__(exc_type, exc_val, exc_tb)
        return False


class TestMCPServerAdapterProtocol:
    """Tests that MCPServerAdapter satisfies the adapter Protocol."""

    def test_is_instance_of_protocol(self, mcp_config: MCPServerConfiguration) -> None:
        """Verify MCPServerAdapter implements IntegrationAdapter."""
        adapter = MCPServerAdapter(mcp_config)
        assert isinstance(adapter, IntegrationAdapter)


class TestMCPServerValidate:
    """Tests for MCPServerAdapter.validate() using MCP SDK."""

    @pytest.mark.asyncio
    async def test_validate_success(self, mcp_config: MCPServerConfiguration) -> None:
        """validate() returns success when SDK ping succeeds."""
        adapter = MCPServerAdapter(mcp_config)

        with MockMCPSDK() as (_mock_sse_client, mock_session):
            result = await adapter.validate(resolved_credential={}, timeout_seconds=10)

        assert result.success is True
        assert result.error is None
        assert result.error_type is None
        mock_session.initialize.assert_awaited_once()
        mock_session.send_ping.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_validate_with_api_key(self, mcp_config: MCPServerConfiguration) -> None:
        """validate() includes Authorization header when API key is provided."""
        adapter = MCPServerAdapter(mcp_config)

        with (
            patch("httpx.AsyncClient") as mock_http_client_cls,
            MockMCPSDK() as (_mock_streamable_client, _mock_session),
        ):
            # Mock httpx.AsyncClient to capture headers
            mock_http_client = AsyncMock()
            mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
            mock_http_client.__aexit__ = AsyncMock(return_value=None)
            mock_http_client_cls.return_value = mock_http_client

            result = await adapter.validate(resolved_credential={"bearer_token": "test-key-123"}, timeout_seconds=10)

        assert result.success is True
        # Verify httpx.AsyncClient was created with Authorization header
        call_kwargs = mock_http_client_cls.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer test-key-123"

    @pytest.mark.asyncio
    async def test_validate_timeout(self, mcp_config: MCPServerConfiguration) -> None:
        """validate() returns timeout error when SDK operations timeout."""
        adapter = MCPServerAdapter(mcp_config)

        with MockMCPSDK(init_error=TimeoutError("Connection timeout")) as (_mock_sse_client, _mock_session):
            result = await adapter.validate(resolved_credential={}, timeout_seconds=5)

        assert result.success is False
        assert "timed out after 5s" in (result.error or "")
        assert result.error_type == HealthCheckErrorType.TIMEOUT

    @pytest.mark.asyncio
    async def test_validate_http_error(self, mcp_config: MCPServerConfiguration) -> None:
        """validate() returns HTTP error when SDK raises HTTPStatusError."""
        adapter = MCPServerAdapter(mcp_config)

        with MockMCPSDK(init_error=_mock_http_error(500)) as (_mock_sse_client, _mock_session):
            result = await adapter.validate(resolved_credential={}, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR

    @pytest.mark.asyncio
    async def test_validate_ssl_error(self, mcp_config: MCPServerConfiguration) -> None:
        """validate() returns SSL error when SDK raises SSL exception."""
        adapter = MCPServerAdapter(mcp_config)

        with MockMCPSDK(init_error=ssl.SSLError("Certificate verification failed")) as (
            _mock_sse_client,
            _mock_session,
        ):
            result = await adapter.validate(resolved_credential={}, timeout_seconds=10)

        assert result.success is False
        assert result.error == "SSL/TLS certificate verification failed"
        assert result.error_type == HealthCheckErrorType.SSL_ERROR

    @pytest.mark.asyncio
    async def test_validate_connection_error(self, mcp_config: MCPServerConfiguration) -> None:
        """validate() returns connection error when SDK cannot connect."""
        adapter = MCPServerAdapter(mcp_config)

        with MockMCPSDK(init_error=httpx.ConnectError("Connection refused")) as (_mock_sse_client, _mock_session):
            result = await adapter.validate(resolved_credential={}, timeout_seconds=10)

        assert result.success is False
        assert result.error == "Unable to connect to the service"
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR

    @pytest.mark.asyncio
    async def test_validate_unexpected_error(self, mcp_config: MCPServerConfiguration) -> None:
        """validate() handles unexpected errors gracefully."""
        adapter = MCPServerAdapter(mcp_config)

        with MockMCPSDK(init_error=RuntimeError("Something went wrong")) as (_mock_sse_client, _mock_session):
            result = await adapter.validate(resolved_credential={}, timeout_seconds=10)

        assert result.success is False
        assert result.error == "Validation failed unexpectedly"
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR

    @pytest.mark.asyncio
    async def test_validate_http_405_method_not_allowed(self, mcp_config: MCPServerConfiguration) -> None:
        """validate() returns descriptive error for HTTP 405 (method not allowed)."""
        adapter = MCPServerAdapter(mcp_config)

        with MockMCPSDK(init_error=_mock_http_error(405)) as (_mock_sse_client, _mock_session):
            result = await adapter.validate(resolved_credential={}, timeout_seconds=10)

        assert result.success is False
        assert result.error == "Method not allowed: HTTP 405"
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR

    @pytest.mark.asyncio
    async def test_validate_http_404_not_found(self, mcp_config: MCPServerConfiguration) -> None:
        """validate() returns descriptive error for HTTP 404 (endpoint does not exist)."""
        adapter = MCPServerAdapter(mcp_config)

        with MockMCPSDK(init_error=_mock_http_error(404)) as (_mock_sse_client, _mock_session):
            result = await adapter.validate(resolved_credential={}, timeout_seconds=10)

        assert result.success is False
        assert result.error == "Endpoint not found: HTTP 404"
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR

    @pytest.mark.asyncio
    async def test_validate_mcp_error_session_terminated(self, mcp_config: MCPServerConfiguration) -> None:
        """validate() handles McpError when server returns non-MCP content (e.g., HTML 404 page)."""
        adapter = MCPServerAdapter(mcp_config)

        # This simulates what happens when google.com/mcp returns HTML instead of MCP protocol
        mcp_error = McpError(ErrorData(code=-1, message="Session terminated"))
        with MockMCPSDK(init_error=mcp_error) as (_mock_sse_client, _mock_session):
            result = await adapter.validate(resolved_credential={}, timeout_seconds=10)

        assert result.success is False
        assert result.error == "Not an MCP endpoint (invalid response format)"
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR

    @pytest.mark.asyncio
    async def test_validate_does_not_return_discovery_fields(self, mcp_config: MCPServerConfiguration) -> None:
        """validate() returns ValidateResult without discovery fields."""
        adapter = MCPServerAdapter(mcp_config)

        with MockMCPSDK() as (_mock_sse_client, _mock_session):
            result = await adapter.validate(resolved_credential={}, timeout_seconds=10)

        assert not hasattr(result, "discovered_tools")
        assert not hasattr(result, "tools_refreshed_count")

    @pytest.mark.asyncio
    async def test_validate_http_401_auth_failure(self, mcp_config: MCPServerConfiguration) -> None:
        """validate() returns AUTH_FAILURE error type for HTTP 401."""
        adapter = MCPServerAdapter(mcp_config)

        with MockMCPSDK(init_error=_mock_http_error(401)) as (_mock_sse_client, _mock_session):
            result = await adapter.validate(resolved_credential={}, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE
        assert "Authentication failed: HTTP 401" in (result.error or "")

    @pytest.mark.asyncio
    async def test_validate_http_403_auth_failure(self, mcp_config: MCPServerConfiguration) -> None:
        """validate() returns AUTH_FAILURE error type for HTTP 403."""
        adapter = MCPServerAdapter(mcp_config)

        with MockMCPSDK(init_error=_mock_http_error(403)) as (_mock_sse_client, _mock_session):
            result = await adapter.validate(resolved_credential={}, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE
        assert "Authentication failed: HTTP 403" in (result.error or "")

    @pytest.mark.asyncio
    async def test_validate_http_429_rate_limit(self, mcp_config: MCPServerConfiguration) -> None:
        """validate() returns RATE_LIMIT error type for HTTP 429."""
        adapter = MCPServerAdapter(mcp_config)

        with MockMCPSDK(init_error=_mock_http_error(429)) as (_mock_sse_client, _mock_session):
            result = await adapter.validate(resolved_credential={}, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.RATE_LIMIT
        assert "Rate limit exceeded: HTTP 429" in (result.error or "")

    @pytest.mark.asyncio
    async def test_validate_httpx_timeout_exception(self, mcp_config: MCPServerConfiguration) -> None:
        """validate() handles httpx.TimeoutException distinct from stdlib TimeoutError."""
        adapter = MCPServerAdapter(mcp_config)

        with MockMCPSDK(init_error=httpx.TimeoutException("timeout")) as (_mock_sse_client, _mock_session):
            result = await adapter.validate(resolved_credential={}, timeout_seconds=5)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.TIMEOUT
        assert "timed out after 5s" in (result.error or "")

    @pytest.mark.asyncio
    async def test_validate_sse_error(self, mcp_config: MCPServerConfiguration) -> None:
        """validate() handles SSEError when server returns non-SSE content."""
        adapter = MCPServerAdapter(mcp_config)

        with MockMCPSDK(init_error=SSEError("Invalid content-type")) as (_mock_sse_client, _mock_session):
            result = await adapter.validate(resolved_credential={}, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR
        assert "Not an MCP endpoint (invalid response format)" in (result.error or "")

    @pytest.mark.asyncio
    async def test_validate_http_protocol_error(self, mcp_config: MCPServerConfiguration) -> None:
        """validate() handles httpx.HTTPError catch-all (e.g., RemoteProtocolError)."""
        adapter = MCPServerAdapter(mcp_config)

        with MockMCPSDK(init_error=httpx.RemoteProtocolError("invalid HTTP response")) as (
            _mock_sse_client,
            _mock_session,
        ):
            result = await adapter.validate(resolved_credential={}, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR
        assert "Not an MCP endpoint (HTTP protocol error)" in (result.error or "")

    @pytest.mark.asyncio
    async def test_validate_blocks_cloud_metadata_endpoint(self) -> None:
        """validate() blocks requests to cloud metadata endpoints (SSRF prevention)."""
        # Cloud metadata endpoint should be blocked even though it's in the 169.254.x.x range
        config = MCPServerConfiguration(base_url="http://169.254.169.254/latest/meta-data", allow_http=True)
        adapter = MCPServerAdapter(config)

        result = await adapter.validate(resolved_credential={}, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR
        assert result.error == "Unable to connect to the service"


class TestMCPServerDiscoverSuccess:
    """Tests for successful MCPServerAdapter.discover() calls."""

    @pytest.mark.asyncio
    async def test_returns_discovered_tools(self, mcp_config: MCPServerConfiguration) -> None:
        """Successful discover returns tool names and descriptions."""
        from syntara.tool_manager.models.tool import Tool

        mock_tool = MagicMock(spec=Tool)
        mock_tool.name = "search"
        mock_tool.description = "Search the web"
        mock_tool.parameters = []

        adapter = MCPServerAdapter(mcp_config)

        with patch(
            "syntara.integrations.adapters.mcp_server.MCPProvider",
        ) as mock_provider_cls:
            mock_provider_cls.return_value = _mock_mcp_provider(tools=[mock_tool])

            result = await adapter.discover(
                resolved_credential={"bearer_token": "test-key"},
                timeout_seconds=10,
            )

        assert result.success is True
        assert result.discovered_tools is not None
        assert len(result.discovered_tools) == 1
        assert result.discovered_tools[0].name == "search"
        assert result.discovered_tools[0].description == "Search the web"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_empty_tools_list(self, mcp_config: MCPServerConfiguration) -> None:
        """MCP server with no tools returns success with empty list."""
        adapter = MCPServerAdapter(mcp_config)

        with patch(
            "syntara.integrations.adapters.mcp_server.MCPProvider",
        ) as mock_provider_cls:
            mock_provider_cls.return_value = _mock_mcp_provider(tools=[])

            result = await adapter.discover(
                resolved_credential={"bearer_token": "test"},
                timeout_seconds=10,
            )

        assert result.success is True
        assert result.discovered_tools == []


class TestMCPServerDiscoverErrors:
    """Tests for MCPServerAdapter.discover() error classification."""

    @pytest.mark.asyncio
    async def test_timeout_error(self, mcp_config: MCPServerConfiguration) -> None:
        """Timeout returns TIMEOUT error type with sanitized message."""
        adapter = MCPServerAdapter(mcp_config)

        with patch(
            "syntara.integrations.adapters.mcp_server.MCPProvider",
        ) as mock_provider_cls:
            mock_provider = _mock_mcp_provider(side_effect=TimeoutError("internal details"))
            mock_provider_cls.return_value = mock_provider

            result = await adapter.discover(
                resolved_credential={"bearer_token": "test"},
                timeout_seconds=5,
            )

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.TIMEOUT
        assert result.error == "Connection timed out after 5s"
        mock_provider.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_error(self, mcp_config: MCPServerConfiguration) -> None:
        """Connection error returns CONNECTION_ERROR with sanitized message."""
        adapter = MCPServerAdapter(mcp_config)

        with patch(
            "syntara.integrations.adapters.mcp_server.MCPProvider",
        ) as mock_provider_cls:
            mock_provider = _mock_mcp_provider(side_effect=ConnectionError("Connection refused"))
            mock_provider_cls.return_value = mock_provider

            result = await adapter.discover(
                resolved_credential={"bearer_token": "test"},
                timeout_seconds=10,
            )

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR
        assert result.error == "Unable to connect to service"
        mock_provider.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_http_401_classified_as_auth_failure(self, mcp_config: MCPServerConfiguration) -> None:
        """HTTP 401 returns AUTH_FAILURE error type."""
        adapter = MCPServerAdapter(mcp_config)

        with patch(
            "syntara.integrations.adapters.mcp_server.MCPProvider",
        ) as mock_provider_cls:
            mock_provider_cls.return_value = _mock_mcp_provider(side_effect=_mock_http_error(401))

            result = await adapter.discover(
                resolved_credential={"bearer_token": "bad-token"},
                timeout_seconds=10,
            )

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE
        assert "401" in (result.error or "")

    @pytest.mark.asyncio
    async def test_http_403_classified_as_auth_failure(self, mcp_config: MCPServerConfiguration) -> None:
        """HTTP 403 returns AUTH_FAILURE error type."""
        adapter = MCPServerAdapter(mcp_config)

        with patch(
            "syntara.integrations.adapters.mcp_server.MCPProvider",
        ) as mock_provider_cls:
            mock_provider_cls.return_value = _mock_mcp_provider(side_effect=_mock_http_error(403))

            result = await adapter.discover(
                resolved_credential={"bearer_token": "test"},
                timeout_seconds=10,
            )

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE

    @pytest.mark.asyncio
    async def test_http_500_classified_as_connection_error(self, mcp_config: MCPServerConfiguration) -> None:
        """HTTP 500 returns CONNECTION_ERROR, not AUTH_FAILURE."""
        adapter = MCPServerAdapter(mcp_config)

        with patch(
            "syntara.integrations.adapters.mcp_server.MCPProvider",
        ) as mock_provider_cls:
            mock_provider_cls.return_value = _mock_mcp_provider(side_effect=_mock_http_error(500))

            result = await adapter.discover(
                resolved_credential={"bearer_token": "test"},
                timeout_seconds=10,
            )

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR

    @pytest.mark.asyncio
    async def test_ssl_error(self, mcp_config: MCPServerConfiguration) -> None:
        """SSL error returns SSL_ERROR with sanitized message."""
        adapter = MCPServerAdapter(mcp_config)

        with patch(
            "syntara.integrations.adapters.mcp_server.MCPProvider",
        ) as mock_provider_cls:
            mock_provider = _mock_mcp_provider(
                side_effect=ssl.SSLCertVerificationError("certificate verify failed"),
            )
            mock_provider_cls.return_value = mock_provider

            result = await adapter.discover(
                resolved_credential={"bearer_token": "test"},
                timeout_seconds=10,
            )

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.SSL_ERROR
        assert result.error == "SSL/TLS verification failed"
        mock_provider.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_unexpected_exception_logged(
        self,
        mcp_config: MCPServerConfiguration,
    ) -> None:
        """Unexpected exceptions are logged and return sanitized message."""
        adapter = MCPServerAdapter(mcp_config)

        with (
            patch(
                "syntara.integrations.adapters.mcp_server.MCPProvider",
            ) as mock_provider_cls,
            structlog.testing.capture_logs() as captured,
        ):
            mock_provider = _mock_mcp_provider(side_effect=RuntimeError("weird internal error"))
            mock_provider_cls.return_value = mock_provider

            result = await adapter.discover(
                resolved_credential={"bearer_token": "test"},
                timeout_seconds=10,
            )

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR
        assert result.error == "Discovery failed unexpectedly"
        assert any("Unexpected error" in entry.get("event", "") for entry in captured)


class TestErrorMessageSanitization:
    """Tests that error messages don't leak sensitive information."""

    @pytest.mark.asyncio
    async def test_connection_error_does_not_leak_details(self, mcp_config: MCPServerConfiguration) -> None:
        """Connection error messages don't contain raw exception text."""
        adapter = MCPServerAdapter(mcp_config)

        with patch(
            "syntara.integrations.adapters.mcp_server.MCPProvider",
        ) as mock_provider_cls:
            mock_provider_cls.return_value = _mock_mcp_provider(
                side_effect=ConnectionError("connect to 10.0.0.5:8765 failed: Connection refused"),
            )

            result = await adapter.discover(
                resolved_credential={"bearer_token": "SECRET-TOKEN-12345"},
                timeout_seconds=10,
            )

        assert "10.0.0.5" not in (result.error or "")
        assert "SECRET-TOKEN-12345" not in (result.error or "")

    @pytest.mark.asyncio
    async def test_ssl_error_does_not_leak_cert_details(self, mcp_config: MCPServerConfiguration) -> None:
        """SSL error messages don't contain certificate subject names."""
        adapter = MCPServerAdapter(mcp_config)

        with patch(
            "syntara.integrations.adapters.mcp_server.MCPProvider",
        ) as mock_provider_cls:
            mock_provider_cls.return_value = _mock_mcp_provider(
                side_effect=ssl.SSLCertVerificationError("certificate verify failed: CN=internal.corp.example.com"),
            )

            result = await adapter.discover(
                resolved_credential={"bearer_token": "SECRET-TOKEN-12345"},
                timeout_seconds=10,
            )

        assert "internal.corp.example.com" not in (result.error or "")
        assert "SECRET-TOKEN-12345" not in (result.error or "")

    @pytest.mark.asyncio
    async def test_unexpected_error_does_not_leak_details(self, mcp_config: MCPServerConfiguration) -> None:
        """Unexpected error messages don't contain internal details."""
        adapter = MCPServerAdapter(mcp_config)

        with patch(
            "syntara.integrations.adapters.mcp_server.MCPProvider",
        ) as mock_provider_cls:
            mock_provider_cls.return_value = _mock_mcp_provider(
                side_effect=RuntimeError("KeyError at /home/user/.secrets/key.pem"),
            )

            result = await adapter.discover(
                resolved_credential={"bearer_token": "SECRET-TOKEN-12345"},
                timeout_seconds=10,
            )

        assert "/home/user" not in (result.error or "")
        assert "SECRET-TOKEN-12345" not in (result.error or "")

    @pytest.mark.asyncio
    async def test_credentials_not_in_logs(
        self,
        mcp_config: MCPServerConfiguration,
    ) -> None:
        """Credential values do not appear in log output."""
        adapter = MCPServerAdapter(mcp_config)
        secret = "SUPER-SECRET-KEY-999"  # noqa: S105

        with (
            patch(
                "syntara.integrations.adapters.mcp_server.MCPProvider",
            ) as mock_provider_cls,
            structlog.testing.capture_logs() as captured,
        ):
            mock_provider_cls.return_value = _mock_mcp_provider(side_effect=ConnectionError("refused"))

            await adapter.discover(
                resolved_credential={"bearer_token": secret},
                timeout_seconds=10,
            )

        # Check that the secret doesn't appear in any log entry
        log_text = " ".join(str(entry) for entry in captured)
        assert secret not in log_text
