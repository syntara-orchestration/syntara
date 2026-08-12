"""Contract tests for PATCH /api/v1/groups/{group_id} endpoint.

Tests partial update functionality, validation, and conflict handling.
"""

import pytest
from httpx import AsyncClient

from syntara.core.models.group import Group
from tests.integration.helpers.error_data import assert_error_data

GROUPS_URL = "/api/v1/groups"


class TestGroupsPatchContract:
    """Contract tests for group patch endpoint."""

    @pytest.mark.asyncio
    async def test_update_group_name_success(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test successful group name update returns 200."""
        patch_data = {"name": "updated-name"}

        response = await admin_client.patch(f"{GROUPS_URL}/{test_group.id}", json=patch_data)

        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "updated-name"
        assert data["description"] == test_group.description

    @pytest.mark.asyncio
    async def test_update_group_description_success(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test successful group description update."""
        patch_data = {"description": "Updated description"}

        response = await admin_client.patch(f"{GROUPS_URL}/{test_group.id}", json=patch_data)

        assert response.status_code == 200

        data = response.json()
        assert data["name"] == test_group.name
        assert data["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_update_group_preserves_unchanged_fields(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test partial update preserves fields not included in patch."""
        patch_data = {"description": "New description only"}

        response = await admin_client.patch(f"{GROUPS_URL}/{test_group.id}", json=patch_data)

        assert response.status_code == 200

        data = response.json()
        assert data["name"] == test_group.name
        assert data["id"] == str(test_group.id)
        assert data["created_by"] == str(test_group.created_by)

    @pytest.mark.asyncio
    async def test_update_group_empty_patch(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test PATCH with empty body returns 200 unchanged, including timestamp."""
        # GET the group first to capture the serialized updated_at value
        get_response = await admin_client.get(f"{GROUPS_URL}/{test_group.id}")
        original_updated_at = get_response.json()["updated_at"]

        patch_data: dict[str, str] = {}

        response = await admin_client.patch(f"{GROUPS_URL}/{test_group.id}", json=patch_data)

        assert response.status_code == 200

        data = response.json()
        assert data["name"] == test_group.name
        assert data["description"] == test_group.description
        assert data["updated_at"] == original_updated_at

    @pytest.mark.asyncio
    async def test_update_group_updates_timestamp(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test that updated_at timestamp changes after update."""
        original_updated_at = test_group.updated_at

        patch_data = {"name": "timestamp-test"}

        response = await admin_client.patch(f"{GROUPS_URL}/{test_group.id}", json=patch_data)

        assert response.status_code == 200

        data = response.json()
        assert data["updated_at"] != str(original_updated_at)

    @pytest.mark.asyncio
    async def test_update_group_name_conflict(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test 409 conflict when updating to an existing group name."""
        # Create another group
        create_response = await admin_client.post(GROUPS_URL, json={"name": "existing-name"})
        assert create_response.status_code == 201

        # Try to update test_group to the same name
        patch_data = {"name": "existing-name"}
        response = await admin_client.patch(f"{GROUPS_URL}/{test_group.id}", json=patch_data)

        assert response.status_code == 409
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/name-conflict",
            title="Group Name Conflict",
            detail="A group with this name already exists",
            code="GROUP_NAME_CONFLICT",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_update_group_not_found(self, admin_client: AsyncClient) -> None:
        """Test 404 error for non-existent group."""
        group_id = "99999999-9999-9999-9999-999999999999"
        patch_data = {"name": "new-name"}

        response = await admin_client.patch(f"{GROUPS_URL}/{group_id}", json=patch_data)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_group_name_too_long(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test validation error for name exceeding max length."""
        patch_data = {"name": "x" * 256}

        response = await admin_client.patch(f"{GROUPS_URL}/{test_group.id}", json=patch_data)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_group_description_too_long(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test validation error for description exceeding max length."""
        patch_data = {"description": "x" * 2001}

        response = await admin_client.patch(f"{GROUPS_URL}/{test_group.id}", json=patch_data)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_group_null_description_is_noop(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test that sending description: null is a no-op (preserves existing value)."""
        patch_data = {"description": None}

        response = await admin_client.patch(f"{GROUPS_URL}/{test_group.id}", json=patch_data)

        assert response.status_code == 200

        data = response.json()
        # None values in GroupUpdate are treated as "not provided", so description is preserved
        assert data["description"] == test_group.description

    @pytest.mark.asyncio
    async def test_update_group_both_fields(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test updating both name and description together."""
        patch_data = {"name": "new-name", "description": "new description"}

        response = await admin_client.patch(f"{GROUPS_URL}/{test_group.id}", json=patch_data)

        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "new-name"
        assert data["description"] == "new description"

    @pytest.mark.asyncio
    async def test_update_group_same_name_no_conflict(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test updating a group with its own current name does not conflict."""
        patch_data = {"name": test_group.name}

        response = await admin_client.patch(f"{GROUPS_URL}/{test_group.id}", json=patch_data)

        assert response.status_code == 200

        data = response.json()
        assert data["name"] == test_group.name

    @pytest.mark.asyncio
    async def test_update_group_unauthenticated(self, base_client: AsyncClient, test_group: Group) -> None:
        """Test updating a group requires authentication."""
        patch_data = {"name": "unauth-update"}

        response = await base_client.patch(f"{GROUPS_URL}/{test_group.id}", json=patch_data)

        assert response.status_code == 401
