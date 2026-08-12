"""MCP server adapter implementing validate() and discover().

validate(): Run a spec-compliant MCP ping against the server using streamable-http transport.

discover(): Connects to the MCP server via MCPProvider.refresh_tools() and
  converts the full Tool objects (including parameters) into DiscoverResult.
  This reuses the same code path as _sync_mcp_tools() to avoid two separate
  connections.
"""

from __future__ import annotations

import asyncio
import ssl
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from syntara.tool_manager.models.tool import ToolParameter

import httpx
import structlog
from httpx import HTTPStatusError
from httpx_sse import SSEError
from langchain_core._security._ssrf_protection import validate_safe_url
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError

from syntara.core.lib.tls_utils import build_integration_httpx_verify
from syntara.core.utils.exceptions import extract_all_exceptions
from syntara.integrations.adapters.factory import register_health_check_adapter
from syntara.integrations.adapters.protocol import (
    DiscoveredTool,
    DiscoveredToolParameter,
    DiscoverResult,
    HealthCheckErrorType,
    ValidateResult,
    classify_http_error,
)
from syntara.integrations.models.integration import IntegrationType
from syntara.integrations.models.integration_configuration import MCPServerConfigurationInput  # noqa: TC001
from syntara.tool_manager.lib.providers.mcp.mcp_provider import MCPProvider

logger = structlog.stdlib.get_logger(__name__)

__all__ = ["MCPServerAdapter"]

# MCP servers authenticate via Bearer token. The expected credential type
# is "HTTP Bearer Token", whose InjectorResolver output maps the raw
# "token" input to "bearer_token" in extra_vars.
_MCP_CREDENTIAL_KEY = "bearer_token"


class MCPServerAdapter:
    """Adapter for MCP server integrations implementing validate() and discover()."""

    def __init__(self, config: MCPServerConfigurationInput) -> None:
        """Initialize with MCP server configuration."""
        self._config = config

    async def validate(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> ValidateResult:
        """Run a spec-compliant MCP ping against the server using streamable-http transport.

        Uses the MCP SDK's streamable_http_client with ClientSession for:
        - Session initialization
        - JSON-RPC 2.0 message formatting
        - Response parsing
        - Protocol validation

        Timeout strategy: httpx.Timeout covers HTTP I/O; asyncio.timeout covers
        MCP session setup and ping (protocol negotiation can block independently
        of HTTP I/O). Both are necessary.

        Note: This creates a fresh MCP session for each ping. MCPProvider (used by discover())
        manages sessions via MultiServerMCPClient from langchain-mcp-adapters. These two
        session management approaches could be unified in future work.

        See AAP-81945 for session reuse optimization investigation.
        """
        ssrf_error = _check_ssrf(self._config.base_url)
        if ssrf_error:
            return ssrf_error

        api_key = cast("str | None", resolved_credential.get(_MCP_CREDENTIAL_KEY))
        http_headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        result = ValidateResult(
            success=False,
            checked_at=datetime.now(UTC),
            error="Validation was not attempted",
            error_type=HealthCheckErrorType.CONNECTION_ERROR,
        )

        try:
            verify = build_integration_httpx_verify(
                insecure_skip_tls_verify=self._config.insecure_skip_tls_verify,
                ca_certificate=self._config.ca_certificate,
            )

            async with (
                httpx.AsyncClient(
                    headers=http_headers,
                    timeout=httpx.Timeout(timeout_seconds),
                    verify=verify,
                ) as http_client,
                streamable_http_client(
                    url=self._config.base_url,
                    http_client=http_client,
                ) as (read, write, _get_session_id),
                ClientSession(read, write) as session,
            ):
                async with asyncio.timeout(timeout_seconds):
                    await session.initialize()
                    await session.send_ping()

            logger.info(
                "MCP validate succeeded",
                base_url=self._config.base_url,
            )

            result = ValidateResult(
                success=True,
                checked_at=datetime.now(UTC),
            )

        except* (TimeoutError, httpx.TimeoutException):
            # NOTE: This handler must come before ConnectError handler to ensure
            # timeout exceptions (including httpx.ConnectTimeout) are classified as
            # TIMEOUT rather than generic CONNECTION_ERROR.
            logger.warning(
                "MCP validate timed out",
                base_url=self._config.base_url,
                timeout_seconds=timeout_seconds,
            )
            result = ValidateResult(
                success=False,
                checked_at=datetime.now(UTC),
                error=f"Connection timed out after {timeout_seconds}s",
                error_type=HealthCheckErrorType.TIMEOUT,
            )

        except* HTTPStatusError as eg:
            errors = extract_all_exceptions(eg)
            error_type, error_msg = classify_http_error(errors)
            logger.warning(
                "MCP validate HTTP error",
                base_url=self._config.base_url,
                error_type=error_type.value,
                status_codes=[e.response.status_code for e in errors if isinstance(e, HTTPStatusError)],
            )
            result = ValidateResult(
                success=False,
                checked_at=datetime.now(UTC),
                error=error_msg,
                error_type=error_type,
            )

        except* McpError as eg:
            errors = extract_all_exceptions(eg)
            logger.warning(
                "MCP validate protocol error",
                base_url=self._config.base_url,
                error=str(errors[0]),
            )
            result = ValidateResult(
                success=False,
                checked_at=datetime.now(UTC),
                error="Not an MCP endpoint (invalid response format)",
                error_type=HealthCheckErrorType.CONNECTION_ERROR,
            )

        except* SSEError as eg:
            errors = extract_all_exceptions(eg)
            logger.warning(
                "MCP validate SSE error",
                base_url=self._config.base_url,
                error=str(errors[0]),
            )
            result = ValidateResult(
                success=False,
                checked_at=datetime.now(UTC),
                error="Not an MCP endpoint (invalid response format)",
                error_type=HealthCheckErrorType.CONNECTION_ERROR,
            )

        except* ssl.SSLError as eg:
            errors = extract_all_exceptions(eg)
            logger.warning(
                "MCP validate SSL error",
                base_url=self._config.base_url,
                error=str(errors[0]),
            )
            result = ValidateResult(
                success=False,
                checked_at=datetime.now(UTC),
                error="SSL/TLS certificate verification failed",
                error_type=HealthCheckErrorType.SSL_ERROR,
            )

        except* (httpx.ConnectError, OSError) as eg:
            errors = extract_all_exceptions(eg)
            logger.warning(
                "MCP validate connection error",
                base_url=self._config.base_url,
                error=str(errors[0]),
            )
            result = ValidateResult(
                success=False,
                checked_at=datetime.now(UTC),
                error="Unable to connect to the service",
                error_type=HealthCheckErrorType.CONNECTION_ERROR,
            )

        except* httpx.HTTPError as eg:
            errors = extract_all_exceptions(eg)
            logger.warning(
                "MCP validate HTTP transport error",
                base_url=self._config.base_url,
                error=str(errors[0]),
            )
            result = ValidateResult(
                success=False,
                checked_at=datetime.now(UTC),
                error="Not an MCP endpoint (HTTP protocol error)",
                error_type=HealthCheckErrorType.CONNECTION_ERROR,
            )

        except* Exception:
            logger.exception(
                "Unexpected error during MCP validate",
                base_url=self._config.base_url,
            )
            result = ValidateResult(
                success=False,
                checked_at=datetime.now(UTC),
                error="Validation failed unexpectedly",
                error_type=HealthCheckErrorType.CONNECTION_ERROR,
            )

        return result

    async def discover(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> DiscoverResult:
        """Discover tools from the MCP server using MCPProvider.refresh_tools().

        Uses MCPProvider (the same code path as _sync_mcp_tools) so we make
        a single connection to the MCP server rather than two.  The returned
        DiscoveredTool list includes parameter information, enabling
        _sync_mcp_tools to perform a full upsert from this result alone.
        """
        ssrf_error = _check_ssrf(self._config.base_url)
        if ssrf_error:
            return DiscoverResult(
                success=False,
                checked_at=ssrf_error.checked_at,
                error=ssrf_error.error,
                error_type=ssrf_error.error_type,
            )

        api_key = cast("str | None", resolved_credential.get(_MCP_CREDENTIAL_KEY))

        success = True
        error_msg: str | None = None
        error_type: HealthCheckErrorType | None = None
        discovered: list[DiscoveredTool] | None = None

        adapter = MCPProvider(
            base_url=self._config.base_url,
            api_key=api_key,
            insecure_skip_tls_verify=self._config.insecure_skip_tls_verify,
            ca_certificate=self._config.ca_certificate,
        )
        try:
            tools_metadata = await asyncio.wait_for(adapter.refresh_tools(), timeout=timeout_seconds)

            discovered = [_tool_to_discovered(t) for t in tools_metadata]

            logger.info(
                "MCP discover succeeded",
                base_url=self._config.base_url,
                tool_count=len(discovered),
            )

        except* TimeoutError:
            success = False
            error_msg = f"Connection timed out after {timeout_seconds}s"
            error_type = HealthCheckErrorType.TIMEOUT
            logger.warning(
                "MCP discover timed out",
                base_url=self._config.base_url,
                timeout_seconds=timeout_seconds,
            )

        except* HTTPStatusError as eg:
            success = False
            errors = extract_all_exceptions(eg)
            error_type, error_msg = classify_http_error(errors)
            logger.warning(
                "MCP discover HTTP error",
                base_url=self._config.base_url,
                error_type=error_type.value,
                status_codes=[e.response.status_code for e in errors if isinstance(e, HTTPStatusError)],
            )

        except* ssl.SSLError as eg:
            success = False
            errors = extract_all_exceptions(eg)
            error_msg = "SSL/TLS verification failed"
            error_type = HealthCheckErrorType.SSL_ERROR
            logger.warning(
                "MCP discover SSL error",
                base_url=self._config.base_url,
                error=str(errors[0]),
            )

        except* (httpx.ConnectError, OSError) as eg:
            success = False
            errors = extract_all_exceptions(eg)
            error_msg = "Unable to connect to service"
            error_type = HealthCheckErrorType.CONNECTION_ERROR
            logger.warning(
                "MCP discover connection error",
                base_url=self._config.base_url,
                error=str(errors[0]),
            )

        except* Exception as eg:
            success = False
            errors = extract_all_exceptions(eg)
            error_msg = "Discovery failed unexpectedly"
            error_type = HealthCheckErrorType.CONNECTION_ERROR
            logger.exception(
                "Unexpected error during MCP discover",
                base_url=self._config.base_url,
            )
        finally:
            await adapter.close()

        return DiscoverResult(
            success=success,
            checked_at=datetime.now(UTC),
            error=error_msg,
            error_type=error_type,
            discovered_tools=discovered,
        )


def _check_ssrf(base_url: str) -> ValidateResult | None:
    """Return a failure result if the URL targets a cloud metadata endpoint, None otherwise."""
    try:
        validate_safe_url(base_url, allow_private=True, allow_http=True)
    except ValueError as e:
        logger.warning(
            "MCP validate blocked by SSRF protection",
            base_url=base_url,
            error=str(e),
        )
        return ValidateResult(
            success=False,
            checked_at=datetime.now(UTC),
            error="Unable to connect to the service",
            error_type=HealthCheckErrorType.CONNECTION_ERROR,
        )
    return None


def _tool_param_to_discovered(param: ToolParameter) -> DiscoveredToolParameter:
    """Convert a ToolParameter domain object to DiscoveredToolParameter."""
    return DiscoveredToolParameter(
        name=param.name,
        type=str(param.type.value) if hasattr(param.type, "value") else str(param.type),
        description=param.description or "",
        required=bool(param.required),
    )


def _tool_to_discovered(tool: object) -> DiscoveredTool:
    """Convert a Tool domain object returned by MCPProvider.refresh_tools() to DiscoveredTool."""
    # MCPProvider.refresh_tools() returns syntara.tool_manager.models.tool.Tool objects.
    # We access fields via getattr to avoid a circular import.
    name: str = getattr(tool, "name", "")
    description: str | None = getattr(tool, "description", None)
    raw_params: list[ToolParameter] | None = getattr(tool, "parameters", None)

    params: list[DiscoveredToolParameter] | None = None
    if raw_params:
        params = [_tool_param_to_discovered(p) for p in raw_params]

    return DiscoveredTool(name=name, description=description, parameters=params)


register_health_check_adapter(
    IntegrationType.MCP_SERVER,
    lambda c: MCPServerAdapter(cast("MCPServerConfigurationInput", c)),
)
