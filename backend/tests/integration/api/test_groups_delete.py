"""Contract tests for DELETE /api/v1/groups/{group_id} endpoint.

Tests soft delete functionality and error handling.
"""

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models.group import Group
from tests.integration.helpers.error_data import assert_error_data

GROUPS_URL = "/api/v1/groups"


class TestGroupsDeleteContract:
    """Contract tests for group delete endpoint."""

    @pytest.mark.asyncio
    async def test_delete_group_success(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test successful soft delete returns 204 with empty body."""
        response = await admin_client.delete(f"{GROUPS_URL}/{test_group.id}")

        assert response.status_code == 204
        assert len(response.content) == 0

    @pytest.mark.asyncio
    async def test_delete_group_not_accessible_via_get(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test deleted group is not accessible via GET."""
        delete_response = await admin_client.delete(f"{GROUPS_URL}/{test_group.id}")
        assert delete_response.status_code == 204

        get_response = await admin_client.get(f"{GROUPS_URL}/{test_group.id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_group_excluded_from_list(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test deleted group does not appear in list."""
        delete_response = await admin_client.delete(f"{GROUPS_URL}/{test_group.id}")
        assert delete_response.status_code == 204

        list_response = await admin_client.get(GROUPS_URL)
        assert list_response.status_code == 200

        data = list_response.json()
        group_ids = [g["id"] for g in data["resources"]]
        assert str(test_group.id) not in group_ids

    @pytest.mark.asyncio
    async def test_delete_group_not_found(self, admin_client: AsyncClient) -> None:
        """Test 404 error for non-existent group."""
        group_id = "99999999-9999-9999-9999-999999999999"

        response = await admin_client.delete(f"{GROUPS_URL}/{group_id}")

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
    async def test_delete_group_already_deleted(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test deleting an already-deleted group returns 404."""
        # First deletion
        response1 = await admin_client.delete(f"{GROUPS_URL}/{test_group.id}")
        assert response1.status_code == 204

        # Second deletion attempt
        response2 = await admin_client.delete(f"{GROUPS_URL}/{test_group.id}")
        assert response2.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_group_invalid_uuid(self, admin_client: AsyncClient) -> None:
        """Test 422 error for invalid UUID format."""
        response = await admin_client.delete(f"{GROUPS_URL}/not-a-uuid")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_group_allows_name_reuse(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test that deleting a group allows reusing its name."""
        original_name = test_group.name

        # Delete the group
        delete_response = await admin_client.delete(f"{GROUPS_URL}/{test_group.id}")
        assert delete_response.status_code == 204

        # Create a new group with the same name
        create_response = await admin_client.post(GROUPS_URL, json={"name": original_name})
        assert create_response.status_code == 201

        data = create_response.json()
        assert data["name"] == original_name

    @pytest.mark.asyncio
    @pytest.mark.parametrize("group_name", ["auditors", "admins", "authenticated"])
    async def test_delete_builtin_group_forbidden(
        self,
        admin_client: AsyncClient,
        test_db_session: AsyncSession,
        group_name: str,
    ) -> None:
        """Test that deleting a builtin group returns 403 Forbidden."""
        result = await test_db_session.exec(
            select(Group).where(Group.name == group_name, Group.deleted_at.is_(None))  # type: ignore[union-attr]
        )
        group = result.one()

        response = await admin_client.delete(f"{GROUPS_URL}/{group.id}")

        assert response.status_code == 403
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/forbidden",
            title="Forbidden",
            detail=f"The built-in '{group_name}' group cannot be deleted",
            code="BUILTIN_GROUP_DELETE_FORBIDDEN",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_delete_group_unauthenticated(self, base_client: AsyncClient, test_group: Group) -> None:
        """Test deleting a group requires authentication."""
        response = await base_client.delete(f"{GROUPS_URL}/{test_group.id}")

        assert response.status_code == 401
