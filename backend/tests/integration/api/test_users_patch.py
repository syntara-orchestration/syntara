"""Contract tests for PATCH /api/v1/users/{user_id} endpoint.

Tests partial update functionality, validation, admin restrictions, and conflict handling.
"""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth import get_current_user
from syntara.core.models import User
from tests.integration.api.conftest import make_admin, make_user_role

USERS_URL = "/api/v1/users"


class TestUsersPatchContract:
    """Contract tests for user patch endpoint."""

    @pytest.mark.asyncio
    async def test_update_user_first_name(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test successful first_name update returns 200."""
        patch_data = {"first_name": "Updated", "last_name": "Name"}

        response = await admin_client.patch(f"{USERS_URL}/{test_user.id}", json=patch_data)

        assert response.status_code == 200

        data = response.json()
        assert data["first_name"] == "Updated"
        assert data["last_name"] == "Name"
        assert data["username"] == test_user.username

    @pytest.mark.asyncio
    async def test_update_user_email(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test successful email update."""
        patch_data = {"email": "newemail@example.com"}

        response = await admin_client.patch(f"{USERS_URL}/{test_user.id}", json=patch_data)

        assert response.status_code == 200

        data = response.json()
        assert data["email"] == "newemail@example.com"

    @pytest.mark.asyncio
    async def test_update_user_is_enabled(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test successful is_enabled update (disable user)."""
        patch_data = {"is_enabled": False}

        response = await admin_client.patch(f"{USERS_URL}/{test_user.id}", json=patch_data)

        assert response.status_code == 200

        data = response.json()
        assert data["is_enabled"] is False

    @pytest.mark.asyncio
    async def test_update_user_multiple_fields(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test updating multiple fields at once."""
        patch_data = {"first_name": "New Full", "last_name": "Name", "email": "multi@example.com"}

        response = await admin_client.patch(f"{USERS_URL}/{test_user.id}", json=patch_data)

        assert response.status_code == 200

        data = response.json()
        assert data["first_name"] == "New Full"
        assert data["last_name"] == "Name"
        assert data["email"] == "multi@example.com"

    @pytest.mark.asyncio
    async def test_update_user_empty_patch(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test PATCH with empty body returns 200 unchanged."""
        patch_data: dict[str, str] = {}

        response = await admin_client.patch(f"{USERS_URL}/{test_user.id}", json=patch_data)

        assert response.status_code == 200

        data = response.json()
        assert data["username"] == test_user.username
        assert data["email"] == test_user.email

    @pytest.mark.asyncio
    async def test_update_user_preserves_unchanged_fields(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test partial update preserves fields not included in patch."""
        patch_data = {"first_name": "Only Name", "last_name": "Changed"}

        response = await admin_client.patch(f"{USERS_URL}/{test_user.id}", json=patch_data)

        assert response.status_code == 200

        data = response.json()
        assert data["first_name"] == "Only Name"
        assert data["last_name"] == "Changed"
        assert data["email"] == test_user.email
        assert data["is_enabled"] == test_user.is_enabled

    @pytest.mark.asyncio
    async def test_clear_last_name_via_patch(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test that sending last_name: null clears the field."""
        # First set a last_name
        await admin_client.patch(f"{USERS_URL}/{test_user.id}", json={"last_name": "Doe"})

        # Now clear it
        response = await admin_client.patch(f"{USERS_URL}/{test_user.id}", json={"last_name": None})

        assert response.status_code == 200
        data = response.json()
        assert data["last_name"] is None

    @pytest.mark.asyncio
    async def test_omit_last_name_preserves_value(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test that omitting last_name from PATCH body preserves the existing value."""
        # Set a last_name
        await admin_client.patch(f"{USERS_URL}/{test_user.id}", json={"last_name": "Doe"})

        # PATCH without last_name — should preserve it
        response = await admin_client.patch(f"{USERS_URL}/{test_user.id}", json={"first_name": "Changed"})

        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Changed"
        assert data["last_name"] == "Doe"

    @pytest.mark.asyncio
    async def test_update_user_updates_timestamp(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test that updated_at timestamp changes after update."""
        original_updated_at = test_user.updated_at

        patch_data = {"first_name": "Timestamp", "last_name": "Test"}

        response = await admin_client.patch(f"{USERS_URL}/{test_user.id}", json=patch_data)

        assert response.status_code == 200

        data = response.json()
        assert data["updated_at"] != str(original_updated_at)

    @pytest.mark.asyncio
    async def test_update_user_duplicate_email_rejected(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test that updating to a duplicate email is rejected (email must be unique)."""
        # Create another user
        create_response = await admin_client.post(
            USERS_URL,
            json={
                "username": "otheruser",
                "email": "existing@example.com",
                "first_name": "Other",
                "last_name": "User",
                "password": "SecurePassword123!",
            },
        )
        assert create_response.status_code == 201

        # Update test_user to the same email — should fail
        patch_data = {"email": "existing@example.com"}
        response = await admin_client.patch(f"{USERS_URL}/{test_user.id}", json=patch_data)

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_update_user_not_found(self, admin_client: AsyncClient) -> None:
        """Test 404 error for non-existent user."""
        user_id = "99999999-9999-9999-9999-999999999999"
        patch_data = {"first_name": "New", "last_name": "Name"}

        response = await admin_client.patch(f"{USERS_URL}/{user_id}", json=patch_data)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_user_first_name_too_long(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test 422 when first_name exceeds max length."""
        patch_data = {"first_name": "x" * 256}

        response = await admin_client.patch(f"{USERS_URL}/{test_user.id}", json=patch_data)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_user_unauthenticated(self, base_client: AsyncClient, test_user: User) -> None:
        """Test updating a user requires authentication."""
        patch_data = {"first_name": "Unauth", "last_name": "Update"}

        response = await base_client.patch(f"{USERS_URL}/{test_user.id}", json=patch_data)

        assert response.status_code == 401


class TestUsersPatchSelfScope:
    """AAP-78918: non-admin users must be able to PATCH their own profile.

    The authenticated role grants user:update:self, which should allow any
    logged-in user to update their own record.  These tests use a user that
    has *only* the authenticated role (no admin), so user:update:self is the
    sole permission path.
    """

    @pytest.mark.asyncio
    async def test_non_admin_can_patch_own_profile(
        self,
        base_client: AsyncClient,
        user_factory: Callable[..., Awaitable[User]],
    ) -> None:
        """A non-admin user with user:update:self can update their own profile."""
        from syntara.api.main import app

        regular_user = await user_factory(
            username="selfpatch-user",
            email="selfpatch@example.com",
            first_name="Original",
        )

        async def override() -> User:
            return regular_user

        app.dependency_overrides[get_current_user] = override

        response = await base_client.patch(
            f"{USERS_URL}/{regular_user.id}",
            json={"first_name": "Updated"},
        )

        assert response.status_code == 200, (
            f"Non-admin user should be able to PATCH own profile via user:update:self. "
            f"Got {response.status_code}: {response.json()}"
        )
        assert response.json()["first_name"] == "Updated"

    @pytest.mark.asyncio
    async def test_non_admin_cannot_patch_other_user(
        self,
        base_client: AsyncClient,
        user_factory: Callable[..., Awaitable[User]],
    ) -> None:
        """A non-admin user cannot update someone else's profile."""
        from syntara.api.main import app

        acting_user = await user_factory(username="actor-user", email="actor@example.com")
        target_user = await user_factory(username="target-user", email="target@example.com")

        async def override() -> User:
            return acting_user

        app.dependency_overrides[get_current_user] = override

        response = await base_client.patch(
            f"{USERS_URL}/{target_user.id}",
            json={"first_name": "Hacked"},
        )

        assert response.status_code == 403


class TestUsersPatchAdminRestrictions:
    """Tests for admin self-disable restriction."""

    @pytest.mark.asyncio
    async def test_admin_can_disable_self(self, auth_client_as_admin: AsyncClient, admin_user: User) -> None:
        """Test admin can disable their own account."""
        patch_data = {"is_enabled": False}

        response = await auth_client_as_admin.patch(f"{USERS_URL}/{admin_user.id}", json=patch_data)

        assert response.status_code == 200

        data = response.json()
        assert data["is_enabled"] is False

    @pytest.mark.asyncio
    async def test_non_admin_cannot_disable_admin(
        self,
        base_client: AsyncClient,
        admin_user: User,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
    ) -> None:
        """Test non-admin user cannot disable the built-in admin account.

        Creates a dedicated limited-role user (with only 'user' role) and
        verifies they get 403 from PermissionChecker (no user:update permission).
        """
        from syntara.api.main import app

        limited_user = await user_factory(username="limited-patch", email="limited-patch@test.com")
        await make_user_role(test_db_session, limited_user)

        async def override_as_user() -> User:
            return limited_user

        app.dependency_overrides[get_current_user] = override_as_user
        patch_data = {"is_enabled": False}

        response = await base_client.patch(f"{USERS_URL}/{admin_user.id}", json=patch_data)

        # Non-admin user lacks user:update permission → 403
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_update_own_non_builtin_fields(
        self,
        base_client: AsyncClient,
        user_factory: Callable[..., Awaitable[User]],
        test_db_session: AsyncSession,
    ) -> None:
        """Test non-builtin admin can update their own non-is_enabled fields."""
        from syntara.api.main import app

        # Create a non-builtin admin user (is_builtin=False allows field updates)
        non_builtin_admin = await user_factory(
            username="non-builtin-admin", email="non-builtin-admin@test.com", is_builtin=False
        )
        await make_admin(test_db_session, non_builtin_admin)

        async def override_as_admin() -> User:
            return non_builtin_admin

        app.dependency_overrides[get_current_user] = override_as_admin

        patch_data = {"first_name": "Updated", "last_name": "Admin Name"}
        response = await base_client.patch(f"{USERS_URL}/{non_builtin_admin.id}", json=patch_data)

        assert response.status_code == 200

        data = response.json()
        assert data["first_name"] == "Updated"
        assert data["last_name"] == "Admin Name"

    @pytest.mark.asyncio
    async def test_admin_can_disable_and_reenable_self(self, admin_client: AsyncClient, admin_user: User) -> None:
        """Test admin can disable and re-enable their own account."""
        # Step 1: Admin disables itself
        disable_response = await admin_client.patch(f"{USERS_URL}/{admin_user.id}", json={"is_enabled": False})
        assert disable_response.status_code == 200

        # Step 2: Admin re-enables itself
        enable_response = await admin_client.patch(f"{USERS_URL}/{admin_user.id}", json={"is_enabled": True})
        assert enable_response.status_code == 200

        data = enable_response.json()
        assert data["is_enabled"] is True
