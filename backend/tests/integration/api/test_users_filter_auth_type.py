"""Integration tests for filtering users by authentication method (API-49).

Tests the ability to filter users by auth_type (local or federated) via the API.
Corresponds to test case API-49 in the authentication test plan.
"""

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.core.models.user import AuthType

USERS_URL = "/api/v1/users"


@pytest.fixture
async def local_user(test_db_session: AsyncSession, admin_user: User) -> User:
    """Create a local (non-builtin) user for testing."""
    from syntara.users.services.user_service import UsersService

    service = UsersService(test_db_session, admin_user)
    return await service.create_user(
        username="localuser",
        first_name="Local",
        last_name="User",
        password="LocalPassword123!",  # noqa: S106
        email="local@example.com",
        is_enabled=True,
    )


@pytest.fixture
async def federated_user(test_db_session: AsyncSession) -> User:
    """Create a federated user for testing."""
    from uuid import uuid4

    user = User(
        id=uuid4(),
        username="federateduser",
        email="federated@example.com",
        first_name="Federated",
        last_name="User",
        auth_type=AuthType.FEDERATED,
        is_enabled=True,
    )
    test_db_session.add(user)
    await test_db_session.commit()
    await test_db_session.refresh(user)
    return user


class TestUsersFilterByAuthType:
    """Test filtering users by authentication method (API-49)."""

    @pytest.mark.asyncio
    async def test_filter_by_local_auth_type(
        self, admin_client: AsyncClient, admin_user: User, local_user: User, federated_user: User
    ) -> None:
        """Test filtering returns only local users (including builtin)."""
        response = await admin_client.get(f"{USERS_URL}?auth_type=local")

        assert response.status_code == 200
        data = response.json()

        # Should return local users (admin + local_user)
        assert "resources" in data
        usernames = [user["username"] for user in data["resources"]]

        # Should include builtin admin and local_user
        assert admin_user.username in usernames
        assert local_user.username in usernames

        # Should NOT include federated user
        assert federated_user.username not in usernames

        # Verify all returned users have auth_type = "local"
        for user in data["resources"]:
            assert user["auth_type"] == "local"

    @pytest.mark.asyncio
    async def test_filter_by_federated_auth_type(
        self, admin_client: AsyncClient, admin_user: User, local_user: User, federated_user: User
    ) -> None:
        """Test filtering returns only federated/IdP users."""
        response = await admin_client.get(f"{USERS_URL}?auth_type=federated")

        assert response.status_code == 200
        data = response.json()

        assert "resources" in data
        usernames = [user["username"] for user in data["resources"]]

        # Should include federated user
        assert federated_user.username in usernames

        # Should NOT include local users
        assert admin_user.username not in usernames
        assert local_user.username not in usernames

        # Verify all returned users have auth_type = "federated"
        for user in data["resources"]:
            assert user["auth_type"] == "federated"

    @pytest.mark.asyncio
    async def test_no_filter_returns_all_auth_types(
        self, admin_client: AsyncClient, admin_user: User, local_user: User, federated_user: User
    ) -> None:
        """Test listing users without auth_type filter returns all users."""
        response = await admin_client.get(USERS_URL)

        assert response.status_code == 200
        data = response.json()

        assert "resources" in data
        usernames = [user["username"] for user in data["resources"]]

        # Should include both local and federated users
        assert admin_user.username in usernames
        assert local_user.username in usernames
        assert federated_user.username in usernames

    @pytest.mark.asyncio
    async def test_auth_type_field_present_in_response(
        self, admin_client: AsyncClient, admin_user: User, local_user: User, federated_user: User
    ) -> None:
        """Test each user record includes auth_type field with correct value."""
        response = await admin_client.get(USERS_URL)

        assert response.status_code == 200
        data = response.json()

        # Build a mapping of username -> auth_type from response
        user_auth_types = {user["username"]: user["auth_type"] for user in data["resources"]}

        # Verify each user has the correct auth_type
        assert user_auth_types[admin_user.username] == "local"
        assert user_auth_types[local_user.username] == "local"
        assert user_auth_types[federated_user.username] == "federated"

    @pytest.mark.asyncio
    async def test_filter_by_invalid_auth_type(self, admin_client: AsyncClient) -> None:
        """Test filtering by invalid auth_type returns 422 validation error."""
        response = await admin_client.get(f"{USERS_URL}?auth_type=invalid")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_builtin_admin_included_in_local_filter(self, admin_client: AsyncClient, admin_user: User) -> None:
        """Test builtin admin is included when filtering by auth_type=local."""
        response = await admin_client.get(f"{USERS_URL}?auth_type=local")

        assert response.status_code == 200
        data = response.json()

        usernames = [user["username"] for user in data["resources"]]
        assert admin_user.username in usernames

        # Find the admin user in the response
        admin_in_response = next(user for user in data["resources"] if user["username"] == admin_user.username)
        assert admin_in_response["is_builtin"] is True
        assert admin_in_response["auth_type"] == "local"

    @pytest.mark.asyncio
    async def test_filter_combined_with_other_params(
        self, admin_client: AsyncClient, local_user: User, federated_user: User
    ) -> None:
        """Test auth_type filter can be combined with other query parameters."""
        # Test combining auth_type with limit
        response = await admin_client.get(f"{USERS_URL}?auth_type=local&limit=1")

        assert response.status_code == 200
        data = response.json()

        assert "resources" in data
        assert len(data["resources"]) <= 1
        if data["resources"]:
            assert data["resources"][0]["auth_type"] == "local"

    @pytest.mark.asyncio
    async def test_get_single_user_includes_auth_type(self, admin_client: AsyncClient, local_user: User) -> None:
        """Test GET /users/{id} includes auth_type field."""
        response = await admin_client.get(f"{USERS_URL}/{local_user.id}")

        assert response.status_code == 200
        data = response.json()

        assert "auth_type" in data
        assert data["auth_type"] == "local"
        assert data["id"] == str(local_user.id)

    @pytest.mark.asyncio
    async def test_sort_by_auth_type(
        self, admin_client: AsyncClient, admin_user: User, local_user: User, federated_user: User
    ) -> None:
        """Test users can be sorted by auth_type field."""
        # Sort ascending (federated before local alphabetically)
        response = await admin_client.get(f"{USERS_URL}?sort=auth_type")

        assert response.status_code == 200
        data = response.json()

        auth_types = [user["auth_type"] for user in data["resources"]]

        # Should be sorted: federated first, then local (alphabetically)
        assert auth_types == sorted(auth_types)

        # Sort descending
        response = await admin_client.get(f"{USERS_URL}?sort=-auth_type")

        assert response.status_code == 200
        data = response.json()

        auth_types = [user["auth_type"] for user in data["resources"]]

        # Should be sorted descending: local first, then federated
        assert auth_types == sorted(auth_types, reverse=True)
