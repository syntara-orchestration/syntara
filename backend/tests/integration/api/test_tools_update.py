"""Contract tests for PATCH /api/v1/tools/{tool_id} endpoint.

Tests tool status updates, validation, and response format.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from syntara.tool_manager.models import Tool, ToolStatus


class TestToolsUpdateContract:
    """Contract tests for tool update endpoint."""

    @pytest.mark.asyncio
    async def test_update_tool_disable_success_contract(self, jwt_client: AsyncClient, test_tool: Tool) -> None:
        """Test successful tool disabling returns 200."""
        # Ensure tool starts as available
        test_tool.status = ToolStatus.AVAILABLE

        response = await jwt_client.patch(f"/api/v1/tools/{test_tool.id}", json={"enabled": False})

        # Contract: Must return 200 OK for successful update
        assert response.status_code == 200

        # Contract: Must return updated tool details
        data = response.json()
        assert "id" in data
        assert "status" in data
        assert data["id"] == str(test_tool.id)
        assert not data["enabled"]

    @pytest.mark.asyncio
    async def test_update_tool_enable_success_contract(self, jwt_client: AsyncClient, test_tool: Tool) -> None:
        """Test successful tool enabling returns 200."""
        # Set tool as disabled first
        test_tool.enabled = False

        response = await jwt_client.patch(f"/api/v1/tools/{test_tool.id}", json={"enabled": True})

        # Contract: Must return 200 OK for successful update
        assert response.status_code == 200

        # Contract: Must return updated tool details
        data = response.json()
        assert data["id"] == str(test_tool.id)
        assert data["enabled"]

    @pytest.mark.asyncio
    async def test_update_tool_status_success_contract(self, jwt_client: AsyncClient, test_tool: Tool) -> None:
        """Test successful tool status update returns 200."""
        # Set initial status
        test_tool.status = ToolStatus.AVAILABLE

        response = await jwt_client.patch(f"/api/v1/tools/{test_tool.id}", json={"status": "error"})

        # Contract: Must return 200 OK for successful update
        assert response.status_code == 200

        # Contract: Must return updated tool details
        data = response.json()
        assert data["id"] == str(test_tool.id)
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_update_tool_refresh_error_success_contract(self, jwt_client: AsyncClient, test_tool: Tool) -> None:
        """Test successful tool refresh error update returns 200."""
        # Set initial refresh error
        test_tool.refresh_error = None

        error_message = "Connection timeout while refreshing tool"
        response = await jwt_client.patch(f"/api/v1/tools/{test_tool.id}", json={"refresh_error": error_message})

        # Contract: Must return 200 OK for successful update
        assert response.status_code == 200

        # Contract: Must return updated tool details
        data = response.json()
        assert data["id"] == str(test_tool.id)
        assert data["refresh_error"] == error_message

    @pytest.mark.asyncio
    async def test_update_tool_all_fields_success_contract(self, jwt_client: AsyncClient, test_tool: Tool) -> None:
        """Test successful update of all tool fields returns 200."""
        # Set initial values
        test_tool.enabled = True
        test_tool.status = ToolStatus.AVAILABLE
        test_tool.refresh_error = None

        error_message = "Tool provider unavailable"
        response = await jwt_client.patch(
            f"/api/v1/tools/{test_tool.id}",
            json={"enabled": False, "status": "error", "refresh_error": error_message},
        )

        # Contract: Must return 200 OK for successful update
        assert response.status_code == 200

        # Contract: Must return updated tool details
        data = response.json()
        assert data["id"] == str(test_tool.id)
        assert not data["enabled"]
        assert data["status"] == "error"
        assert data["refresh_error"] == error_message

    @pytest.mark.asyncio
    async def test_update_tool_not_found_contract(self, jwt_client: AsyncClient) -> None:
        """Test tool update with non-existent ID returns 404."""
        non_existent_id = uuid4()
        response = await jwt_client.patch(f"/api/v1/tools/{non_existent_id}", json={"enabled": False})

        # Contract: Must return 404 Not Found for non-existent tool
        assert response.status_code == 404

        # Contract: Must return error details
        data = response.json()
        assert "detail" in data
        assert str(non_existent_id) in data["detail"]

    @pytest.mark.asyncio
    async def test_update_tool_invalid_uuid_contract(self, jwt_client: AsyncClient) -> None:
        """Test tool update with invalid UUID format returns 422."""
        invalid_uuid = "not-a-valid-uuid"
        response = await jwt_client.patch(f"/api/v1/tools/{invalid_uuid}", json={"enabled": False})

        # Contract: Must return 422 Unprocessable Entity for invalid UUID
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_tool_invalid_json_contract(self, jwt_client: AsyncClient, test_tool: Tool) -> None:
        """Test tool update with invalid JSON returns 422."""
        response = await jwt_client.patch(
            f"/api/v1/tools/{test_tool.id}",
            content="invalid json",
            headers={"Content-Type": "application/json"},
        )

        # Contract: Must return 422 for invalid JSON
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_tool_unknown_field_contract(self, jwt_client: AsyncClient, test_tool: Tool) -> None:
        """Test tool update with unknown fields."""
        response = await jwt_client.patch(
            f"/api/v1/tools/{test_tool.id}", json={"enabled": False, "unknown_field": "value"}
        )

        # Contract: Should either accept (ignoring unknown fields) or reject
        # The exact behavior depends on Pydantic configuration
        assert response.status_code in [200, 422]

        if response.status_code == 200:
            # If accepted, should still update the status correctly
            data = response.json()
            assert not data["enabled"]

    @pytest.mark.asyncio
    async def test_update_tool_response_format_contract(self, jwt_client: AsyncClient, test_tool: Tool) -> None:
        """Test update response includes all tool fields."""
        response = await jwt_client.patch(f"/api/v1/tools/{test_tool.id}", json={"enabled": False})

        # Contract: Must return 200 OK
        assert response.status_code == 200

        # Contract: Response must include all tool fields
        data = response.json()
        required_fields = [
            "id",
            "name",
            "description",
            "namespaced_name",
            "enabled",
            "status",
            "last_executed_at",
            "last_refreshed_at",
            "refresh_error",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        for field in required_fields:
            assert field in data, f"Missing field in response: {field}"

    @pytest.mark.asyncio
    async def test_update_tool_audit_fields_contract(self, jwt_client: AsyncClient, test_tool: Tool) -> None:
        """Test update modifies audit fields correctly."""
        # Get original updated_at timestamp
        original_response = await jwt_client.get(f"/api/v1/tools/{test_tool.id}")
        original_data = original_response.json()
        original_updated_at = original_data["updated_at"]

        # Update the tool
        response = await jwt_client.patch(f"/api/v1/tools/{test_tool.id}", json={"enabled": False})

        # Contract: Must return 200 OK
        assert response.status_code == 200

        # Contract: updated_at should be modified
        data = response.json()
        assert data["updated_at"] > original_updated_at

        # Contract: created_at should not change
        assert data["created_at"] == original_data["created_at"]

    @pytest.mark.asyncio
    async def test_update_tool_status_transitions_contract(self, jwt_client: AsyncClient, test_tool: Tool) -> None:
        """Test valid status transitions."""
        # Test available -> disabled
        response1 = await jwt_client.patch(f"/api/v1/tools/{test_tool.id}", json={"enabled": False})
        assert response1.status_code == 200
        assert not response1.json()["enabled"]

        # Test disabled -> available
        response2 = await jwt_client.patch(f"/api/v1/tools/{test_tool.id}", json={"enabled": True})
        assert response2.status_code == 200
        assert response2.json()["enabled"]

        # Test available -> available (idempotent)
        response3 = await jwt_client.patch(f"/api/v1/tools/{test_tool.id}", json={"enabled": True})
        assert response3.status_code == 200
        assert response3.json()["enabled"]

    @pytest.mark.asyncio
    async def test_update_tool_content_type_contract(self, jwt_client: AsyncClient, test_tool: Tool) -> None:
        """Test request requires JSON content type."""
        # Test with correct content type
        response = await jwt_client.patch(f"/api/v1/tools/{test_tool.id}", json={"enabled": False})
        assert response.status_code == 200

        # Test response content type
        assert response.headers["content-type"].startswith("application/json")

    @pytest.mark.asyncio
    async def test_update_tool_case_insensitivity_contract(self, jwt_client: AsyncClient, test_tool: Tool) -> None:
        """Test status values are case-insensitive."""
        response = await jwt_client.patch(
            f"/api/v1/tools/{test_tool.id}",
            json={"enabled": "FALSE"},
        )

        # Contract: Should accept any case
        assert response.status_code == 200
        assert not response.json()["enabled"]

    @pytest.mark.asyncio
    async def test_update_tool_preserves_other_fields_contract(self, jwt_client: AsyncClient, test_tool: Tool) -> None:
        """Test update preserves fields not being changed."""
        # Get original data
        original_response = await jwt_client.get(f"/api/v1/tools/{test_tool.id}")
        original_data = original_response.json()

        # Update only status
        response = await jwt_client.patch(f"/api/v1/tools/{test_tool.id}", json={"enabled": False})

        # Contract: Must return 200 OK
        assert response.status_code == 200

        # Contract: Other fields should be preserved
        data = response.json()
        assert data["name"] == original_data["name"]
        assert data["description"] == original_data["description"]
        assert data["integration_id"] == original_data["integration_id"]
        assert data["namespaced_name"] == original_data["namespaced_name"]

    @pytest.mark.asyncio
    async def test_update_tool_clear_refresh_error_contract(self, jwt_client: AsyncClient, test_tool: Tool) -> None:
        """Test clearing refresh_error by setting it to null."""
        # First, set a refresh error
        error_message = "Initial error message"
        response = await jwt_client.patch(f"/api/v1/tools/{test_tool.id}", json={"refresh_error": error_message})
        assert response.status_code == 200
        assert response.json()["refresh_error"] == error_message

        # Now clear it by setting to null
        response = await jwt_client.patch(f"/api/v1/tools/{test_tool.id}", json={"refresh_error": None})

        # Contract: Must return 200 OK
        assert response.status_code == 200

        # Contract: Must clear refresh_error field
        data = response.json()
        assert data["refresh_error"] is None

    @pytest.mark.asyncio
    async def test_update_tool_preserve_refresh_error_contract(self, jwt_client: AsyncClient, test_tool: Tool) -> None:
        """Test that PATCH without refresh_error field preserves existing value."""
        # First, set a refresh error
        error_message = "Persistent error message"
        response = await jwt_client.patch(f"/api/v1/tools/{test_tool.id}", json={"refresh_error": error_message})
        assert response.status_code == 200
        initial_data = response.json()
        assert initial_data["refresh_error"] == error_message

        # Now patch without refresh_error field
        response = await jwt_client.patch(f"/api/v1/tools/{test_tool.id}", json={"enabled": False})

        # Contract: Must return 200 OK
        assert response.status_code == 200

        # Contract: Must preserve existing refresh_error value
        data = response.json()
        assert data["refresh_error"] == error_message  # Preserved from initial set
        assert not data["enabled"]  # Updated field
