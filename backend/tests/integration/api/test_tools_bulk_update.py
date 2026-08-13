"""Contract tests for PATCH /api/v1/integrations/{integration_id}/tools/bulk_update endpoint.

Tests bulk tool status updates, validation, and response format.
"""

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient

from syntara.tool_manager.models import Tool

if TYPE_CHECKING:
    from tests.integration.helpers.tool_manager import ToolFactory


@pytest_asyncio.fixture
async def multiple_tools_for_bulk(tool_factory: "ToolFactory") -> list[Tool]:
    """Create multiple test tools for bulk update tests."""
    return await tool_factory.create_bulk_tools(count=3)


class TestToolsBulkUpdateContract:
    """Contract tests for tools bulk update endpoint."""

    @pytest.mark.asyncio
    async def test_bulk_update_disable_success_contract(
        self, jwt_client: AsyncClient, multiple_tools_for_bulk: list[Tool]
    ) -> None:
        """Test successful bulk disable returns 200."""
        tool_ids = [str(tool.id) for tool in multiple_tools_for_bulk[:2]]
        integration_id = multiple_tools_for_bulk[0].integration_id

        response = await jwt_client.patch(
            f"/api/v1/integrations/{integration_id}/tools/bulk_update", json={"tool_ids": tool_ids, "enabled": False}
        )

        # Contract: Must return 200 OK for successful bulk update
        assert response.status_code == 200

        # Contract: Must return update statistics
        data = response.json()
        assert "updated_count" in data
        assert "skipped_count" in data
        assert "updated_at" in data

        # Should update 2 existing tools
        assert data["updated_count"] == 2
        assert data["skipped_count"] == 0

    @pytest.mark.asyncio
    async def test_bulk_update_enable_success_contract(
        self, jwt_client: AsyncClient, multiple_tools_for_bulk: list[Tool]
    ) -> None:
        """Test successful bulk enable returns 200."""
        # Use the disabled tool
        tool_ids = [str(multiple_tools_for_bulk[2].id)]
        integration_id = multiple_tools_for_bulk[0].integration_id

        response = await jwt_client.patch(
            f"/api/v1/integrations/{integration_id}/tools/bulk_update", json={"tool_ids": tool_ids, "enabled": True}
        )

        # Contract: Must return 200 OK
        assert response.status_code == 200

        # Contract: Must return update statistics
        data = response.json()
        assert data["updated_count"] == 1
        assert data["skipped_count"] == 0

    @pytest.mark.asyncio
    async def test_bulk_update_mixed_existing_nonexistent_contract(
        self, jwt_client: AsyncClient, multiple_tools_for_bulk: list[Tool]
    ) -> None:
        """Test bulk update with mix of existing and non-existent tool IDs."""
        existing_id = str(multiple_tools_for_bulk[0].id)
        nonexistent_ids = [str(uuid4()), str(uuid4())]
        tool_ids = [existing_id, *nonexistent_ids]
        integration_id = multiple_tools_for_bulk[0].integration_id

        response = await jwt_client.patch(
            f"/api/v1/integrations/{integration_id}/tools/bulk_update", json={"tool_ids": tool_ids, "enabled": False}
        )

        # Contract: Must return 200 OK (partial success)
        assert response.status_code == 200

        # Contract: Must return accurate statistics
        data = response.json()
        assert data["updated_count"] == 1  # Only the existing tool
        assert data["skipped_count"] == 2  # Two non-existent tools

    @pytest.mark.asyncio
    async def test_bulk_update_empty_tool_ids_contract(
        self, jwt_client: AsyncClient, multiple_tools_for_bulk: list[Tool]
    ) -> None:
        """Test bulk update with empty tool_ids list returns 422."""
        integration_id = multiple_tools_for_bulk[0].integration_id
        response = await jwt_client.patch(
            f"/api/v1/integrations/{integration_id}/tools/bulk_update", json={"tool_ids": [], "enabled": False}
        )

        # Contract: Must return 422 Unprocessable Entity for validation failure
        assert response.status_code == 422

        # Contract: Must return validation error details
        data = response.json()
        assert "detail" in data
        # Pydantic validation error message may vary but should indicate empty list issue
        assert isinstance(data["detail"], list) or "cannot be empty" in str(data["detail"])

    @pytest.mark.asyncio
    async def test_bulk_update_too_many_tools_contract(
        self, jwt_client: AsyncClient, multiple_tools_for_bulk: list[Tool]
    ) -> None:
        """Test bulk update with more than 50 tools returns 422."""
        # Create list of 51 tool IDs
        tool_ids = [str(uuid4()) for _ in range(51)]

        integration_id = multiple_tools_for_bulk[0].integration_id
        response = await jwt_client.patch(
            f"/api/v1/integrations/{integration_id}/tools/bulk_update", json={"tool_ids": tool_ids, "enabled": False}
        )

        # Contract: Must return 422 Unprocessable Entity for validation failure
        assert response.status_code == 422

        # Contract: Must return validation error details
        data = response.json()
        assert "detail" in data
        # Pydantic validation error for max_length or custom validator
        assert isinstance(data["detail"], list) or "50" in str(data["detail"])

    @pytest.mark.asyncio
    async def test_bulk_update_missing_required_fields_contract(
        self, jwt_client: AsyncClient, multiple_tools_for_bulk: list[Tool]
    ) -> None:
        """Test bulk update with missing required fields returns 422."""
        dummy_integration_id = multiple_tools_for_bulk[0].integration_id

        # Missing status field
        response = await jwt_client.patch(
            f"/api/v1/integrations/{dummy_integration_id}/tools/bulk_update",
            json={
                "tool_ids": [str(uuid4())]
                # Missing enabled
            },
        )

        # Contract: Must return 422 for missing required fields
        assert response.status_code == 422

        # Missing tool_ids field
        response = await jwt_client.patch(
            f"/api/v1/integrations/{dummy_integration_id}/tools/bulk_update",
            json={
                "enabled": False
                # Missing tool_ids
            },
        )

        # Contract: Must return 422 for missing required fields
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_bulk_update_invalid_uuid_format_contract(
        self, jwt_client: AsyncClient, multiple_tools_for_bulk: list[Tool]
    ) -> None:
        """Test bulk update with invalid UUID format returns 422."""
        integration_id = multiple_tools_for_bulk[0].integration_id
        response = await jwt_client.patch(
            f"/api/v1/integrations/{integration_id}/tools/bulk_update",
            json={"tool_ids": ["not-a-valid-uuid", "also-invalid"], "enabled": False},
        )

        # Contract: Must return 422 for invalid UUID format
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_bulk_update_response_format_contract(
        self, jwt_client: AsyncClient, multiple_tools_for_bulk: list[Tool]
    ) -> None:
        """Test bulk update response has correct format."""
        tool_ids = [str(tool.id) for tool in multiple_tools_for_bulk[:2]]
        integration_id = multiple_tools_for_bulk[0].integration_id

        response = await jwt_client.patch(
            f"/api/v1/integrations/{integration_id}/tools/bulk_update", json={"tool_ids": tool_ids, "enabled": False}
        )

        # Contract: Must return 200 OK
        assert response.status_code == 200

        # Contract: Must return statistics with correct types
        data = response.json()
        assert isinstance(data["updated_count"], int)
        assert isinstance(data["skipped_count"], int)
        assert isinstance(data["updated_at"], str)

        # Contract: Counts should sum to total requested
        assert data["updated_count"] + data["skipped_count"] == len(tool_ids)

    @pytest.mark.asyncio
    async def test_bulk_update_idempotent_contract(
        self, jwt_client: AsyncClient, multiple_tools_for_bulk: list[Tool]
    ) -> None:
        """Test bulk update is idempotent."""
        tool_ids = [str(multiple_tools_for_bulk[0].id)]
        integration_id = multiple_tools_for_bulk[0].integration_id

        # First update
        response1 = await jwt_client.patch(
            f"/api/v1/integrations/{integration_id}/tools/bulk_update", json={"tool_ids": tool_ids, "enabled": False}
        )
        assert response1.status_code == 200

        # Second update with same status
        response2 = await jwt_client.patch(
            f"/api/v1/integrations/{integration_id}/tools/bulk_update", json={"tool_ids": tool_ids, "enabled": False}
        )

        # Contract: Should succeed even if already in target state
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["updated_count"] == 1  # Still counts as updated

    @pytest.mark.asyncio
    async def test_bulk_update_case_insensitivity_contract(
        self, jwt_client: AsyncClient, multiple_tools_for_bulk: list[Tool]
    ) -> None:
        """Test status values are case-insensitive."""
        tool_ids = [str(multiple_tools_for_bulk[0].id)]
        integration_id = multiple_tools_for_bulk[0].integration_id

        # Test with incorrect case
        response = await jwt_client.patch(
            f"/api/v1/integrations/{integration_id}/tools/bulk_update",
            json={
                "tool_ids": tool_ids,
                "enabled": "FALSE",
            },
        )

        # Contract: Should accept any case
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_bulk_update_invalid_json_contract(self, jwt_client: AsyncClient) -> None:
        """Test bulk update with invalid JSON returns 422."""
        response = await jwt_client.patch(
            f"/api/v1/integrations/{uuid4()}/tools/bulk_update",
            content="invalid json",
            headers={"Content-Type": "application/json"},
        )

        # Contract: Must return 422 for invalid JSON
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_bulk_update_content_type_contract(
        self, jwt_client: AsyncClient, multiple_tools_for_bulk: list[Tool]
    ) -> None:
        """Test response has correct content type."""
        tool_ids = [str(multiple_tools_for_bulk[0].id)]
        integration_id = multiple_tools_for_bulk[0].integration_id

        response = await jwt_client.patch(
            f"/api/v1/integrations/{integration_id}/tools/bulk_update", json={"tool_ids": tool_ids, "enabled": False}
        )

        # Contract: Must return 200 OK
        assert response.status_code == 200

        # Contract: Must return JSON content type
        assert response.headers["content-type"].startswith("application/json")

    @pytest.mark.asyncio
    async def test_bulk_update_max_limit_boundary_contract(
        self, jwt_client: AsyncClient, multiple_tools_for_bulk: list[Tool]
    ) -> None:
        """Test bulk update at the 50 tool limit."""
        # Create exactly 50 tool IDs (mix of existing and non-existing)
        existing_ids = [str(tool.id) for tool in multiple_tools_for_bulk]
        additional_ids = [str(uuid4()) for _ in range(50 - len(existing_ids))]
        tool_ids = existing_ids + additional_ids
        integration_id = multiple_tools_for_bulk[0].integration_id

        response = await jwt_client.patch(
            f"/api/v1/integrations/{integration_id}/tools/bulk_update", json={"tool_ids": tool_ids, "enabled": False}
        )

        # Contract: Should accept exactly 50 tools
        assert response.status_code == 200

        # Contract: Should return accurate statistics
        data = response.json()
        assert data["updated_count"] == len(existing_ids)
        assert data["skipped_count"] == len(additional_ids)

    @pytest.mark.asyncio
    async def test_bulk_update_unknown_fields_contract(
        self, jwt_client: AsyncClient, multiple_tools_for_bulk: list[Tool]
    ) -> None:
        """Test bulk update with unknown fields."""
        tool_ids = [str(multiple_tools_for_bulk[0].id)]
        integration_id = multiple_tools_for_bulk[0].integration_id

        response = await jwt_client.patch(
            f"/api/v1/integrations/{integration_id}/tools/bulk_update",
            json={"tool_ids": tool_ids, "enabled": False, "unknown_field": "value"},
        )

        # Contract: Should either accept (ignoring unknown fields) or reject
        assert response.status_code in [200, 422]

        if response.status_code == 200:
            # If accepted, should still perform the update correctly
            data = response.json()
            assert data["updated_count"] == 1

    @pytest.mark.asyncio
    async def test_bulk_update_duplicate_tool_ids_contract(
        self, jwt_client: AsyncClient, multiple_tools_for_bulk: list[Tool]
    ) -> None:
        """Test bulk update with duplicate tool IDs."""
        tool_id = str(multiple_tools_for_bulk[0].id)
        tool_ids = [tool_id, tool_id, tool_id]  # Same ID repeated
        integration_id = multiple_tools_for_bulk[0].integration_id

        response = await jwt_client.patch(
            f"/api/v1/integrations/{integration_id}/tools/bulk_update", json={"tool_ids": tool_ids, "enabled": False}
        )

        # Contract: Should handle duplicates gracefully
        assert response.status_code == 200

        # Contract: Should count each unique tool only once and not count duplicates as skipped
        data = response.json()
        assert data["updated_count"] == 1  # Only one unique tool updated
        assert data["skipped_count"] == 0  # Duplicates are removed, not skipped

    @pytest.mark.asyncio
    async def test_bulk_update_nonexistent_tool_contract(
        self, jwt_client: AsyncClient, multiple_tools_for_bulk: list[Tool]
    ) -> None:
        """Test bulk update with completely non-existent tool IDs."""
        # Generate UUIDs that don't exist in the database
        nonexistent_tool_ids = [str(uuid4()), str(uuid4()), str(uuid4())]
        integration_id = multiple_tools_for_bulk[0].integration_id

        response = await jwt_client.patch(
            f"/api/v1/integrations/{integration_id}/tools/bulk_update",
            json={"tool_ids": nonexistent_tool_ids, "enabled": False},
        )

        # Contract: Should succeed but skip all non-existent tools
        assert response.status_code == 200

        # Contract: Should update 0 tools and skip all requested tools
        data = response.json()
        assert data["updated_count"] == 0  # No tools exist to update
        assert data["skipped_count"] == 3  # All three non-existent tools skipped

    @pytest.mark.asyncio
    async def test_bulk_update_mixed_scenarios_contract(
        self,
        jwt_client: AsyncClient,
        multiple_tools_for_bulk: list[Tool],
    ) -> None:
        """Test bulk update with mix of active, non-existent, and duplicate tools."""
        # Mix of different scenarios:
        # - Active tool (should be updated)
        # - Non-existent tool (should be skipped)
        # - Duplicate active tool (should be deduplicated)
        active_tool_id = str(multiple_tools_for_bulk[0].id)
        tool_ids = [
            active_tool_id,  # Active tool
            str(uuid4()),  # Non-existent tool
            active_tool_id,  # Duplicate active tool
        ]
        integration_id = multiple_tools_for_bulk[0].integration_id

        response = await jwt_client.patch(
            f"/api/v1/integrations/{integration_id}/tools/bulk_update", json={"tool_ids": tool_ids, "enabled": False}
        )

        # Contract: Should handle all scenarios gracefully
        assert response.status_code == 200

        # Contract: Should update 1 unique active tool and skip non-existent tools
        data = response.json()
        assert data["updated_count"] == 1  # Only the unique active tool
        assert data["skipped_count"] == 1  # Non-existent (duplicates removed first)
