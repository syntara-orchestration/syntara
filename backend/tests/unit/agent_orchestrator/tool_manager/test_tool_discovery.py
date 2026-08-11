"""Tests for ToolManagerClient MCP integration discovery functionality."""

from typing import Any
from uuid import uuid4

import httpx
import pytest
import respx

from syntara.agent_orchestrator.tool_manager.tool_manager_client import ToolManagerClient
from syntara.integrations.models.integration import IntegrationRead, IntegrationStatus, IntegrationType

from .conftest import mock_paginated_api


def _make_integration_response(
    name: str = "test_integration",
    *,
    enabled: bool = True,
    status: str = "available",
) -> dict[str, Any]:
    """Create a sample integration response dict."""
    return {
        "id": str(uuid4()),
        "name": name,
        "description": "Test integration for unit tests",
        "integration_type": "mcp_server",
        "enabled": enabled,
        "validation_status": status,
        "configuration": {
            "integration_type": "mcp_server",
            "base_url": "http://localhost:3000",
        },
        "scope": "global",
        "management_credential_id": None,
        "last_validated_at": None,
        "validation_error": None,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "created_by": str(uuid4()),
        "updated_by": None,
        "labels": {},
    }


class TestMCPIntegrationDiscovery:
    """Test MCP integration discovery scenarios."""

    @pytest.fixture
    def sample_integration_response(self) -> dict[str, Any]:
        """Sample integration response from Integrations API."""
        return _make_integration_response()

    @pytest.fixture
    def client(self) -> ToolManagerClient:
        """Create client instance for testing."""
        return ToolManagerClient(base_url="http://test-api/api/v1", timeout=30.0)

    @respx.mock
    async def test_get_all_mcp_integrations_success(
        self, client: ToolManagerClient, sample_integration_response: dict[str, Any]
    ) -> None:
        """Test successful retrieval of all MCP integrations."""
        respx.get("http://test-api/api/v1/integrations").mock(
            return_value=httpx.Response(
                200, json={"resources": [sample_integration_response], "total_count": 1, "next": None}
            )
        )

        integrations = await client.get_all_mcp_integrations()

        assert len(integrations) == 1
        integration = integrations[0]
        assert isinstance(integration, IntegrationRead)
        assert integration.name == "test_integration"
        assert integration.enabled is True
        assert integration.validation_status == IntegrationStatus.AVAILABLE
        assert integration.integration_type == IntegrationType.MCP_SERVER

    @respx.mock
    async def test_get_all_mcp_integrations_filters_by_type(self, client: ToolManagerClient) -> None:
        """Test that integrations request includes mcp_server type filter."""
        respx.get("http://test-api/api/v1/integrations").mock(
            return_value=httpx.Response(200, json={"resources": [], "total_count": 0})
        )

        await client.get_all_mcp_integrations()

        # Verify the API was called with integration_type filter
        request = respx.calls.last.request
        assert "integration_type=mcp_server" in str(request.url)

    @respx.mock
    async def test_get_all_mcp_integrations_empty_response(self, client: ToolManagerClient) -> None:
        """Test handling of empty integration list."""
        respx.get("http://test-api/api/v1/integrations").mock(
            return_value=httpx.Response(200, json={"resources": [], "total_count": 0})
        )

        integrations = await client.get_all_mcp_integrations()

        assert integrations == []

    @respx.mock
    @pytest.mark.usefixtures("fast_retry_settings")
    async def test_get_all_mcp_integrations_api_error(self, client: ToolManagerClient) -> None:
        """Test handling of API errors during integration discovery."""
        respx.get("http://test-api/api/v1/integrations").mock(
            return_value=httpx.Response(500, text="Internal server error")
        )

        with pytest.raises(httpx.HTTPStatusError):
            await client.get_all_mcp_integrations()

    @respx.mock
    @pytest.mark.usefixtures("fast_retry_settings")
    async def test_get_all_mcp_integrations_timeout(self, client: ToolManagerClient) -> None:
        """Test handling of timeout during integration discovery."""
        respx.get("http://test-api/api/v1/integrations").mock(side_effect=httpx.TimeoutException("Request timeout"))

        with pytest.raises(httpx.TimeoutException):
            await client.get_all_mcp_integrations()

    @respx.mock
    @pytest.mark.usefixtures("fast_retry_settings")
    async def test_get_all_mcp_integrations_network_error(self, client: ToolManagerClient) -> None:
        """Test handling of network errors during integration discovery."""
        respx.get("http://test-api/api/v1/integrations").mock(side_effect=httpx.ConnectError("Connection failed"))

        with pytest.raises(httpx.ConnectError):
            await client.get_all_mcp_integrations()

    async def test_get_all_mcp_integrations_pagination(self, client: ToolManagerClient) -> None:
        """Test handling of paginated integration responses."""
        page1 = [_make_integration_response("integration_1")]
        page2 = [_make_integration_response("integration_2")]

        pages = [
            {"resources": page1, "total_count": 2, "next": "cursor_123"},
            {"resources": page2, "total_count": 2, "next": None},
        ]

        with mock_paginated_api(r".*integrations.*", pages):
            integrations = await client.get_all_mcp_integrations()

        assert len(integrations) == 2
        assert integrations[0].name == "integration_1"
        assert integrations[1].name == "integration_2"
