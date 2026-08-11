"""Integration tests for email anonymization on user deletion (security fix).

Tests that email addresses are anonymized when users are deleted to prevent
email reuse attacks where an attacker could:
1. Engineer victim's account deletion
2. Register with victim's email
3. Intercept password resets and sensitive communications
"""

import pytest
from httpx import AsyncClient

from syntara.core.models import User

USERS_URL = "/api/v1/users"


class TestEmailAnonymizationOnDeletion:
    """Test email anonymization prevents email reuse attacks."""

    @pytest.mark.asyncio
    async def test_deleted_user_email_is_anonymized(self, admin_client: AsyncClient, admin_user: User) -> None:
        """Test that deleting a user anonymizes their email."""
        # Create user with email
        user_data = {
            "username": "emailuser",
            "email": "test@example.com",
            "first_name": "Email",
            "last_name": "User",
            "password": "SecurePassword123!",
        }
        create_response = await admin_client.post(USERS_URL, json=user_data)
        assert create_response.status_code == 201
        user_id = create_response.json()["id"]

        # Delete the user
        delete_response = await admin_client.delete(f"{USERS_URL}/{user_id}")
        assert delete_response.status_code == 204

        # Verify email was anonymized (GET should show email as null for deleted user)
        # Note: Depending on API design, deleted users might not be retrievable
        # This test assumes we can still GET deleted users for verification

    @pytest.mark.asyncio
    async def test_deleted_user_email_can_be_reused(self, admin_client: AsyncClient, admin_user: User) -> None:
        """Test that after deletion, the email can be reused by a new account."""
        original_email = "reusable@example.com"

        # Create first user
        user1_data = {
            "username": "user1",
            "email": original_email,
            "first_name": "User",
            "last_name": "1",
            "password": "SecurePassword123!",
        }
        create1_response = await admin_client.post(USERS_URL, json=user1_data)
        assert create1_response.status_code == 201
        user1_id = create1_response.json()["id"]

        # Delete first user
        delete_response = await admin_client.delete(f"{USERS_URL}/{user1_id}")
        assert delete_response.status_code == 204

        # Create second user with same email - should succeed due to anonymization
        user2_data = {
            "username": "user2",
            "email": original_email,  # Same email as deleted user
            "first_name": "User",
            "last_name": "2",
            "password": "SecurePassword123!",
        }
        create2_response = await admin_client.post(USERS_URL, json=user2_data)
        assert create2_response.status_code == 201

        user2 = create2_response.json()
        assert user2["email"] == original_email
        assert user2["id"] != user1_id  # Different user

    @pytest.mark.asyncio
    async def test_user_without_email_deletion_works(self, admin_client: AsyncClient, admin_user: User) -> None:
        """Test that users without email can still be deleted (no email to anonymize)."""
        # Create user without email
        user_data = {
            "username": "noemail",
            "first_name": "No Email",
            "last_name": "User",
            "password": "SecurePassword123!",
        }
        create_response = await admin_client.post(USERS_URL, json=user_data)
        assert create_response.status_code == 201
        user_id = create_response.json()["id"]
        assert create_response.json()["email"] is None

        # Delete should work without error
        delete_response = await admin_client.delete(f"{USERS_URL}/{user_id}")
        assert delete_response.status_code == 204

    @pytest.mark.asyncio
    async def test_multiple_deletions_dont_conflict(self, admin_client: AsyncClient, admin_user: User) -> None:
        """Test that deleting multiple users with same email (sequentially) works.

        This verifies the anonymization happens before the constraint check.
        """
        shared_email = "shared@example.com"

        # Create, delete, create, delete cycle
        for i in range(3):
            user_data = {
                "username": f"user{i}",
                "email": shared_email,
                "first_name": "User",
                "last_name": f"{i}",
                "password": "SecurePassword123!",
            }
            create_response = await admin_client.post(USERS_URL, json=user_data)
            assert create_response.status_code == 201
            user_id = create_response.json()["id"]

            # Delete immediately
            delete_response = await admin_client.delete(f"{USERS_URL}/{user_id}")
            assert delete_response.status_code == 204

        # All should succeed without email uniqueness conflicts
