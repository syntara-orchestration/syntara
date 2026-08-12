"""Integration tests for OR logic filtering functionality.

Tests the end-to-end filtering functionality from HTTP GET through FastAPI router
to the service layer, covering the OR logic implementation for comma-separated values.
Uses the /tools endpoint.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.tool_manager.models.tool import Tool, ToolStatus


@pytest_asyncio.fixture
async def filtering_test_tools(
    test_db_session: AsyncSession,
    test_mcp_integration,
    test_user: User,
) -> list[Tool]:
    """Create test tools specifically for OR filtering tests."""
    tools = [
        Tool(
            name="Alpha Service",
            description="Development service for testing",
            namespaced_name="test::alpha_service",
            integration_id=test_mcp_integration.id,
            enabled=True,
            status=ToolStatus.AVAILABLE,
            created_by=test_user.id,
            updated_by=test_user.id,
        ),
        Tool(
            name="Beta Service",
            description="Production service for testing",
            namespaced_name="test::beta_service",
            integration_id=test_mcp_integration.id,
            enabled=False,
            status=ToolStatus.MISSING,
            created_by=test_user.id,
            updated_by=test_user.id,
        ),
        Tool(
            name="Gamma Service",
            description="Staging service for testing",
            namespaced_name="test::gamma_service",
            integration_id=test_mcp_integration.id,
            enabled=True,
            status=ToolStatus.AVAILABLE,
            created_by=test_user.id,
            updated_by=test_user.id,
        ),
        Tool(
            name="Delta Provider",
            description="Development provider for testing",
            namespaced_name="test::delta_provider",
            integration_id=test_mcp_integration.id,
            enabled=True,
            status=ToolStatus.AVAILABLE,
            created_by=test_user.id,
            updated_by=test_user.id,
        ),
        Tool(
            name="Echo Provider",
            description="Production provider for testing",
            namespaced_name="test::echo_provider",
            integration_id=test_mcp_integration.id,
            enabled=False,
            status=ToolStatus.MISSING,
            created_by=test_user.id,
            updated_by=test_user.id,
        ),
        Tool(
            name="Foxtrot Provider",
            description="Staging provider for testing",
            namespaced_name="test::foxtrot_provider",
            integration_id=test_mcp_integration.id,
            enabled=True,
            status=ToolStatus.AVAILABLE,
            created_by=test_user.id,
            updated_by=test_user.id,
        ),
    ]

    for tool in tools:
        test_db_session.add(tool)

    await test_db_session.commit()

    for tool in tools:
        await test_db_session.refresh(tool)

    return tools


class TestFilteringORLogic:
    """Integration tests for OR logic filtering functionality."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("filtering_test_tools")
    async def test_single_field_filtering(
        self,
        jwt_client: AsyncClient,
    ) -> None:
        """Test filtering on a single field with single value."""
        response = await jwt_client.get("/api/v1/tools", params={"enabled[eq]": "true"})

        assert response.status_code == 200
        data = response.json()
        assert "resources" in data

        # Should return 4 enabled tools (Alpha, Gamma, Delta, Foxtrot)
        assert len(data["resources"]) == 4

        enabled_names = {tool["name"] for tool in data["resources"]}
        expected_enabled = {"Alpha Service", "Gamma Service", "Delta Provider", "Foxtrot Provider"}
        assert enabled_names == expected_enabled

        # All returned tools should be enabled
        for tool in data["resources"]:
            assert tool["enabled"] is True

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("filtering_test_tools")
    async def test_multiple_fields_and_logic(
        self,
        jwt_client: AsyncClient,
    ) -> None:
        """Test filtering on multiple fields using AND logic."""
        response = await jwt_client.get(
            "/api/v1/tools",
            params={"enabled[eq]": "true", "description[contains]": "Development"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "resources" in data

        # Should return 2 tools (Alpha and Delta) - enabled AND Development in description
        assert len(data["resources"]) == 2

        returned_names = {tool["name"] for tool in data["resources"]}
        expected_names = {"Alpha Service", "Delta Provider"}
        assert returned_names == expected_names

        # All returned tools should meet both criteria
        for tool in data["resources"]:
            assert tool["enabled"] is True
            assert "Development" in tool["description"]

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("filtering_test_tools")
    async def test_single_field_or_logic(
        self,
        jwt_client: AsyncClient,
    ) -> None:
        """Test filtering on a single field using OR logic (comma-separated values)."""
        response = await jwt_client.get("/api/v1/tools", params={"name[contains]": "Service,Provider"})

        assert response.status_code == 200
        data = response.json()
        assert "resources" in data

        # Should return all 6 tools - name contains "Service" OR "Provider"
        assert len(data["resources"]) == 6

        returned_names = {tool["name"] for tool in data["resources"]}
        expected_names = {
            "Alpha Service",
            "Beta Service",
            "Gamma Service",
            "Delta Provider",
            "Echo Provider",
            "Foxtrot Provider",
        }
        assert returned_names == expected_names

        # All returned tools should have either "Service" or "Provider" in name
        for tool in data["resources"]:
            assert "Service" in tool["name"] or "Provider" in tool["name"]

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("filtering_test_tools")
    async def test_multiple_fields_mixed_logic(
        self,
        jwt_client: AsyncClient,
    ) -> None:
        """Test filtering with one field using OR and another using AND."""
        response = await jwt_client.get(
            "/api/v1/tools",
            params={
                "name[contains]": "Service,Delta",  # OR logic within this field
                "enabled[eq]": "true",  # AND logic between fields
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "resources" in data

        # Should return 3 tools: Alpha Service, Gamma Service, Delta Provider
        # (name contains "Service" OR "Delta") AND enabled=true
        assert len(data["resources"]) == 3

        returned_names = {tool["name"] for tool in data["resources"]}
        expected_names = {"Alpha Service", "Gamma Service", "Delta Provider"}
        assert returned_names == expected_names

        # All returned tools should be enabled AND have "Service" OR "Delta" in name
        for tool in data["resources"]:
            assert tool["enabled"] is True
            assert "Service" in tool["name"] or "Delta" in tool["name"]

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("filtering_test_tools")
    async def test_in_operator_single_field(
        self,
        jwt_client: AsyncClient,
    ) -> None:
        """Test filtering with the [in] operator for multi-value OR logic."""
        response = await jwt_client.get("/api/v1/tools", params={"status[in]": "available,missing"})

        assert response.status_code == 200
        data = response.json()
        assert "resources" in data

        # All 6 test tools are either available or missing, so all should match
        assert len(data["resources"]) == 6

        for tool in data["resources"]:
            assert tool["status"] in ("available", "missing")

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("filtering_test_tools")
    async def test_in_operator_combined_with_and(
        self,
        jwt_client: AsyncClient,
    ) -> None:
        """Test [in] operator combined with another filter using AND logic."""
        response = await jwt_client.get(
            "/api/v1/tools",
            params={
                "status[in]": "available,missing",
                "enabled[eq]": "true",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "resources" in data

        # 4 enabled tools (Alpha, Gamma, Delta, Foxtrot) - all are available
        assert len(data["resources"]) == 4

        for tool in data["resources"]:
            assert tool["enabled"] is True
            assert tool["status"] in ("available", "missing")

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("filtering_test_tools")
    async def test_in_operator_single_value(
        self,
        jwt_client: AsyncClient,
    ) -> None:
        """Test [in] operator with a single value behaves like equality."""
        response = await jwt_client.get("/api/v1/tools", params={"status[in]": "missing"})

        assert response.status_code == 200
        data = response.json()
        assert "resources" in data

        # Beta and Echo are the only tools with status=missing
        assert len(data["resources"]) == 2

        returned_names = {tool["name"] for tool in data["resources"]}
        assert returned_names == {"Beta Service", "Echo Provider"}

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("filtering_test_tools")
    async def test_multiple_fields_both_with_or_logic(
        self,
        jwt_client: AsyncClient,
    ) -> None:
        """Test filtering with multiple fields each using OR logic."""
        response = await jwt_client.get(
            "/api/v1/tools",
            params={
                "name[contains]": "Alpha,Echo",  # OR within field
                "description[contains]": "Development,Production",  # OR within field, AND between fields
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "resources" in data

        # Should return tools that have (Alpha OR Echo in name) AND (Development OR Production in description)
        # Alpha Service: name has "Alpha" + description has "Development" ✓
        # Echo Provider: name has "Echo" + description has "Production" ✓
        # Beta Service: name doesn't have "Alpha" or "Echo" ✗
        assert len(data["resources"]) == 2

        returned_names = {tool["name"] for tool in data["resources"]}
        expected_names = {"Alpha Service", "Echo Provider"}
        assert returned_names == expected_names

        # All returned tools should meet the criteria
        valid_name_parts = {"Alpha", "Echo"}
        valid_desc_parts = {"Development", "Production"}
        for tool in data["resources"]:
            has_valid_name = any(part in tool["name"] for part in valid_name_parts)
            has_valid_desc = any(part in tool["description"] for part in valid_desc_parts)
            assert has_valid_name
            assert has_valid_desc
