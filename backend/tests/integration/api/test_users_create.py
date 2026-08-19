"""Contract tests for POST /api/v1/users endpoint.

Tests user creation, validation, and conflict handling.
"""

import pytest
from httpx import AsyncClient

from tests.integration.helpers.error_data import assert_error_data

USERS_URL = "/api/v1/users"


class TestUsersCreateContract:
    """Contract tests for user creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_user_success(self, admin_client: AsyncClient) -> None:
        """Test successful user creation returns 201."""
        user_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "first_name": "New",
            "last_name": "User",
            "password": "SecurePassword123!",
        }

        response = await admin_client.post(USERS_URL, json=user_data)

        assert response.status_code == 201

        data = response.json()
        assert data["username"] == "newuser"
        assert data["email"] == "newuser@example.com"
        assert data["first_name"] == "New"
        assert data["last_name"] == "User"
        assert data["is_enabled"] is True  # default

    @pytest.mark.asyncio
    async def test_create_user_omitted_group_names_assigns_default_users_group(self, admin_client: AsyncClient) -> None:
        """Omitting group_names should assign users + authenticated groups.

        Note: relies on seeded built-in groups (or create_user fallback creation).
        """
        user_data = {
            "username": "defaultgroupuser",
            "email": "defaultgroupuser@example.com",
            "first_name": "Default",
            "last_name": "Group",
            "password": "SecurePassword123!",
        }

        response = await admin_client.post(USERS_URL, json=user_data)
        assert response.status_code == 201
        created = response.json()

        groups_response = await admin_client.get(f"{USERS_URL}/{created['id']}/groups")
        assert groups_response.status_code == 200
        group_names = {resource["name"] for resource in groups_response.json()["resources"]}
        assert group_names == {"users", "authenticated"}

    @pytest.mark.asyncio
    async def test_create_user_empty_group_names_skips_default_users_group(self, admin_client: AsyncClient) -> None:
        """Explicit empty group_names should skip default users group assignment."""
        user_data = {
            "username": "emptygroupuser",
            "email": "emptygroupuser@example.com",
            "first_name": "Empty",
            "last_name": "Group",
            "password": "SecurePassword123!",
            "group_names": [],
        }

        response = await admin_client.post(USERS_URL, json=user_data)
        assert response.status_code == 201
        created = response.json()

        groups_response = await admin_client.get(f"{USERS_URL}/{created['id']}/groups")
        assert groups_response.status_code == 200
        group_names = {resource["name"] for resource in groups_response.json()["resources"]}
        assert group_names == {"authenticated"}

    @pytest.mark.asyncio
    async def test_create_user_with_all_fields(self, admin_client: AsyncClient) -> None:
        """Test creating user with all explicit fields."""
        user_data = {
            "username": "fulluser",
            "email": "fulluser@example.com",
            "first_name": "Full",
            "last_name": "User",
            "password": "SecurePassword123!",
            "is_enabled": False,
        }

        response = await admin_client.post(USERS_URL, json=user_data)

        assert response.status_code == 201

        data = response.json()
        assert data["username"] == "fulluser"
        assert data["is_enabled"] is False

    @pytest.mark.asyncio
    async def test_create_user_response_schema(self, admin_client: AsyncClient) -> None:
        """Test response contains all required UserRead fields."""
        user_data = {
            "username": "schemauser",
            "email": "schemauser@example.com",
            "first_name": "Schema",
            "last_name": "User",
            "password": "SecurePassword123!",
        }

        response = await admin_client.post(USERS_URL, json=user_data)

        assert response.status_code == 201

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

        # Password should never be in response
        assert "password" not in data
        assert "password_hash" not in data

    @pytest.mark.asyncio
    async def test_create_user_no_password_in_response(self, admin_client: AsyncClient) -> None:
        """Test password is never returned in API response."""
        user_data = {
            "username": "nopwduser",
            "email": "nopwduser@example.com",
            "first_name": "No Password",
            "last_name": "User",
            "password": "SecurePassword123!",
        }

        response = await admin_client.post(USERS_URL, json=user_data)

        assert response.status_code == 201

        data = response.json()
        assert "password" not in data
        assert "password_hash" not in data

    @pytest.mark.asyncio
    async def test_create_user_duplicate_username(self, admin_client: AsyncClient) -> None:
        """Test 409 conflict when username already exists."""
        user_data = {
            "username": "dupuser",
            "email": "dupuser@example.com",
            "first_name": "Dup",
            "last_name": "User",
            "password": "SecurePassword123!",
        }

        # Create first user
        response1 = await admin_client.post(USERS_URL, json=user_data)
        assert response1.status_code == 201

        # Try to create second user with same username
        user_data["email"] = "different@example.com"
        response2 = await admin_client.post(USERS_URL, json=user_data)

        assert response2.status_code == 409
        assert_error_data(
            response2,
            error_type="https://api.example.com/errors/name-conflict",
            title="Username Conflict",
            detail="A user with this username already exists",
            code="USER_USERNAME_CONFLICT",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email_rejected(self, admin_client: AsyncClient) -> None:
        """Test that duplicate emails are rejected (email must be unique)."""
        user_data = {
            "username": "emailuser1",
            "email": "same@example.com",
            "first_name": "Email",
            "last_name": "User 1",
            "password": "SecurePassword123!",
        }

        # Create first user
        response1 = await admin_client.post(USERS_URL, json=user_data)
        assert response1.status_code == 201

        # Create second user with same email — should fail
        user_data["username"] = "emailuser2"
        user_data["first_name"] = "Email"
        user_data["last_name"] = "User 2"
        response2 = await admin_client.post(USERS_URL, json=user_data)

        assert response2.status_code == 409

    @pytest.mark.asyncio
    async def test_create_user_missing_username(self, admin_client: AsyncClient) -> None:
        """Test 422 when username is missing."""
        user_data = {
            "email": "nouser@example.com",
            "first_name": "No",
            "last_name": "Username",
            "password": "SecurePassword123!",
        }

        response = await admin_client.post(USERS_URL, json=user_data)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_user_without_email(self, admin_client: AsyncClient) -> None:
        """Test user can be created without email."""
        user_data = {
            "username": "noemail",
            "first_name": "No",
            "last_name": "Email",
            "password": "SecurePassword123!",
        }

        response = await admin_client.post(USERS_URL, json=user_data)

        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "noemail"
        assert data["email"] is None

    @pytest.mark.asyncio
    async def test_create_user_missing_password(self, admin_client: AsyncClient) -> None:
        """Test 422 when password is missing."""
        user_data = {
            "username": "nopwd",
            "email": "nopwd@example.com",
            "first_name": "No",
            "last_name": "Password",
        }

        response = await admin_client.post(USERS_URL, json=user_data)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_user_empty_username(self, admin_client: AsyncClient) -> None:
        """Test 422 when username is empty string."""
        user_data = {
            "username": "",
            "email": "empty@example.com",
            "first_name": "Empty",
            "last_name": "Username",
            "password": "SecurePassword123!",
        }

        response = await admin_client.post(USERS_URL, json=user_data)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_user_username_too_long(self, admin_client: AsyncClient) -> None:
        """Test 422 when username exceeds max length."""
        user_data = {
            "username": "x" * 256,
            "email": "long@example.com",
            "first_name": "Long",
            "last_name": "Username",
            "password": "SecurePassword123!",
        }

        response = await admin_client.post(USERS_URL, json=user_data)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_user_unauthenticated(self, base_client: AsyncClient) -> None:
        """Test creating a user requires authentication."""
        user_data = {
            "username": "unauth",
            "email": "unauth@example.com",
            "first_name": "Unauth",
            "last_name": "User",
            "password": "SecurePassword123!",
        }

        response = await base_client.post(USERS_URL, json=user_data)

        assert response.status_code == 401

    # ============================================================================
    # Password validation tests (API-46: InfoSec password requirements)
    # ============================================================================

    @pytest.mark.asyncio
    async def test_create_user_password_too_short(self, admin_client: AsyncClient) -> None:
        """Test password must be at least 14 characters."""
        user_data = {
            "username": "shortpwd",
            "email": "shortpwd@example.com",
            "first_name": "Short",
            "last_name": "Password",
            "password": "Short123!",  # Only 9 characters
        }

        response = await admin_client.post(USERS_URL, json=user_data)

        assert response.status_code == 422
        data = response.json()
        assert "at least 14 items" in str(data).lower()

    @pytest.mark.asyncio
    async def test_create_user_password_only_two_character_classes(self, admin_client: AsyncClient) -> None:
        """Test password must have at least 3 of 4 character classes."""
        user_data = {
            "username": "twoclasses",
            "email": "twoclasses@example.com",
            "first_name": "Two",
            "last_name": "Classes",
            "password": "lowercaseonly123456",  # Only lowercase + digits (2 classes)
        }

        response = await admin_client.post(USERS_URL, json=user_data)

        assert response.status_code == 422
        data = response.json()
        assert "at least 3" in str(data).lower()
        assert "character classes" in str(data).lower()

    @pytest.mark.asyncio
    async def test_create_user_password_valid_three_classes_upper_lower_digit(self, admin_client: AsyncClient) -> None:
        """Test valid password with uppercase, lowercase, and digits (3 of 4 classes)."""
        user_data = {
            "username": "threeclasses1",
            "email": "threeclasses1@example.com",
            "first_name": "Three",
            "last_name": "Classes 1",
            "password": "ValidPassword123",  # Uppercase + lowercase + digits
        }

        response = await admin_client.post(USERS_URL, json=user_data)

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_user_password_valid_three_classes_lower_digit_special(
        self, admin_client: AsyncClient
    ) -> None:
        """Test valid password with lowercase, digits, and special chars (3 of 4 classes)."""
        user_data = {
            "username": "threeclasses2",
            "email": "threeclasses2@example.com",
            "first_name": "Three",
            "last_name": "Classes 2",
            "password": "validpassword123!@#",  # Lowercase + digits + special
        }

        response = await admin_client.post(USERS_URL, json=user_data)

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_user_password_valid_four_classes(self, admin_client: AsyncClient) -> None:
        """Test valid password with all 4 character classes."""
        user_data = {
            "username": "fourclasses",
            "email": "fourclasses@example.com",
            "first_name": "Four",
            "last_name": "Classes",
            "password": "ValidPassword123!",  # All 4 classes
        }

        response = await admin_client.post(USERS_URL, json=user_data)

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_user_password_with_spaces(self, admin_client: AsyncClient) -> None:
        """Test password can contain spaces (counts as punctuation/other class)."""
        user_data = {
            "username": "spaceword",
            "email": "spaceword@example.com",
            "first_name": "Space",
            "last_name": "Password",
            "password": "Valid Password 123",  # Uppercase + lowercase + digits + space
        }

        response = await admin_client.post(USERS_URL, json=user_data)

        assert response.status_code == 201
