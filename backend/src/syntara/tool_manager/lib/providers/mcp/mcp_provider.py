"""MCP (Model Context Protocol) provider implementation using langchain."""

import asyncio
import logging
import ssl
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
import structlog
from httpx import HTTPStatusError, codes
from langchain_core.tools import BaseTool

# See https://github.com/langchain-ai/langchain-mcp-adapters/issues/319
from langchain_mcp_adapters.client import MultiServerMCPClient  # type: ignore[import-untyped]

from syntara.core.lib.tls_utils import build_integration_httpx_verify
from syntara.core.utils.exceptions import extract_all_exceptions
from syntara.tool_manager.exceptions import ToolNotFoundError
from syntara.tool_manager.lib.providers.base import ToolProviderAdapter
from syntara.tool_manager.models import (
    Tool,
    ToolParameter,
    ToolParameterType,
    ToolProviderValidationResult,
    ToolSchema,
    ToolStatus,
    ToolValidationResult,
)

logger = structlog.stdlib.get_logger(__name__)


def _make_httpx_client_factory(
    *,
    verify: bool | ssl.SSLContext,
) -> Callable[..., httpx.AsyncClient]:
    """Return an httpx.AsyncClient factory that pins the given TLS verify setting."""
    return lambda headers=None, timeout=None, auth=None: httpx.AsyncClient(
        headers=headers, timeout=timeout, auth=auth, verify=verify
    )


class MCPProvider(ToolProviderAdapter):
    """MCP provider adapter using langchain MultiServerMCPClient.

    This provider integrates with MCP servers using the langchain-mcp-adapters library,
    supporting both SSE and Streaming HTTP transports for communication with MCP servers.

    The configuration is provided as an MCPConfiguration object which includes:
    - provider_type: Always "mcp"
    - base_url: URL of the MCP server
    - api_key: Authentication key for the MCP server (optional)
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        integration_id: UUID | None = None,
        integration_name: str | None = "mcp-integration",
        *,
        insecure_skip_tls_verify: bool = False,
        ca_certificate: str | None = None,
    ) -> None:
        """Initialize MCP provider with configuration.

        Args:
            base_url: URL of the MCP server
            api_key: Authentication key for the MCP server (optional)
            integration_id: Unique identifier for this integration instance (optional for factory)
            integration_name: Human-readable name for the integration (optional for factory)
            insecure_skip_tls_verify: Disable TLS certificate verification (optional)
            ca_certificate: PEM-encoded CA certificate for custom trust (optional)

        Raises:
            ValueError: If configuration is invalid
            ConnectionError: If unable to initialize MCP client

        """
        self.integration_id = integration_id or uuid4()
        self.integration_name = integration_name

        # Store connection parameters directly — api_key is never serialized
        self._base_url = base_url
        self._api_key = api_key
        self._insecure_skip_tls_verify = insecure_skip_tls_verify
        self._ca_certificate = ca_certificate

        # Initialize langchain MCP client
        self._client: MultiServerMCPClient | None = None
        self._tools_cache: dict[str, dict[str, Any]] = {}

    async def _get_client(self) -> MultiServerMCPClient:
        """Get or create the MCP client instance.

        Returns:
            MultiServerMCPClient instance

        Raises:
            ConnectionError: If unable to initialize client

        """
        if self._client is None:
            try:
                # Configure server connection for langchain MCP client
                # Using streamable_http as the primary transport (as per AAP-55733)
                # Use provider_name or fallback to a default key
                server_key = self.integration_name or "mcp-server"
                server_config: dict[str, dict[str, Any]] = {
                    server_key: {
                        "transport": "streamable_http",  # Note: underscore not hyphen
                        "url": self._base_url,
                    }
                }

                # Add API key as Authorization header if provided
                if self._api_key:
                    server_config[server_key]["headers"] = {"Authorization": f"Bearer {self._api_key}"}

                if self._insecure_skip_tls_verify or self._ca_certificate:
                    verify = build_integration_httpx_verify(
                        insecure_skip_tls_verify=self._insecure_skip_tls_verify,
                        ca_certificate=self._ca_certificate,
                    )
                    server_config[server_key]["httpx_client_factory"] = _make_httpx_client_factory(verify=verify)

                # Initialize the MultiServerMCPClient
                self._client = MultiServerMCPClient(server_config)

                auth_info = " with API key authentication" if self._api_key else ""
                logger.info(
                    "Initialized MCP client for provider using streamable-http transport",
                    integration_name=self.integration_name,
                    auth_info=auth_info,
                )

            except Exception as e:
                msg = f"Failed to initialize MCP client: {e}"
                logger.exception(msg)
                raise ConnectionError(msg) from e

        return self._client

    def _process_http_status_error(self, error: HTTPStatusError) -> str:
        if error.response.status_code == codes.UNAUTHORIZED:
            return "MCP session failed to establish connection - Unauthorized"
        if error.response.status_code == codes.FORBIDDEN:
            return "MCP session failed to establish connection - Forbidden"
        return f"Connection validation failed with HTTP error: {error}"

    async def _attempt_validate_connection(self, attempt_timeout: int) -> tuple[list[str], bool]:
        """Attempt a single validation against the MCP server.

        Args:
            attempt_timeout: Timeout in seconds for the connection attempt

        Returns:
            A tuple of (error_messages, retriable). error_messages is empty on
            success. retriable is True when the caller should retry (e.g. on timeout).

        """
        errors: list[str] = []
        retriable = False
        # Reset client so each attempt starts with a fresh MCP session
        self._client = None

        try:
            client = await self._get_client()
            tools = await asyncio.wait_for(client.get_tools(), timeout=attempt_timeout)

            logger.info(
                "Successfully validated MCP provider, found tools",
                integration_name=self.integration_name,
                tool_count=len(tools),
            )
        except* TimeoutError as eg:
            all_exceptions = extract_all_exceptions(eg)
            errors.extend([str(e) for e in all_exceptions])
            retriable = True
        except* httpx.ConnectError as eg:
            all_exceptions = extract_all_exceptions(eg)
            errors.extend([str(e) for e in all_exceptions])
        except* ConnectionError as eg:
            all_exceptions = extract_all_exceptions(eg)
            errors.extend([str(e) for e in all_exceptions])
        except* HTTPStatusError as eg:
            all_exceptions = extract_all_exceptions(eg)
            for exception in all_exceptions:
                if isinstance(exception, HTTPStatusError):
                    msg = self._process_http_status_error(exception)
                    errors.append(msg)
                else:
                    errors.append(str(exception))

        return errors, retriable

    async def validate_connection(self) -> ToolProviderValidationResult:
        """Validate connection to the MCP server.

        Uses retry logic because the streamable-http transport in FastMCP
        has a known race condition where the SSE stream handler can fail
        intermittently with ``ASGI callable returned without completing
        response``, which manifests as a timeout on the client side.

        Returns:
            ToolProviderValidationResult containing validation details

        """
        max_attempts = 3
        per_attempt_timeout = 15
        validation_errors: list[str] = []
        timed_out = False

        logger.info("Validating connection to MCP provider", integration_name=self.integration_name)

        for attempt in range(1, max_attempts + 1):
            validation_errors, retriable = await self._attempt_validate_connection(per_attempt_timeout)

            if not validation_errors:
                break

            if retriable:
                timed_out = True
                if attempt < max_attempts:
                    logger.warning(
                        "MCP validation attempt timed out, retrying",
                        integration_name=self.integration_name,
                        attempt=attempt,
                        max_attempts=max_attempts,
                    )
                    continue
            # Non-retriable error or last attempt — stop
            break

        return ToolProviderValidationResult(
            valid=len(validation_errors) == 0,
            provider_type="mcp",
            validated_at=datetime.now(UTC),
            error="\n".join(validation_errors) if validation_errors else None,
            timeout=timed_out,
        )

    async def get_base_tools(self) -> list[BaseTool]:
        """Get LangChain BaseTools from provider without conversion.

        Returns raw BaseTools for use in Agent Orchestrator without
        converting to Tool domain models.

        Returns:
            list[BaseTool]: Raw LangChain tools from provider

        Raises:
            ProviderError: If tool retrieval fails
            TimeoutError: If operation times out
            ConnectionError: If unable to communicate with provider

        """
        timeout = 30  # Default timeout for tool retrieval

        try:
            logger.info("Retrieving base tools from MCP provider", integration_name=self.integration_name)

            client = await self._get_client()

            # Get tools from MCP server
            langchain_tools: list[BaseTool] = await asyncio.wait_for(client.get_tools(), timeout=timeout)

            logger.info(
                "Successfully retrieved base tools from MCP provider",
                tool_count=len(langchain_tools),
                integration_name=self.integration_name,
            )
            return langchain_tools

        except TimeoutError as e:
            msg = f"Tool retrieval timed out after {timeout}s"
            logger.warning(
                "MCP provider tool retrieval timed out",
                integration_name=self.integration_name,
                message=msg,
                timeout_seconds=timeout,
            )
            raise TimeoutError(msg) from e
        except Exception as e:
            msg = f"Tool retrieval failed: {e}"
            logger.exception("MCP provider tool retrieval failed", integration_name=self.integration_name, message=msg)
            raise ConnectionError(msg) from e

    async def refresh_tools(self) -> list[Tool]:
        """Refresh and discover tools from the MCP server.

        Returns:
            list[Tool]: List of available tools with their schemas

        Raises:
            ProviderError: If tool discovery fails
            TimeoutError: If operation times out
            ConnectionError: If unable to communicate with provider

        """
        try:
            logger.info("Refreshing tools from MCP provider", integration_name=self.integration_name)

            # Use get_base_tools to retrieve raw tools
            langchain_tools = await self.get_base_tools()

            tools = []
            self._tools_cache.clear()

            for langchain_tool in langchain_tools:
                try:
                    tool = self._convert_langchain_tool_to_tool(langchain_tool)
                    tools.append(tool)
                except (ValueError, TypeError, AttributeError) as e:
                    logger.warning("Failed to convert tool", tool_name=langchain_tool.name, error=str(e))
                    continue

            logger.info(
                "Successfully refreshed tools from MCP provider",
                tool_count=len(tools),
                integration_name=self.integration_name,
            )
            return tools

        except (TimeoutError, ConnectionError):
            # Re-raise these as they're already properly formatted
            raise
        except Exception as e:
            msg = f"Tool refresh failed: {e}"
            logger.exception("MCP provider tool refresh failed", integration_name=self.integration_name, message=msg)
            raise ConnectionError(msg) from e

    async def get_tool_schema(self, tool_name: str) -> ToolSchema:
        """Get detailed schema for a specific tool.

        Args:
            tool_name: Name of the tool to get schema for

        Returns:
            ToolSchema containing tool schema with input/output specifications

        Raises:
            ToolNotFoundError: If tool doesn't exist on provider
            ProviderError: If schema retrieval fails
            TimeoutError: If operation times out

        """
        if tool_name not in self._tools_cache:
            msg = f"Tool '{tool_name}' not found in provider {self.integration_name}."
            logger.warning(msg)
            raise ToolNotFoundError(msg)

        try:
            cached_tool = self._tools_cache[tool_name]
            langchain_tool = cached_tool["langchain_tool"]

            # Build comprehensive schema
            input_schema = cached_tool.get("schema", {})

            tool_schema = ToolSchema(
                name=tool_name,
                description=langchain_tool.description,
                input_schema=input_schema,
                output_schema=None,  # MCP tools don't typically define output schemas
                examples=None,  # Could be added from tool examples if available
            )

            logger.debug(
                "Retrieved schema for tool from MCP provider",
                tool_name=tool_name,
                integration_name=self.integration_name,
            )
            return tool_schema

        except Exception as e:
            msg = f"Failed to get schema for tool '{tool_name}': {e}"
            logger.exception(
                "MCP provider get tool schema failed",
                integration_name=self.integration_name,
                tool_name=tool_name,
                message=msg,
            )
            raise ConnectionError(msg) from e

    async def validate_tool(self, tool_name: str, parameters: dict[str, Any] | None = None) -> ToolValidationResult:
        """Validate tool functionality and server communication.

        This method validates that the tool can be called and communicates properly
        with the provider. It performs a dry-run validation without executing the tool.

        Args:
            tool_name: Name of the tool to validate
            parameters: Optional minimal parameters for validation

        Returns:
            ToolValidationResult containing validation details

        Raises:
            ToolNotFoundError: If tool doesn't exist on provider
            ProviderError: If tool validation fails due to provider issues
            TimeoutError: If validation times out

        """
        if tool_name not in self._tools_cache:
            msg = f"Tool '{tool_name}' not found in provider {self.integration_name}"
            logger.warning(msg)
            raise ToolNotFoundError(msg)

        try:
            logger.info(
                "Validating tool from MCP provider", tool_name=tool_name, integration_name=self.integration_name
            )

            cached_tool = self._tools_cache[tool_name]
            langchain_tool = cached_tool["langchain_tool"]
            test_params = parameters or {}

            # Perform schema and connectivity validation
            schema_valid, schema_error = self._validate_tool_schema(langchain_tool, test_params)
            connectivity_valid, connectivity_error = await self._validate_tool_connectivity()

            # Build result
            success = schema_valid and connectivity_valid
            error_message = self._build_validation_error_message(
                schema_valid=schema_valid,
                schema_error=schema_error,
                connectivity_valid=connectivity_valid,
                connectivity_error=connectivity_error,
            )

            result = ToolValidationResult(
                success=success,
                duration_ms=0,  # Not measuring actual execution time
                status="success" if success else "failure",
                message=error_message or f"Tool '{tool_name}' validation completed successfully",
                validated_at=datetime.now(UTC),
            )

            self._log_validation_result(tool_name, success=success)
            return result

        except TimeoutError as e:
            msg = "Tool validation timed out after 10s"
            logger.warning(
                "MCP provider tool validation timed out",
                integration_name=self.integration_name,
                tool_name=tool_name,
                message=msg,
            )
            raise TimeoutError(msg) from e
        except Exception as e:
            msg = f"Tool validation failed: {e}"
            logger.exception(
                "MCP provider tool validation failed",
                integration_name=self.integration_name,
                tool_name=tool_name,
                message=msg,
            )
            raise ConnectionError(msg) from e

    def _validate_tool_schema(self, langchain_tool: BaseTool, test_params: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate tool schema.

        Args:
            langchain_tool: The langchain tool object
            test_params: Parameters to validate

        Returns:
            tuple: (is_valid, error_message)

        """
        if not langchain_tool.args_schema:
            return True, None

        try:
            # Handle both BaseModel classes and dict schemas
            if hasattr(langchain_tool.args_schema, "model_validate"):
                # Pydantic BaseModel
                langchain_tool.args_schema.model_validate(test_params)
            else:
                # Other schema types - skip validation
                pass
            return True, None
        except (ValueError, TypeError, AttributeError) as e:
            return False, str(e)

    async def _validate_tool_connectivity(self) -> tuple[bool, str | None]:
        """Validate tool connectivity.

        Returns:
            tuple: (is_valid, error_message)

        """
        try:
            client = await self._get_client()
            timeout = 10  # Shorter timeout for validation
            await asyncio.wait_for(client.get_tools(), timeout=timeout)
            return True, None
        except (TimeoutError, ConnectionError, OSError) as e:
            return False, str(e)

    def _build_validation_error_message(
        self,
        *,
        schema_valid: bool,
        schema_error: str | None,
        connectivity_valid: bool,
        connectivity_error: str | None,
    ) -> str | None:
        """Build validation error message.

        Args:
            schema_valid: Whether schema validation passed
            schema_error: Schema validation error
            connectivity_valid: Whether connectivity check passed
            connectivity_error: Connectivity error

        Returns:
            Combined error message or None if all validations passed

        """
        if schema_valid and connectivity_valid:
            return None

        error_parts = []
        if not schema_valid:
            error_parts.append(f"Schema validation failed: {schema_error}")
        if not connectivity_valid:
            error_parts.append(f"Connectivity check failed: {connectivity_error}")
        return "; ".join(error_parts)

    def _log_validation_result(self, tool_name: str, *, success: bool) -> None:
        """Log validation result.

        Args:
            tool_name: Name of the tool
            success: Whether validation succeeded

        """
        log_level = logging.INFO if success else logging.WARNING
        status_msg = "success" if success else "failed"
        logger.log(
            log_level,
            "Tool validation from MCP provider",
            tool_name=tool_name,
            integration_name=self.integration_name,
            status=status_msg,
        )

    def _convert_langchain_tool_to_tool(self, langchain_tool: BaseTool) -> Tool:
        """Convert a langchain tool to our Tool model.

        Args:
            langchain_tool: The langchain tool object

        Returns:
            Tool: Converted tool object

        """
        tool_name = langchain_tool.name
        namespaced_name = f"{self.integration_name}::{tool_name}"

        # Extract and cache schema
        schema = self._extract_tool_schema(langchain_tool)
        self._tools_cache[tool_name] = {
            "langchain_tool": langchain_tool,
            "schema": schema,
        }

        # Convert schema to parameters
        parameters = self._create_tool_parameters(schema)

        # Create tool object (integration_id is set by IntegrationService when persisting)
        tool = Tool(
            id=uuid4(),
            name=tool_name,
            namespaced_name=namespaced_name,
            description=langchain_tool.description,
            parameters=parameters,
            status=ToolStatus.AVAILABLE,
            last_refreshed_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=self.integration_id,
            updated_by=self.integration_id,
        )

        # Update parameter tool_id references
        for parameter in parameters:
            parameter.tool_id = tool.id

        return tool

    def _extract_tool_schema(self, langchain_tool: BaseTool) -> dict[str, Any]:
        """Extract schema from langchain tool.

        Args:
            langchain_tool: The langchain tool object

        Returns:
            dict: Tool schema

        """
        schema: dict[str, Any] = {}
        if langchain_tool.args_schema:
            if hasattr(langchain_tool.args_schema, "model_json_schema"):
                schema = langchain_tool.args_schema.model_json_schema()
            elif isinstance(langchain_tool.args_schema, dict):
                schema = langchain_tool.args_schema

        return schema

    def _create_tool_parameters(self, schema: dict[str, Any]) -> list[ToolParameter]:
        """Create ToolParameter objects from schema.

        Args:
            schema: Tool schema dictionary

        Returns:
            list[ToolParameter]: List of tool parameters

        """
        parameters: list[ToolParameter] = []
        if not schema:
            return parameters

        properties = schema.get("properties", {})
        required_params = schema.get("required", [])

        for param_name, param_def in properties.items():
            parameter = self._create_tool_parameter(param_name, param_def, required_params)
            parameters.append(parameter)

        return parameters

    def _create_tool_parameter(
        self, param_name: str, param_def: dict[str, Any], required_params: list[str]
    ) -> ToolParameter:
        """Create a single ToolParameter from definition.

        Args:
            param_name: Parameter name
            param_def: Parameter definition
            required_params: List of required parameter names

        Returns:
            ToolParameter: Created parameter

        """
        param_type = self._convert_json_type_to_tool_parameter_type(param_def.get("type", "string"))

        # Handle default_value - must be dict[str, Any] | None
        default_val = param_def.get("default")
        if default_val is not None and not isinstance(default_val, dict):
            default_val = {"value": default_val}

        # Handle example_value - must be dict[str, Any] | None
        example_val = param_def.get("examples", [None])[0] if param_def.get("examples") else None
        if example_val is not None and not isinstance(example_val, dict):
            example_val = {"value": example_val}

        return ToolParameter(
            id=uuid4(),
            tool_id=uuid4(),  # Will be set when Tool is created
            name=param_name,
            type=param_type,
            description=param_def.get("description") or "",
            required=param_name in required_params,
            default_value=default_val,
            example_value=example_val,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=self.integration_id,
            updated_by=self.integration_id,
        )

    def _convert_json_type_to_tool_parameter_type(self, json_type: str) -> ToolParameterType:
        """Convert JSON schema type to ToolParameterType enum.

        Args:
            json_type: JSON schema type string

        Returns:
            ToolParameterType enum value

        """
        type_mapping = {
            "string": ToolParameterType.STRING,
            "number": ToolParameterType.NUMBER,
            "integer": ToolParameterType.NUMBER,
            "boolean": ToolParameterType.BOOLEAN,
            "object": ToolParameterType.OBJECT,
            "array": ToolParameterType.ARRAY,
        }

        return type_mapping.get(json_type, ToolParameterType.STRING)

    async def close(self) -> None:
        """Close the MCP client connection.

        This method should be called when the provider is no longer needed
        to properly clean up resources.
        """
        if self._client:
            try:
                # The langchain MCP client doesn't have an explicit close method,
                # but we can clear our reference and cache
                self._client = None
                self._tools_cache.clear()
                logger.info("Closed MCP client for provider", integration_name=self.integration_name)
            except (AttributeError, RuntimeError) as e:
                logger.warning(
                    "Error closing MCP client for provider", integration_name=self.integration_name, error=str(e)
                )
