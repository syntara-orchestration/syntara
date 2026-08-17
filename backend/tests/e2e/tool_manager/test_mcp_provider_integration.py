"""E2E tests for MCP provider with the MCP server started by the e2e infrastructure.

Tests complete MCP integration workflow including:
- Integration status and tool discovery via the shared MCP integration
- Tool parameters persistence
- Tools API integration
- Connection failure scenarios
"""

import os
import time
from http import HTTPStatus
from typing import Any
from uuid import UUID

import httpx
import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import _retry_api_call
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import IntegrationCreate, IntegrationStatus, IntegrationType
from syntara_api_client.models.health_check_error_type import HealthCheckErrorType
from syntara_api_client.models.mcp_server_configuration_input import MCPServerConfigurationInput
from syntara_api_client.models.tool_status import ToolStatus
from syntara_api_client.models.validate_result import ValidateResult
from syntara_api_client.types import Response

pytestmark = [pytest.mark.e2e]

MCP_PORT = os.environ.get("MCP_PORT", "8765")
MCP_PROVIDER_URL = os.environ.get("MCP_BASE_URL", f"http://mcp-server:{MCP_PORT}/mcp")

# Auxiliary MCP servers deployed by the e2e infrastructure specifically for the
# auth-failure tests below (see podman-compose.yml and
# tools/run_mcp_scenario_servers.py). These are reached via the same
# compose-network service name pattern as MCP_PROVIDER_URL above.
#
# Earlier revisions pointed at ad hoc servers started in-process via
# `http://host.containers.internal:<port>/mcp`. Under Podman's pasta network
# backend that address resolves to a 169.254.0.0/16 link-local IP that is
# unconditionally blocked by SSRF cloud-metadata protection, so validate()
# failed with CONNECTION_ERROR before ever reaching the target server instead
# of exercising the intended 401/403 AUTH_FAILURE path.
MCP_AUTH_PORT = os.environ.get("MCP_AUTH_PORT", "8766")
MCP_AUTH_PROVIDER_URL = os.environ.get("MCP_AUTH_BASE_URL", f"http://mcp-server-scenarios:{MCP_AUTH_PORT}/mcp")
MCP_FORBIDDEN_PORT = os.environ.get("MCP_FORBIDDEN_PORT", "8767")
MCP_FORBIDDEN_PROVIDER_URL = os.environ.get(
    "MCP_FORBIDDEN_BASE_URL", f"http://mcp-server-scenarios:{MCP_FORBIDDEN_PORT}/mcp"
)

# Guard: skip auth/forbidden tests when the scenario server is not deployed
# (e.g. Konflux pipelines that only wire the happy-path MCP server).
_SCENARIO_SERVERS_AVAILABLE: bool | None = None


def _check_scenario_servers_available() -> bool:
    """Return True if mcp-server-scenarios health endpoints respond."""
    global _SCENARIO_SERVERS_AVAILABLE  # noqa: PLW0603
    if _SCENARIO_SERVERS_AVAILABLE is not None:
        return _SCENARIO_SERVERS_AVAILABLE
    import urllib.request

    auth_health = MCP_AUTH_PROVIDER_URL.rsplit("/mcp", 1)[0] + "/health"
    try:
        urllib.request.urlopen(auth_health, timeout=3)  # noqa: S310
        _SCENARIO_SERVERS_AVAILABLE = True
    except Exception:
        _SCENARIO_SERVERS_AVAILABLE = False
    return _SCENARIO_SERVERS_AVAILABLE


requires_scenario_servers = pytest.mark.skipif(
    "not _check_scenario_servers_available()",
    reason="mcp-server-scenarios not deployed (requires compose profile or k8s manifests)",
)


TRANSIENT_STATUSES = {HTTPStatus.INTERNAL_SERVER_ERROR, HTTPStatus.BAD_GATEWAY, HTTPStatus.SERVICE_UNAVAILABLE}


def _validate_provider(
    syntara_api: SyntaraApiRegistry,
    provider_id: UUID,
    *,
    timeout: float = 10.0,
    interval: float = 0.5,
) -> Response[Any]:
    """Call validate, retrying on 404 and transient errors until the integration is findable."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            resp = syntara_api.integrations.validate(integration_id=provider_id)
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(interval)
            continue
        if resp.status_code not in {HTTPStatus.NOT_FOUND, *TRANSIENT_STATUSES}:
            return resp
        if time.monotonic() >= deadline:
            msg = f"Integration {provider_id} still returns {resp.status_code} after {timeout}s"
            raise AssertionError(msg)
        time.sleep(interval)


def _wait_for_provider_status(
    syntara_api: SyntaraApiRegistry,
    provider_id: UUID,
    expected: IntegrationStatus,
    *,
    timeout: float = 30.0,
    interval: float = 0.5,
) -> None:
    """Poll until the integration reaches the expected status."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            resp = syntara_api.integrations.get(integration_id=provider_id)
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(interval)
            continue
        if resp.status_code in TRANSIENT_STATUSES:
            if time.monotonic() >= deadline:
                msg = f"Integration {provider_id} still returns {resp.status_code} after {timeout}s"
                raise AssertionError(msg)
            time.sleep(interval)
            continue
        integration = resp.assert_and_get()
        if integration.validation_status == expected:
            return
        if time.monotonic() >= deadline:
            msg = (
                f"Integration {provider_id} status is {integration.validation_status}, expected {expected} "
                f"(timed out after {timeout}s)"
            )
            raise AssertionError(msg)
        time.sleep(interval)


class TestMCPProviderIntegration:
    """E2E tests for MCP integration with the running MCP server."""

    @pytest.mark.mcp
    def test_provider_status_and_tools(self, syntara_api: SyntaraApiRegistry, mcp_integration_id: str) -> None:
        """Test that the shared MCP integration is available with discovered tools."""
        integration_id = UUID(mcp_integration_id)

        # Check integration status
        integration = syntara_api.integrations.get(integration_id=integration_id).assert_and_get()
        assert integration.validation_status == IntegrationStatus.AVAILABLE
        assert integration.enabled is True
        assert integration.validation_error is None
        assert integration.last_validated_at is not None
        assert integration.integration_type == IntegrationType.MCP_SERVER

        # Verify discovered tools
        tools_list = syntara_api.tools.list(
            additional_params={"integration_id[eq]": mcp_integration_id}
        ).assert_and_get()
        tools = tools_list.resources
        expected_tools = {"calculate_sum", "calculate_product", "get_greeting"}
        discovered_names = {t.name for t in tools}
        assert len(tools) == 3, f"Expected 3 tools, got {len(tools)}: {discovered_names}"
        assert discovered_names == expected_tools

        for tool in tools:
            assert tool.integration_id == integration_id
            assert tool.status == ToolStatus.AVAILABLE
            assert tool.last_refreshed_at is not None
            assert tool.description is not None
            assert len(tool.description) > 0

        # Verify tool detail endpoint
        sum_tool = next(t for t in tools if t.name == "calculate_sum")
        syntara_api.tools.get(tool_id=sum_tool.id).assert_and_get()

    @pytest.mark.mcp
    def test_tool_parameters_persistence(self, syntara_api: SyntaraApiRegistry, mcp_integration_id: str) -> None:
        """Test that MCP tool parameters are properly persisted to database."""
        integration_id = UUID(mcp_integration_id)

        tools_list = syntara_api.tools.list(
            additional_params={"integration_id[eq]": mcp_integration_id}
        ).assert_and_get()
        tools = tools_list.resources
        assert len(tools) == 3

        sum_tool = next((t for t in tools if t.name == "calculate_sum"), None)
        assert sum_tool is not None

        tool_detail = syntara_api.tools.get(tool_id=sum_tool.id).assert_and_get()
        assert tool_detail.integration_id == integration_id
        assert tool_detail.name == "calculate_sum"
        assert tool_detail.description is not None

    @pytest.mark.mcp
    def test_mcp_provider_connection_failure_handling(self, syntara_api: SyntaraApiRegistry) -> None:
        """Test MCP integration creation with unreachable server."""
        create_resp = _retry_api_call(
            lambda: syntara_api.integrations.create(
                body=IntegrationCreate(
                    name=unique_name("test-mcp-unreachable"),
                    description="Test MCP integration with unreachable server",
                    integration_type=IntegrationType.MCP_SERVER,
                    configuration=MCPServerConfigurationInput(
                        base_url="https://mcp-server:9999/nonexistent",
                    ),
                ),
            )
        )
        integration = create_resp.assert_and_get()
        integration_id = integration.id
        assert integration.validation_status == IntegrationStatus.UNKNOWN

        validate_result = _validate_provider(syntara_api, integration_id).assert_and_get()
        assert isinstance(validate_result, ValidateResult)
        assert validate_result.success is False
        assert validate_result.error_type == HealthCheckErrorType.CONNECTION_ERROR
        assert isinstance(validate_result.error, str)
        assert "unable to connect" in validate_result.error.lower()

        _wait_for_provider_status(syntara_api, integration_id, IntegrationStatus.ERROR)

        integration_after = syntara_api.integrations.get(integration_id=integration_id).assert_and_get()
        assert integration_after.validation_error is not None

        tools_list = syntara_api.tools.list(
            additional_params={"integration_id[eq]": str(integration_id)}
        ).assert_and_get()
        assert len(tools_list.resources) == 0

    @pytest.mark.mcp
    @requires_scenario_servers
    def test_mcp_provider_connection_failure_unauthorized(self, syntara_api: SyntaraApiRegistry) -> None:
        """Test MCP integration validation fails when the server requires auth.

        Targets the long-lived mcp-server-scenarios auth-required endpoint
        (deployed by the e2e infrastructure) rather than starting a server
        in-process, so the backend reaches it via a real, environment-agnostic
        network name instead of host.containers.internal.
        """
        create_resp = _retry_api_call(
            lambda: syntara_api.integrations.create(
                body=IntegrationCreate(
                    name=unique_name("test-mcp-unauthorised"),
                    description="Test MCP integration with unauthorised user",
                    integration_type=IntegrationType.MCP_SERVER,
                    configuration=MCPServerConfigurationInput(base_url=MCP_AUTH_PROVIDER_URL, allow_http=True),
                ),
            )
        )
        integration = create_resp.assert_and_get()
        integration_id = integration.id
        assert integration.validation_status == IntegrationStatus.UNKNOWN

        validate_result = _validate_provider(syntara_api, integration_id).assert_and_get()
        assert isinstance(validate_result, ValidateResult)
        assert validate_result.success is False
        assert validate_result.error_type == HealthCheckErrorType.AUTH_FAILURE
        assert isinstance(validate_result.error, str)
        assert validate_result.error

        _wait_for_provider_status(syntara_api, integration_id, IntegrationStatus.ERROR)

        tools_list = syntara_api.tools.list(
            additional_params={"integration_id[eq]": str(integration_id)}
        ).assert_and_get()
        assert len(tools_list.resources) == 0

    @pytest.mark.mcp
    @requires_scenario_servers
    def test_mcp_provider_connection_failure_forbidden(self, syntara_api: SyntaraApiRegistry) -> None:
        """Test MCP integration validation fails when the server returns 403.

        Targets the long-lived mcp-server-scenarios forbidden endpoint
        (deployed by the e2e infrastructure) rather than starting a server
        in-process, so the backend reaches it via a real, environment-agnostic
        network name instead of host.containers.internal.
        """
        create_resp = _retry_api_call(
            lambda: syntara_api.integrations.create(
                body=IntegrationCreate(
                    name=unique_name("test-mcp-forbidden"),
                    description="Test MCP integration with forbidden user",
                    integration_type=IntegrationType.MCP_SERVER,
                    configuration=MCPServerConfigurationInput(base_url=MCP_FORBIDDEN_PROVIDER_URL, allow_http=True),
                ),
            )
        )
        integration = create_resp.assert_and_get()
        integration_id = integration.id
        assert integration.validation_status == IntegrationStatus.UNKNOWN

        validate_result = _validate_provider(syntara_api, integration_id).assert_and_get()
        assert isinstance(validate_result, ValidateResult)
        assert validate_result.success is False
        assert validate_result.error_type == HealthCheckErrorType.AUTH_FAILURE
        assert isinstance(validate_result.error, str)
        assert validate_result.error

        _wait_for_provider_status(syntara_api, integration_id, IntegrationStatus.ERROR)

        tools_list = syntara_api.tools.list(
            additional_params={"integration_id[eq]": str(integration_id)}
        ).assert_and_get()
        assert len(tools_list.resources) == 0
