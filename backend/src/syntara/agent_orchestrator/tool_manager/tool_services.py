"""Tool Manager Integration Services.

This module provides functions for integrating with the Tool Manager component,
including tool discovery, retrieval, and error reporting.
"""

import re
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import structlog
from langchain_core.tools import BaseTool

from syntara.agent_orchestrator.audit.tool_management import ToolDiscoveryEvent, ToolDiscoveryStatus
from syntara.agent_orchestrator.tool_manager.tool_filtering import (
    enhance_namespaced_tools_with_metadata,
    filter_base_tools_by_enabled,
)
from syntara.agent_orchestrator.tool_manager.tool_manager_client import ToolManagerClient
from syntara.agent_orchestrator.tool_manager.types import (
    NamespacedBaseTool,
    ToolDiscoveryResult,
)
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.sanitization import CREDENTIAL_PATTERNS, REDACTED
from syntara.core.config.base import get_settings
from syntara.integrations.models.integration import IntegrationRead, IntegrationType
from syntara.tool_manager.lib.providers.factory import ProviderFactory, get_provider_factory
from syntara.tool_manager.models.tool import ToolStatus, ToolWithParameters

logger = structlog.stdlib.get_logger(__name__)


def _get_tool_manager_client() -> ToolManagerClient:
    """Create a ToolManagerClient with settings from the application configuration.

    Centralises the 4-parameter construction so that adding a new
    constructor parameter requires only one change.
    """
    settings = get_settings()
    return ToolManagerClient(
        base_url=str(settings.tool_manager_base_url),
        timeout=settings.tool_manager_timeout_seconds,
        max_connections=settings.tool_manager_max_connections,
        max_keepalive_connections=settings.tool_manager_max_keepalive_connections,
    )


async def _discover_mcp_integrations() -> list[IntegrationRead]:
    """Discover MCP server integrations from the Integrations API.

    Fetches all integrations of type mcp_server.

    Returns:
        List of all MCP server IntegrationRead records.
        Returns empty list if the API is unavailable or fails.

    """
    try:
        async with _get_tool_manager_client() as client:
            all_integrations = await client.get_all_mcp_integrations()
            logger.info("Discovered MCP integrations", integration_count=len(all_integrations))
            return all_integrations
    except Exception as e:  # noqa: BLE001 (Failure of ToolManagerClient for whatever reason is not critical)
        logger.warning("Failed to discover MCP integrations, continuing without them", error=str(e))
        return []


async def _discover_tools() -> ToolDiscoveryResult:
    """Discover tools from Tool Manager.

    Fetches all tools and filters them at service layer.

    Returns:
        Tuple of (enabled_tools, disabled_tools).
        Returns empty lists if Tool Manager is unavailable or fails.

    """
    try:
        async with _get_tool_manager_client() as client:
            all_tools = await client.get_all_tools()
            enabled_tools = [t for t in all_tools if t.enabled]
            disabled_tools = [t for t in all_tools if not t.enabled]
            logger.info(
                "Discovered enabled and disabled Tools",
                enabled_count=len(enabled_tools),
                disabled_count=len(disabled_tools),
                total_count=len(all_tools),
            )
            return enabled_tools, disabled_tools
    except Exception as e:  # noqa: BLE001 (Failure of ToolManagerClient for whatever reason is not critical)
        logger.warning("Tool Manager failed, continuing without tools", error=str(e))
        return [], []


async def report_tool_execution_failure(tool_id: UUID, error_message: str) -> None:
    """Report tool execution failure to Tool Manager.

    Args:
        tool_id: ID of the tool that failed
        error_message: Error message describing the failure

    """
    async with _get_tool_manager_client() as client:
        try:
            await client.update_tool_status(tool_id=tool_id, status=ToolStatus.ERROR, refresh_error=error_message)
            logger.info("Reported tool execution failure", tool_id=tool_id)
        except Exception:
            logger.exception("Failed to report tool execution failure")


def _should_skip_integration(integration: IntegrationRead) -> bool:
    """Check if integration should be skipped due to missing configuration."""
    if not integration.configuration:
        logger.warning("Skipping integration: no configuration", integration_name=integration.name)
        return True
    return False


def _is_integration_type_supported(integration: IntegrationRead, provider_factory: ProviderFactory) -> bool:
    """Check if integration type is supported by the provider factory."""
    if integration.integration_type != IntegrationType.MCP_SERVER:
        logger.warning(
            "Skipping integration with unsupported type",
            integration_name=integration.name,
            integration_type=integration.integration_type,
        )
        return False

    provider_type = "mcp"
    if not provider_factory.is_registered(provider_type):
        supported_types = provider_factory.get_registered_provider_types()
        logger.warning(
            "Skipping integration: mcp provider type not registered",
            integration_name=integration.name,
            supported_types=supported_types,
        )
        return False
    return True


def _prepare_config_params(integration: IntegrationRead, api_key: str | None = None) -> dict[str, Any]:
    """Prepare configuration parameters for provider adapter creation.

    Filters configuration fields to only those understood by the provider adapter:
    - base_url: The MCP server endpoint
    - provider_id: Set from integration.id
    - provider_name: Set from integration.name
    - api_key: The bearer token (if provided by the credential resolver)

    System-managed fields are excluded since they are not constructor
    parameters on the adapter implementations.
    """
    config = integration.configuration
    excluded_fields = frozenset({"integration_type", "discovered_models", "allow_http"})
    config_params = {k: v for k, v in config.model_dump().items() if k not in excluded_fields and v is not None}
    config_params["integration_id"] = integration.id
    config_params["integration_name"] = integration.name
    if api_key is not None:
        config_params["api_key"] = api_key
    return config_params


def _create_namespaced_tools(integration: IntegrationRead, provider_tools: list[BaseTool]) -> list[NamespacedBaseTool]:
    """Create namespaced tools from integration tools."""
    return [
        NamespacedBaseTool(
            integration_id=integration.id,
            integration_name=integration.name,
            tool_name=tool.name,
            base_tool=tool,
        )
        for tool in provider_tools
    ]


def _sanitize_error_message(error: Exception, max_length: int = 200) -> str:
    """Produce a safe, truncated error summary for user-facing storage.

    Raw exception messages from external services may contain internal
    hostnames, credentials, stack traces, or other sensitive data.
    Uses the same credential patterns as the audit EventSanitizer to
    detect and redact sensitive tokens embedded in the message.
    """
    msg = str(error).split("\n", maxsplit=1)[0].strip()
    if len(msg) > max_length:
        msg = msg[:max_length] + "…"

    msg_lower = msg.lower()
    for pattern in CREDENTIAL_PATTERNS:
        if re.search(rf"(?:^|[_\-. ])(?:{re.escape(pattern)})(?:[_\-. ]|$)", msg_lower):
            return f"{type(error).__name__}: {REDACTED}"

    return msg


async def _process_single_integration(
    integration: IntegrationRead,
    provider_factory: ProviderFactory,
    credential_resolver: Callable[[UUID], Awaitable[str | None]] | None = None,
) -> list[NamespacedBaseTool]:
    """Process a single integration and return its namespaced tools.

    Read-only: connects to the MCP server and returns tools.
    Does NOT mutate integration or tool status on failure — just skips.
    Only processes enabled integrations with valid configuration.
    """
    if _should_skip_integration(integration):
        return []

    if not _is_integration_type_supported(integration, provider_factory):
        return []

    if not integration.enabled:
        logger.debug(
            "Skipping disabled integration",
            integration_name=integration.name,
            integration_status=integration.validation_status.value if integration.validation_status else "unknown",
        )
        return []

    try:
        api_key: str | None = None
        if credential_resolver:
            api_key = await credential_resolver(integration.id)

        config_params = _prepare_config_params(integration, api_key=api_key)
        provider_type = "mcp"

        adapter = provider_factory.create_provider_instance(provider_type, **config_params)
        provider_tools = await adapter.get_base_tools()

        namespaced_tools = _create_namespaced_tools(integration, provider_tools)
        logger.info(
            "Retrieved tools from integration", tool_count=len(provider_tools), integration_name=integration.name
        )

        return namespaced_tools

    except Exception as e:  # noqa: BLE001 (Handle any integration errors gracefully without mutating state)
        safe_msg = _sanitize_error_message(e)
        logger.warning(
            "Failed to get tools from integration during execution, skipping",
            integration_name=integration.name,
            error=safe_msg,
        )
        return []


async def _retrieve_base_tools_from_integrations(
    all_integrations: list[IntegrationRead],
    credential_resolver: Callable[[UUID], Awaitable[str | None]] | None = None,
) -> list[NamespacedBaseTool]:
    """Retrieve BaseTools from MCP server integrations using ProviderFactory pattern.

    Read-only: connects to enabled integrations and retrieves callable tools.
    Does NOT update integration or tool status.

    Args:
        all_integrations: List of all mcp_server integrations
        credential_resolver: Optional async callable that resolves a bearer token given an integration_id

    Returns:
        List of NamespacedBaseTool containing tools retrieved from integrations

    """
    namespaced_tools: list[NamespacedBaseTool] = []

    provider_factory = await get_provider_factory()
    for integration in all_integrations:
        integration_tools = await _process_single_integration(integration, provider_factory, credential_resolver)
        namespaced_tools.extend(integration_tools)

    logger.info(
        "Retrieved total tools from integrations",
        total_tool_count=len(namespaced_tools),
        integration_count=len(all_integrations),
    )
    return namespaced_tools


def _filter_enabled_tools(
    namespaced_tools: list[NamespacedBaseTool],
    enabled_tools: list[ToolWithParameters],
) -> list[NamespacedBaseTool]:
    """Filter NamespacedBaseTools by enabled status using (integration_id, name).

    Args:
        namespaced_tools: List of NamespacedBaseTool from integrations
        enabled_tools: List of enabled tools from Tool Manager

    Returns:
        List of filtered NamespacedBaseTools

    """
    filtered_tools = filter_base_tools_by_enabled(namespaced_tools, enabled_tools)
    logger.info("Filtered tools for execution", filtered_tool_count=len(filtered_tools))
    return filtered_tools


def _enhance_tools_with_metadata(
    namespaced_tools: list[NamespacedBaseTool],
    enabled_tools: list[ToolWithParameters],
) -> list[BaseTool]:
    """Enhance NamespacedBaseTools with metadata from Tool Manager.

    Args:
        namespaced_tools: List of filtered NamespacedBaseTools
        enabled_tools: List of enabled tools from Tool Manager

    Returns:
        List of BaseTools enhanced with metadata

    """
    enhanced_tools = enhance_namespaced_tools_with_metadata(namespaced_tools, enabled_tools)
    logger.info("Enhanced tools with metadata", enhanced_tool_count=len(enhanced_tools))
    return enhanced_tools


class ToolRetriever:
    """Read-only tool retrieval orchestrator for agent execution.

    Retrieves tools from MCP servers and matches them against the Tool Manager
    database to provide the agent with callable, metadata-enriched tools.

    Unlike the former ToolSynchronizer, this class does NOT mutate any state:
    it does not mark tools MISSING, does not re-enable tools, and does not
    update integration status. State management is the responsibility of the
    integrations domain's own refresh/health-check flows.
    """

    def __init__(
        self,
        session_id: str,
        invocation_id: UUID,
        execution_id: UUID | None = None,
        request_id: UUID | None = None,
        credential_resolver: Callable[[UUID], Awaitable[str | None]] | None = None,
        activity_id: str | None = None,
        activity_name: str | None = None,
    ) -> None:
        """Initialize the tool retriever."""
        self.session_id = session_id
        self.invocation_id = invocation_id
        self.execution_id = execution_id
        self.request_id = request_id
        self.credential_resolver = credential_resolver
        self.activity_id = activity_id
        self.activity_name = activity_name
        self.all_integrations: list[IntegrationRead] = []
        self.enabled_tools: list[ToolWithParameters] = []
        self.disabled_tools: list[ToolWithParameters] = []
        self.namespaced_tools: list[NamespacedBaseTool] = []

    async def retrieve_tools(self) -> list[BaseTool]:
        """Retrieve tools from MCP servers, filtered by what is enabled in the DB.

        Returns:
            List of filtered BaseTools ready for execution

        """
        logger.info("Starting tool retrieval", invocation_id=self.invocation_id)

        AuditEventDispatcher.dispatch(
            ToolDiscoveryEvent(
                status=ToolDiscoveryStatus.STARTED,
                session_id=self.session_id,
                invocation_id=self.invocation_id,
                execution_id=self.execution_id,
                request_id=self.request_id,
                activity_id=self.activity_id,
                activity_name=self.activity_name,
            )
        )

        try:
            # Step 1: Discover MCP integrations and tools from Tool Manager
            self.all_integrations = await _discover_mcp_integrations()
            self.enabled_tools, self.disabled_tools = await _discover_tools()

            # Step 2: Connect to enabled integrations and retrieve BaseTools
            self.namespaced_tools = await _retrieve_base_tools_from_integrations(
                self.all_integrations, self.credential_resolver
            )

            # Step 3: Filter BaseTools by enabled status
            filtered_tools = _filter_enabled_tools(self.namespaced_tools, self.enabled_tools)

            # Step 4: Enhance BaseTools with metadata for failure handling
            enhanced_tools = _enhance_tools_with_metadata(filtered_tools, self.enabled_tools)

            logger.info("Tool retrieval completed", invocation_id=self.invocation_id)

            tool_names = [tool.name for tool in enhanced_tools]
            AuditEventDispatcher.dispatch(
                ToolDiscoveryEvent(
                    status=ToolDiscoveryStatus.COMPLETED,
                    session_id=self.session_id,
                    invocation_id=self.invocation_id,
                    execution_id=self.execution_id,
                    request_id=self.request_id,
                    integrations_discovered=len(self.all_integrations),
                    tools_discovered=len(self.namespaced_tools),
                    tools_enabled=len(self.enabled_tools),
                    tools_disabled=len(self.disabled_tools),
                    tools_filtered=len(filtered_tools),
                    tools_provided_to_llm=len(enhanced_tools),
                    tool_names=tool_names,
                    activity_id=self.activity_id,
                    activity_name=self.activity_name,
                )
            )

            return enhanced_tools

        except Exception as e:
            AuditEventDispatcher.dispatch(
                ToolDiscoveryEvent(
                    status=ToolDiscoveryStatus.FAILED,
                    session_id=self.session_id,
                    invocation_id=self.invocation_id,
                    execution_id=self.execution_id,
                    request_id=self.request_id,
                    error_type=type(e).__name__,
                    activity_id=self.activity_id,
                    activity_name=self.activity_name,
                )
            )

            logger.exception("Tool retrieval failed", invocation_id=self.invocation_id)
            return []
