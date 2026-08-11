"""Contract tests for GET /api/v1/users/{user_id} endpoint.

Tests user retrieval, 404 handling, and response format.
"""

import pytest
from httpx import AsyncClient

from syntara.core.models import User
from tests.integration.helpers.error_data import assert_error_data

USERS_URL = "/api/v1/users"


class TestUsersGetContract:
    """Contract tests for user get endpoint."""

    @pytest.mark.asyncio
    async def test_get_user_success(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test successful user retrieval returns 200."""
        response = await admin_client.get(f"{USERS_URL}/{test_user.id}")

        assert response.status_code == 200

        data = response.json()
        assert data["id"] == str(test_user.id)
        assert data["username"] == test_user.username
        assert data["email"] == test_user.email

    @pytest.mark.asyncio
    async def test_get_user_all_fields(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test response includes all required UserRead fields."""
        response = await admin_client.get(f"{USERS_URL}/{test_user.id}")

        assert response.status_code == 200

        data = response.json()
        required_fields = [
            "id",
            "username",
            "email",
            "first_name",
            "is_enabled",
            "last_login",
            "created_at",
            "updated_at",
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    @pytest.mark.asyncio
    async def test_get_user_timestamps_format(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test timestamp fields are properly formatted."""
        response = await admin_client.get(f"{USERS_URL}/{test_user.id}")

        assert response.status_code == 200

        data = response.json()
        for field in ["created_at", "updated_at"]:
            assert field in data
            assert isinstance(data[field], str)
            assert "T" in data[field]

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, admin_client: AsyncClient) -> None:
        """Test 404 error for non-existent user."""
        user_id = "99999999-9999-9999-9999-999999999999"

        response = await admin_client.get(f"{USERS_URL}/{user_id}")

        assert response.status_code == 404
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/resource-not-found",
            title="User Not Found",
            detail="The requested user was not found",
            code="USER_NOT_FOUND",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_get_user_invalid_uuid(self, admin_client: AsyncClient) -> None:
        """Test 422 error for invalid UUID format."""
        response = await admin_client.get(f"{USERS_URL}/not-a-uuid")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_user_no_password_in_response(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test password fields are never in response."""
        response = await admin_client.get(f"{USERS_URL}/{test_user.id}")

        assert response.status_code == 200

        data = response.json()
        assert "password" not in data
        assert "password_hash" not in data

    @pytest.mark.asyncio
    async def test_get_user_unauthenticated(self, base_client: AsyncClient, test_user: User) -> None:
        """Test getting a user requires authentication."""
        response = await base_client.get(f"{USERS_URL}/{test_user.id}")

        assert response.status_code == 401
