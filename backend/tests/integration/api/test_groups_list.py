"""Contract tests for GET /api/v1/groups endpoint.

Tests cursor-based pagination, bracket filter notation, sorting, and response format.
"""

import pytest
from httpx import AsyncClient

from syntara.core.models.group import Group

GROUPS_URL = "/api/v1/groups"


class TestGroupsListContract:
    """Contract tests for group list endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("multiple_test_groups")
    async def test_list_groups_basic_success(self, admin_client: AsyncClient) -> None:
        """Test basic GET /api/v1/groups returns 200."""
        response = await admin_client.get(GROUPS_URL)

        assert response.status_code == 200

        data = response.json()
        assert "resources" in data
        assert isinstance(data["resources"], list)
        # 6 from fixture + 4 builtin + 1 test-users + 1 admin-grp
        assert len(data["resources"]) == 12

    @pytest.mark.asyncio
    async def test_list_groups_only_builtin(self, admin_client: AsyncClient) -> None:
        """Test response format when only builtin groups exist."""
        response = await admin_client.get(GROUPS_URL)

        assert response.status_code == 200

        data = response.json()
        assert "resources" in data
        assert isinstance(data["resources"], list)
        # 4 builtin groups (authenticated, admins, auditors, users) + 1 test-users + 1 admin-grp
        assert len(data["resources"]) == 6

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("multiple_test_groups")
    async def test_list_groups_response_schema(self, admin_client: AsyncClient) -> None:
        """Test response matches expected schema structure."""
        response = await admin_client.get(GROUPS_URL)

        assert response.status_code == 200

        data = response.json()
        assert len(data["resources"]) > 0

        for group in data["resources"]:
            required_fields = ["id", "name", "description", "created_by", "created_at", "updated_at"]
            for field in required_fields:
                assert field in group, f"Missing required field: {field}"

            assert isinstance(group["id"], str)
            assert isinstance(group["name"], str)
            assert isinstance(group["created_at"], str)
            assert isinstance(group["updated_at"], str)

    @pytest.mark.asyncio
    async def test_list_groups_pagination(self, admin_client: AsyncClient, multiple_test_groups: list[Group]) -> None:
        """Test pagination with limit parameter."""
        response = await admin_client.get(GROUPS_URL, params={"limit": "3"})

        assert response.status_code == 200

        data = response.json()
        assert "next" in data
        assert "prev" in data
        assert "resources" in data
        assert len(data["resources"]) <= 3

        if len(multiple_test_groups) > 3:
            assert data["next"] is not None

        # Follow next cursor
        if data["next"]:
            next_response = await admin_client.get(GROUPS_URL, params={"limit": "3", "cursor": data["next"]})
            assert next_response.status_code == 200
            next_data = next_response.json()
            assert "resources" in next_data

            first_page_ids = {g["id"] for g in data["resources"]}
            second_page_ids = {g["id"] for g in next_data["resources"]}
            assert first_page_ids.isdisjoint(second_page_ids)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("multiple_test_groups")
    async def test_list_groups_cursor_format(self, admin_client: AsyncClient) -> None:
        """Test cursor token format in response."""
        response = await admin_client.get(GROUPS_URL, params={"limit": "1"})

        assert response.status_code == 200

        data = response.json()
        assert data["next"] is not None
        assert isinstance(data["next"], str)
        assert len(data["next"]) > 0
        assert len(data["resources"]) == 1

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("multiple_test_groups")
    async def test_list_groups_sorting_by_name(self, admin_client: AsyncClient) -> None:
        """Test sorting groups by name ascending and descending."""
        response = await admin_client.get(GROUPS_URL, params={"sort": "name"})
        assert response.status_code == 200

        data = response.json()
        names = [g["name"] for g in data["resources"]]
        # DB sorts case-insensitively, so compare with key=str.lower
        assert names == sorted(names, key=str.lower)

        desc_response = await admin_client.get(GROUPS_URL, params={"sort": "-name"})
        assert desc_response.status_code == 200

        desc_data = desc_response.json()
        desc_names = [g["name"] for g in desc_data["resources"]]
        assert desc_names == sorted(desc_names, key=str.lower, reverse=True)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("multiple_test_groups")
    async def test_list_groups_sorting_by_created_at(self, admin_client: AsyncClient) -> None:
        """Test sorting groups by creation date."""
        response = await admin_client.get(GROUPS_URL, params={"sort": "created_at"})
        assert response.status_code == 200

        data = response.json()
        created_dates = [g["created_at"] for g in data["resources"]]
        assert created_dates == sorted(created_dates)

        desc_response = await admin_client.get(GROUPS_URL, params={"sort": "-created_at"})
        assert desc_response.status_code == 200

        desc_data = desc_response.json()
        desc_dates = [g["created_at"] for g in desc_data["resources"]]
        assert desc_dates == sorted(desc_dates, reverse=True)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("multiple_test_groups")
    async def test_list_groups_filter_by_name_contains(self, admin_client: AsyncClient) -> None:
        """Test bracket filter notation for name contains."""
        response = await admin_client.get(GROUPS_URL, params={"name[contains]": "Alpha"})
        assert response.status_code == 200

        data = response.json()
        assert len(data["resources"]) == 1
        assert data["resources"][0]["name"] == "Alpha Group"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("multiple_test_groups")
    async def test_list_groups_include_total(self, admin_client: AsyncClient) -> None:
        """Test include_total parameter returns total count."""
        response = await admin_client.get(GROUPS_URL, params={"include_total": "true"})

        assert response.status_code == 200

        data = response.json()
        assert "total" in data
        assert isinstance(data["total"], int)
        # 6 from fixture + 4 builtin + 1 test-users + 1 admin-grp
        assert data["total"] == 12

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("multiple_test_groups")
    async def test_list_groups_include_total_with_pagination(self, admin_client: AsyncClient) -> None:
        """Test total count is accurate even with pagination."""
        response = await admin_client.get(GROUPS_URL, params={"include_total": "true", "limit": "2"})

        assert response.status_code == 200

        data = response.json()
        # 6 from fixture + 4 builtin + 1 test-users + 1 admin-grp
        assert data["total"] == 12
        assert len(data["resources"]) == 2

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("multiple_test_groups")
    async def test_list_groups_combined_filter_and_sort(self, admin_client: AsyncClient) -> None:
        """Test combining filters and sorting."""
        response = await admin_client.get(GROUPS_URL, params={"name[contains]": "Group", "sort": "name"})
        assert response.status_code == 200

        data = response.json()
        names = [g["name"] for g in data["resources"]]
        assert names == sorted(names)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("multiple_test_groups")
    async def test_list_groups_filter_no_results(self, admin_client: AsyncClient) -> None:
        """Test filtering that returns no results."""
        response = await admin_client.get(GROUPS_URL, params={"name[contains]": "nonexistent"})

        assert response.status_code == 200

        data = response.json()
        assert len(data["resources"]) == 0
        assert data["next"] is None
        assert data["prev"] is None

    @pytest.mark.asyncio
    async def test_list_groups_invalid_limit(self, admin_client: AsyncClient) -> None:
        """Test validation of invalid limit parameter."""
        response = await admin_client.get(GROUPS_URL, params={"limit": "invalid"})

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_groups_zero_limit(self, admin_client: AsyncClient) -> None:
        """Test validation error for zero limit."""
        response = await admin_client.get(GROUPS_URL, params={"limit": "0"})

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_groups_deleted_groups_excluded(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test that soft-deleted groups are excluded from listing."""
        # Verify group appears in list
        response = await admin_client.get(GROUPS_URL)
        assert response.status_code == 200
        data = response.json()
        group_ids = [g["id"] for g in data["resources"]]
        assert str(test_group.id) in group_ids

        # Delete the group
        delete_response = await admin_client.delete(f"{GROUPS_URL}/{test_group.id}")
        assert delete_response.status_code == 204

        # Verify group no longer appears in list
        response = await admin_client.get(GROUPS_URL)
        assert response.status_code == 200
        data = response.json()
        group_ids = [g["id"] for g in data["resources"]]
        assert str(test_group.id) not in group_ids

    @pytest.mark.asyncio
    async def test_list_groups_unauthenticated(self, base_client: AsyncClient) -> None:
        """Test listing groups requires authentication."""
        response = await base_client.get(GROUPS_URL)

        assert response.status_code == 401
