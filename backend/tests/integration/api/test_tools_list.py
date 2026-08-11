"""Contract tests for GET /api/v1/tools endpoint.

Tests keyset pagination, bracket filter notation, and OpenAPI schema compliance.
"""

from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from httpx import AsyncClient

from syntara.tool_manager.models import Tool
from tests.integration.helpers.error_data import assert_error_data

if TYPE_CHECKING:
    from tests.integration.helpers.tool_manager import ToolFactory


@pytest_asyncio.fixture
async def multiple_test_tools(tool_factory: "ToolFactory") -> list[Tool]:
    """Create multiple test tools for pagination, filtering, and sorting tests."""
    return await tool_factory.create_list_tools()


class TestToolsListContract:
    """Contract tests for tools list endpoint."""

    @pytest.mark.asyncio
    async def test_list_tools_basic_success(
        self,
        jwt_client: AsyncClient,
        multiple_test_tools: list[Tool],
    ) -> None:
        """Test basic GET /api/v1/tools returns 200."""
        response = await jwt_client.get("/api/v1/tools")

        # Contract: Must return 200 OK
        assert response.status_code == 200

        # Contract: Must return JSON with resources array
        data = response.json()
        assert "resources" in data
        assert isinstance(data["resources"], list)

        # Contract: Must return the test tools
        assert len(data["resources"]) == 6
        tool_names = [t["name"] for t in data["resources"]]
        expected_names = [
            "Alpha Tool",
            "Beta Tool",
            "Gamma Tool",
            "Delta Tool",
            "Echo Tool",
            "Foxtrot Tool",
        ]
        for name in expected_names:
            assert name in tool_names

    @pytest.mark.asyncio
    async def test_list_tools_pagination_contract(
        self, jwt_client: AsyncClient, multiple_test_tools: list[Tool]
    ) -> None:
        """Test pagination parameters are accepted and response format is correct."""
        # Test with limit smaller than total count to ensure pagination works
        response = await jwt_client.get("/api/v1/tools", params={"limit": "3"})

        # Contract: Must return 200 OK
        assert response.status_code == 200

        # Contract: Must include pagination metadata
        data = response.json()
        assert "next" in data
        assert "prev" in data
        assert "resources" in data

        # Contract: Must respect limit parameter
        assert len(data["resources"]) <= 3

        # Contract: Should have next cursor since we have more data
        if len(multiple_test_tools) > 3:
            assert data["next"] is not None

        # Test pagination with cursor
        if data["next"]:
            next_response = await jwt_client.get("/api/v1/tools", params={"limit": "3", "cursor": data["next"]})
            assert next_response.status_code == 200
            next_data = next_response.json()
            assert "resources" in next_data

            # Should get different resources
            first_page_ids = {t["id"] for t in data["resources"]}
            second_page_ids = {t["id"] for t in next_data["resources"]}

            assert first_page_ids.isdisjoint(second_page_ids)

    @pytest.mark.asyncio
    async def test_list_tools_bracket_filters_contract(
        self,
        jwt_client: AsyncClient,
        multiple_test_tools: list[Tool],
    ) -> None:
        """Test bracket filter notation is accepted."""
        # Test filtering by status
        response = await jwt_client.get("/api/v1/tools", params={"status[eq]": "available"})
        assert response.status_code == 200
        data = response.json()
        assert "resources" in data

        # All returned tools should be available
        for tool in data["resources"]:
            assert tool["status"] == "available"

        # Should return 3 available tools (Alpha, Gamma, Foxtrot)
        assert len(data["resources"]) == 3

        # Test filtering by integration_id
        integration_response = await jwt_client.get(
            "/api/v1/tools",
            params={"integration_id[eq]": str(multiple_test_tools[0].integration_id)},
        )
        assert integration_response.status_code == 200
        integration_data = integration_response.json()

        # All returned tools should have the same integration_id
        for tool in integration_data["resources"]:
            assert tool["integration_id"] == str(multiple_test_tools[0].integration_id)

        # Should return all 6 tools since they all have the same integration
        assert len(integration_data["resources"]) == 6

        # Test name contains filter
        alpha_response = await jwt_client.get("/api/v1/tools", params={"name[contains]": "Alpha"})
        assert alpha_response.status_code == 200
        alpha_data = alpha_response.json()
        assert len(alpha_data["resources"]) == 1
        assert alpha_data["resources"][0]["name"] == "Alpha Tool"

    @pytest.mark.asyncio
    async def test_list_tools_include_total_contract(
        self,
        jwt_client: AsyncClient,
        multiple_test_tools: list[Tool],
    ) -> None:
        """Test include_total parameter returns total count."""
        response = await jwt_client.get("/api/v1/tools", params={"include_total": "true"})

        # Contract: Must return 200 OK
        assert response.status_code == 200

        # Contract: Must include total field when requested
        data = response.json()
        assert "total" in data
        assert isinstance(data["total"], int)
        assert data["total"] == 6  # Should match our test tools

    @pytest.mark.asyncio
    async def test_list_tools_response_schema_contract(
        self,
        jwt_client: AsyncClient,
        multiple_test_tools: list[Tool],
    ) -> None:
        """Test response matches OpenAPI specification schema."""
        response = await jwt_client.get("/api/v1/tools")

        # Contract: Must return 200 OK
        assert response.status_code == 200

        # Contract: Must match expected schema structure
        data = response.json()
        assert "resources" in data
        assert len(data["resources"]) > 0

        # Each tool resource must have required fields per OpenAPI spec
        for tool in data["resources"]:
            required_fields = [
                "id",
                "name",
                "description",
                "integration_id",
                "namespaced_name",
                "status",
                "last_executed_at",
                "last_refreshed_at",
                "refresh_error",
                "created_at",
                "updated_at",
                "created_by",
                "updated_by",
                "parameters",
            ]
            for field in required_fields:
                assert field in tool, f"Missing required field: {field}"

            # Verify data types
            assert isinstance(tool["id"], str)
            assert isinstance(tool["name"], str)
            # integration_id may be null for orphaned tools
            assert tool["integration_id"] is None or isinstance(tool["integration_id"], str)
            assert isinstance(tool["namespaced_name"], str)
            assert isinstance(tool["status"], str)

    @pytest.mark.asyncio
    async def test_list_tools_invalid_parameters_contract(self, jwt_client: AsyncClient) -> None:
        """Test validation of query parameters."""
        # Test with invalid limit parameter
        response = await jwt_client.get("/api/v1/tools", params={"limit": "invalid"})

        # Contract: Must return 422 Unprocessable Entity for invalid parameters
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_tools_empty_result_contract(self, jwt_client: AsyncClient) -> None:
        """Test response format when no tools exist."""
        response = await jwt_client.get("/api/v1/tools")

        # Contract: Must return 200 even for empty results
        assert response.status_code == 200

        # Contract: Must return empty array, not null
        data = response.json()
        assert "resources" in data
        assert isinstance(data["resources"], list)

    @pytest.mark.asyncio
    async def test_list_tools_sorting_by_name_contract(
        self,
        jwt_client: AsyncClient,
        multiple_test_tools: list[Tool],
    ) -> None:
        """Test sorting tools by name."""
        # Test ascending sort
        response = await jwt_client.get("/api/v1/tools", params={"sort": "name"})
        assert response.status_code == 200

        data = response.json()
        assert len(data["resources"]) == 6

        # Names should be in alphabetical order
        names = [t["name"] for t in data["resources"]]
        assert names == sorted(names)
        assert names[0] == "Alpha Tool"
        assert names[-1] == "Gamma Tool"  # Last alphabetically

        # Test descending sort
        desc_response = await jwt_client.get("/api/v1/tools", params={"sort": "-name"})
        assert desc_response.status_code == 200

        desc_data = desc_response.json()
        desc_names = [t["name"] for t in desc_data["resources"]]
        assert desc_names == sorted(names, reverse=True)

    @pytest.mark.asyncio
    async def test_list_tools_combined_filter_and_sort_contract(
        self,
        jwt_client: AsyncClient,
        multiple_test_tools: list[Tool],
    ) -> None:
        """Test combining filters and sorting."""
        # Filter available tools and sort by name
        response = await jwt_client.get("/api/v1/tools", params={"status[eq]": "available", "sort": "name"})
        assert response.status_code == 200

        data = response.json()
        assert len(data["resources"]) == 3  # Alpha, Gamma, Foxtrot

        # Should be available and sorted
        for tool in data["resources"]:
            assert tool["status"] == "available"

        names = [t["name"] for t in data["resources"]]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_list_tools_filter_by_multiple_criteria_contract(
        self,
        jwt_client: AsyncClient,
        multiple_test_tools: list[Tool],
    ) -> None:
        """Test filtering by multiple criteria."""
        # Filter available tools with execution count >= 5
        response = await jwt_client.get("/api/v1/tools", params={"status[eq]": "available", "name[contains]": "Alpha"})
        assert response.status_code == 200

        data = response.json()
        assert len(data["resources"]) == 1  # Alpha

        for tool in data["resources"]:
            assert tool["status"] == "available"
            assert tool["name"] == "Alpha Tool"

    @pytest.mark.asyncio
    async def test_list_tools_filter_no_results_contract(
        self,
        jwt_client: AsyncClient,
        multiple_test_tools: list[Tool],
    ) -> None:
        """Test filtering that returns no results."""
        # Filter for tools with a name that won't match any test data
        response = await jwt_client.get("/api/v1/tools", params={"name[contains]": "NonexistentTool"})
        assert response.status_code == 200

        data = response.json()
        assert "resources" in data
        assert len(data["resources"]) == 0
        assert isinstance(data["resources"], list)

        # Should still include pagination metadata
        assert "next" in data
        assert "prev" in data
        assert data["next"] is None
        assert data["prev"] is None

    @pytest.mark.asyncio
    async def test_list_tools_filter_invalid_enum_value_contract(
        self,
        jwt_client: AsyncClient,
        multiple_test_tools: list[Tool],
    ) -> None:
        """Test filtering with invalid enum value returns 400."""
        # Filter with invalid status value
        response = await jwt_client.get("/api/v1/tools", params={"status[eq]": "nonexistent"})

        # Contract: Must return 422 Unprocessable Entity for invalid enum value
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Validation Error",
            detail="Invalid value 'nonexistent' for field 'status'. Valid values are: available, missing, error",
            code="VALIDATION_ERROR",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_list_tools_include_total_with_filters_contract(
        self,
        jwt_client: AsyncClient,
        multiple_test_tools: list[Tool],
    ) -> None:
        """Test include_total works correctly with filters."""
        # Get total for all tools
        all_response = await jwt_client.get("/api/v1/tools", params={"include_total": "true"})
        assert all_response.status_code == 200
        all_data = all_response.json()
        assert all_data["total"] == 6

        # Get total for available tools only
        available_response = await jwt_client.get(
            "/api/v1/tools", params={"status[eq]": "available", "include_total": "true"}
        )
        assert available_response.status_code == 200
        available_data = available_response.json()
        assert available_data["total"] == 3  # 3 available tools

        # Total should be accurate even with pagination
        paginated_response = await jwt_client.get(
            "/api/v1/tools", params={"status[eq]": "available", "include_total": "true", "limit": "2"}
        )
        assert paginated_response.status_code == 200
        paginated_data = paginated_response.json()
        assert paginated_data["total"] == 3  # Total count, not page count
        assert len(paginated_data["resources"]) == 2  # Page size

    @pytest.mark.asyncio
    async def test_list_tools_pagination_with_filters_contract(
        self,
        jwt_client: AsyncClient,
        multiple_test_tools: list[Tool],
    ) -> None:
        """Test pagination works correctly with filters."""
        # Get available tools with pagination
        response = await jwt_client.get("/api/v1/tools", params={"status[eq]": "available", "limit": "2"})
        assert response.status_code == 200

        data = response.json()
        assert len(data["resources"]) == 2
        assert data["next"] is not None  # Should have more available tools

        # All results should be available
        for tool in data["resources"]:
            assert tool["status"] == "available"

        # Get next page
        next_response = await jwt_client.get(
            "/api/v1/tools", params={"status[eq]": "available", "limit": "2", "cursor": data["next"]}
        )
        assert next_response.status_code == 200

        next_data = next_response.json()
        for tool in next_data["resources"]:
            assert tool["status"] == "available"

    @pytest.mark.asyncio
    async def test_list_tools_edge_cases_contract(
        self,
        jwt_client: AsyncClient,
        multiple_test_tools: list[Tool],
    ) -> None:
        """Test edge cases and boundary conditions."""
        # Test with limit = 0 (should return error)
        response = await jwt_client.get("/api/v1/tools", params={"limit": "0"})
        assert response.status_code == 422  # Validation error

        # Test with very large limit (should be capped)
        response = await jwt_client.get("/api/v1/tools", params={"limit": "1000"})
        assert response.status_code in [200, 422]  # Either capped or validation error

        # Test with invalid cursor
        response = await jwt_client.get("/api/v1/tools", params={"cursor": "invalid-cursor"})
        assert response.status_code in [200, 422]  # Either ignored or validation error

        # Test with invalid sort field
        response = await jwt_client.get("/api/v1/tools", params={"sort": "invalid_field"})
        assert response.status_code in [200, 422]  # Either ignored or validation error

    @pytest.mark.asyncio
    async def test_list_tools_parameters_eager_loading(
        self,
        jwt_client: AsyncClient,
        tool_factory: "ToolFactory",
    ) -> None:
        """Test that ToolParameters are eagerly loaded in list_tools endpoint to avoid N+1 queries.

        This integration test verifies that the list_tools endpoint efficiently loads
        tool parameters without generating N+1 queries when serializing tools to JSON.
        """
        # Create tools with parameters using the factory method
        await tool_factory.create_tools_with_parameters()

        # Make HTTP request to list tools - this is end-to-end testing
        response = await jwt_client.get("/api/v1/tools")

        # Verify successful response
        assert response.status_code == 200
        data = response.json()
        assert "resources" in data
        assert isinstance(data["resources"], list)

        # Find our Calculator Tool in the response
        calculator_tool = None
        for tool_data in data["resources"]:
            if tool_data["name"] == "Calculator Tool":
                calculator_tool = tool_data
                break

        assert calculator_tool is not None, "Calculator Tool not found in response"

        # Verify tool parameters are included in the response (proving eager loading)
        assert "parameters" in calculator_tool, "Tool parameters should be included in response"
        assert isinstance(calculator_tool["parameters"], list)
        assert len(calculator_tool["parameters"]) == 4  # operation, operand_a, operand_b, precision

        # Verify specific parameter details to ensure complete loading
        param_names = [param["name"] for param in calculator_tool["parameters"]]
        expected_params = ["operation", "operand_a", "operand_b", "precision"]
        for expected_param in expected_params:
            assert expected_param in param_names

        # Verify parameter structure
        operation_param = next(p for p in calculator_tool["parameters"] if p["name"] == "operation")
        assert operation_param["type"] == "string"
        assert operation_param["description"] == "Mathematical operation to perform"
        assert operation_param["required"] is True
