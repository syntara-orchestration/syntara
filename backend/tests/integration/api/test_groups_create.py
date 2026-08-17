"""Contract tests for POST /api/v1/groups endpoint.

Tests group creation, validation, and conflict handling.
"""

import pytest
from httpx import AsyncClient

from syntara.core.models import User
from tests.integration.helpers.error_data import assert_error_data

GROUPS_URL = "/api/v1/groups"


class TestGroupsCreateContract:
    """Contract tests for group create endpoint."""

    @pytest.mark.asyncio
    async def test_create_group_success(self, admin_client: AsyncClient) -> None:
        """Test successful group creation returns 201."""
        group_data = {
            "name": "engineering",
            "description": "Engineering team group",
        }

        response = await admin_client.post(GROUPS_URL, json=group_data)

        assert response.status_code == 201

        data = response.json()
        assert "id" in data
        assert data["name"] == "engineering"
        assert data["description"] == "Engineering team group"

    @pytest.mark.asyncio
    async def test_create_group_without_description(self, admin_client: AsyncClient) -> None:
        """Test successful group creation without optional description."""
        group_data = {"name": "no-desc-group"}

        response = await admin_client.post(GROUPS_URL, json=group_data)

        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "no-desc-group"
        assert data["description"] is None

    @pytest.mark.asyncio
    async def test_create_group_response_schema(self, admin_client: AsyncClient) -> None:
        """Test response includes all required GroupRead fields."""
        group_data = {"name": "schema-test-group"}

        response = await admin_client.post(GROUPS_URL, json=group_data)

        assert response.status_code == 201

        data = response.json()
        required_fields = ["id", "name", "description", "created_by", "created_at", "updated_at"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        assert isinstance(data["id"], str)
        assert isinstance(data["name"], str)
        assert isinstance(data["created_at"], str)
        assert isinstance(data["updated_at"], str)

    @pytest.mark.asyncio
    async def test_create_group_sets_created_by(self, admin_client: AsyncClient, admin_user: User) -> None:
        """Test created_by is set to the authenticated user's ID."""
        group_data = {"name": "created-by-test"}

        response = await admin_client.post(GROUPS_URL, json=group_data)

        assert response.status_code == 201

        data = response.json()
        assert data["created_by"] == str(admin_user.id)

    @pytest.mark.asyncio
    async def test_create_group_duplicate_name_conflict(self, admin_client: AsyncClient) -> None:
        """Test 409 conflict for duplicate group names."""
        group_data = {"name": "duplicate-group"}

        response1 = await admin_client.post(GROUPS_URL, json=group_data)
        assert response1.status_code == 201

        response2 = await admin_client.post(GROUPS_URL, json=group_data)

        assert response2.status_code == 409
        assert_error_data(
            response2,
            error_type="https://api.example.com/errors/name-conflict",
            title="Group Name Conflict",
            detail="A group with this name already exists",
            code="GROUP_NAME_CONFLICT",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_create_group_missing_name(self, admin_client: AsyncClient) -> None:
        """Test validation error for missing name field."""
        group_data: dict[str, str] = {}

        response = await admin_client.post(GROUPS_URL, json=group_data)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_group_empty_name(self, admin_client: AsyncClient) -> None:
        """Test validation error for empty name."""
        group_data = {"name": ""}

        response = await admin_client.post(GROUPS_URL, json=group_data)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_group_name_too_long(self, admin_client: AsyncClient) -> None:
        """Test validation error for name exceeding max length."""
        group_data = {"name": "x" * 256}

        response = await admin_client.post(GROUPS_URL, json=group_data)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_group_description_too_long(self, admin_client: AsyncClient) -> None:
        """Test validation error for description exceeding max length."""
        group_data = {
            "name": "long-desc-group",
            "description": "x" * 2001,
        }

        response = await admin_client.post(GROUPS_URL, json=group_data)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_group_with_max_length_name(self, admin_client: AsyncClient) -> None:
        """Test group creation with name at max length boundary."""
        group_data = {"name": "x" * 255}

        response = await admin_client.post(GROUPS_URL, json=group_data)

        assert response.status_code == 201

        data = response.json()
        assert len(data["name"]) == 255

    @pytest.mark.asyncio
    async def test_create_group_unauthenticated(self, base_client: AsyncClient) -> None:
        """Test group creation requires authentication."""
        group_data = {"name": "unauth-group"}

        response = await base_client.post(GROUPS_URL, json=group_data)

        assert response.status_code == 401
