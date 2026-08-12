"""Contract tests for GET /api/v1/groups/{group_id} endpoint.

Tests group retrieval, 404 handling, and response format.
"""

import pytest
from httpx import AsyncClient

from syntara.core.models import User
from syntara.core.models.group import Group
from tests.integration.helpers.error_data import assert_error_data

GROUPS_URL = "/api/v1/groups"


class TestGroupsGetContract:
    """Contract tests for group get endpoint."""

    @pytest.mark.asyncio
    async def test_get_group_success(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test successful group retrieval returns 200."""
        response = await admin_client.get(f"{GROUPS_URL}/{test_group.id}")

        assert response.status_code == 200

        data = response.json()
        assert data["id"] == str(test_group.id)
        assert data["name"] == test_group.name
        assert data["description"] == test_group.description

    @pytest.mark.asyncio
    async def test_get_group_all_fields(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test response includes all required GroupRead fields."""
        response = await admin_client.get(f"{GROUPS_URL}/{test_group.id}")

        assert response.status_code == 200

        data = response.json()
        required_fields = ["id", "name", "description", "created_by", "created_at", "updated_at"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    @pytest.mark.asyncio
    async def test_get_group_timestamps_format(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test timestamp fields are properly formatted."""
        response = await admin_client.get(f"{GROUPS_URL}/{test_group.id}")

        assert response.status_code == 200

        data = response.json()
        for field in ["created_at", "updated_at"]:
            assert field in data
            assert isinstance(data[field], str)
            assert "T" in data[field]

    @pytest.mark.asyncio
    async def test_get_group_not_found(self, admin_client: AsyncClient) -> None:
        """Test 404 error for non-existent group."""
        group_id = "99999999-9999-9999-9999-999999999999"

        response = await admin_client.get(f"{GROUPS_URL}/{group_id}")

        assert response.status_code == 404
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/resource-not-found",
            title="Group Not Found",
            detail="The requested group was not found",
            code="GROUP_NOT_FOUND",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_get_group_invalid_uuid(self, admin_client: AsyncClient) -> None:
        """Test 422 error for invalid UUID format."""
        response = await admin_client.get(f"{GROUPS_URL}/not-a-uuid")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_group_deleted_returns_404(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test that soft-deleted group returns 404."""
        # Delete the group
        delete_response = await admin_client.delete(f"{GROUPS_URL}/{test_group.id}")
        assert delete_response.status_code == 204

        # Attempt to get deleted group
        response = await admin_client.get(f"{GROUPS_URL}/{test_group.id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_group_created_by_matches(
        self, admin_client: AsyncClient, test_group: Group, test_user: User
    ) -> None:
        """Test created_by field matches the creating user."""
        response = await admin_client.get(f"{GROUPS_URL}/{test_group.id}")

        assert response.status_code == 200

        data = response.json()
        assert data["created_by"] == str(test_user.id)

    @pytest.mark.asyncio
    async def test_get_group_unauthenticated(self, base_client: AsyncClient, test_group: Group) -> None:
        """Test getting a group requires authentication."""
        response = await base_client.get(f"{GROUPS_URL}/{test_group.id}")

        assert response.status_code == 401
