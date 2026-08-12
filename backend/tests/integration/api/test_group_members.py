"""Contract tests for group membership endpoints.

Tests adding, removing, and listing group members, as well as listing user groups.
"""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.core.models.group import Group
from tests.integration.helpers.error_data import assert_error_data

GROUPS_URL = "/api/v1/groups"
USERS_URL = "/api/v1/users"


class TestAddMember:
    """Tests for POST /auth/groups/{group_id}/members."""

    @pytest.mark.asyncio
    async def test_add_member_success(self, admin_client: AsyncClient, test_group: Group, test_user: User) -> None:
        """Test successfully adding a user to a group returns 201."""
        response = await admin_client.post(
            f"{GROUPS_URL}/{test_group.id}/members",
            json={"user_id": str(test_user.id)},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Member added successfully"

    @pytest.mark.asyncio
    async def test_add_member_already_exists(
        self, admin_client: AsyncClient, group_with_members: tuple[Group, list[User]]
    ) -> None:
        """Test 409 when adding a user who is already a member."""
        group, members = group_with_members
        existing_member = members[0]

        response = await admin_client.post(
            f"{GROUPS_URL}/{group.id}/members",
            json={"user_id": str(existing_member.id)},
        )

        assert response.status_code == 409
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/resource-conflict",
            title="Membership Conflict",
            detail="The user is already a member of this group",
            code="USER_ALREADY_IN_GROUP",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_add_member_group_not_found(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test 404 when group does not exist."""
        fake_group_id = "99999999-9999-9999-9999-999999999999"

        response = await admin_client.post(
            f"{GROUPS_URL}/{fake_group_id}/members",
            json={"user_id": str(test_user.id)},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_add_member_user_not_found(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test 404 when user does not exist."""
        fake_user_id = "99999999-9999-9999-9999-999999999999"

        response = await admin_client.post(
            f"{GROUPS_URL}/{test_group.id}/members",
            json={"user_id": fake_user_id},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_add_member_non_local_user(
        self, admin_client: AsyncClient, test_group: Group, non_local_user: User
    ) -> None:
        """Test that a non-local (federated) user can be added to a group."""
        response = await admin_client.post(
            f"{GROUPS_URL}/{test_group.id}/members",
            json={"user_id": str(non_local_user.id)},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Member added successfully"

    @pytest.mark.asyncio
    async def test_add_member_unauthenticated(
        self, base_client: AsyncClient, test_group: Group, test_user: User
    ) -> None:
        """Test adding a member requires authentication."""
        response = await base_client.post(
            f"{GROUPS_URL}/{test_group.id}/members",
            json={"user_id": str(test_user.id)},
        )

        assert response.status_code == 401


class TestRemoveMember:
    """Tests for DELETE /auth/groups/{group_id}/members/{user_id}."""

    @pytest.mark.asyncio
    async def test_remove_member_success(
        self, admin_client: AsyncClient, group_with_members: tuple[Group, list[User]]
    ) -> None:
        """Test successfully removing a member returns 204."""
        group, members = group_with_members
        member_to_remove = members[0]

        response = await admin_client.delete(
            f"{GROUPS_URL}/{group.id}/members/{member_to_remove.id}",
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_remove_member_not_a_member(
        self, admin_client: AsyncClient, test_group: Group, test_user: User
    ) -> None:
        """Test 404 when user is not a member of the group."""
        response = await admin_client.delete(
            f"{GROUPS_URL}/{test_group.id}/members/{test_user.id}",
        )

        assert response.status_code == 404
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/resource-not-found",
            title="Membership Not Found",
            detail="The user is not a member of this group",
            code="USER_NOT_IN_GROUP",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_remove_member_group_not_found(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test 404 when group does not exist."""
        fake_group_id = "99999999-9999-9999-9999-999999999999"

        response = await admin_client.delete(
            f"{GROUPS_URL}/{fake_group_id}/members/{test_user.id}",
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_remove_member_non_local_user(
        self, admin_client: AsyncClient, test_group: Group, non_local_user: User
    ) -> None:
        """Test that a non-local (federated) user can be added and removed from a group."""
        await admin_client.post(
            f"{GROUPS_URL}/{test_group.id}/members",
            json={"user_id": str(non_local_user.id)},
        )

        response = await admin_client.delete(
            f"{GROUPS_URL}/{test_group.id}/members/{non_local_user.id}",
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_remove_member_unauthenticated(
        self, base_client: AsyncClient, test_group: Group, test_user: User
    ) -> None:
        """Test removing a member requires authentication."""
        response = await base_client.delete(
            f"{GROUPS_URL}/{test_group.id}/members/{test_user.id}",
        )

        assert response.status_code == 401


class TestListMembers:
    """Tests for GET /auth/groups/{group_id}/members."""

    @pytest.mark.asyncio
    async def test_list_members_basic(
        self, admin_client: AsyncClient, group_with_members: tuple[Group, list[User]]
    ) -> None:
        """Test listing group members returns 200 with members."""
        group, members = group_with_members

        response = await admin_client.get(f"{GROUPS_URL}/{group.id}/members")

        assert response.status_code == 200

        data = response.json()
        assert "resources" in data
        assert len(data["resources"]) == len(members)

    @pytest.mark.asyncio
    async def test_list_members_response_schema(
        self, admin_client: AsyncClient, group_with_members: tuple[Group, list[User]]
    ) -> None:
        """Test each member in response includes required user fields."""
        group, _members = group_with_members

        response = await admin_client.get(f"{GROUPS_URL}/{group.id}/members")

        assert response.status_code == 200

        data = response.json()
        required_fields = ["id", "username", "email", "first_name", "is_enabled"]
        for member in data["resources"]:
            for field in required_fields:
                assert field in member, f"Missing required field: {field}"
            assert "password" not in member
            assert "password_hash" not in member

    @pytest.mark.asyncio
    async def test_list_members_empty_group(self, admin_client: AsyncClient, test_group: Group) -> None:
        """Test listing members of a group with no members."""
        response = await admin_client.get(f"{GROUPS_URL}/{test_group.id}/members")

        assert response.status_code == 200

        data = response.json()
        assert "resources" in data
        assert len(data["resources"]) == 0

    @pytest.mark.asyncio
    async def test_list_members_pagination(
        self, admin_client: AsyncClient, group_with_members: tuple[Group, list[User]]
    ) -> None:
        """Test pagination with limit parameter."""
        group, _members = group_with_members

        response = await admin_client.get(f"{GROUPS_URL}/{group.id}/members", params={"limit": 1})

        assert response.status_code == 200

        data = response.json()
        assert len(data["resources"]) == 1
        assert data.get("next") is not None

    @pytest.mark.asyncio
    async def test_list_members_group_not_found(self, admin_client: AsyncClient) -> None:
        """Test 404 when group does not exist."""
        fake_group_id = "99999999-9999-9999-9999-999999999999"

        response = await admin_client.get(f"{GROUPS_URL}/{fake_group_id}/members")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_members_unauthenticated(self, base_client: AsyncClient, test_group: Group) -> None:
        """Test listing members requires authentication."""
        response = await base_client.get(f"{GROUPS_URL}/{test_group.id}/members")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_members_sorted_by_username(
        self, admin_client: AsyncClient, group_with_members: tuple[Group, list[User]]
    ) -> None:
        """Test that members are sorted by username."""
        group, _members = group_with_members

        response = await admin_client.get(f"{GROUPS_URL}/{group.id}/members")

        assert response.status_code == 200

        data = response.json()
        usernames = [m["username"] for m in data["resources"]]
        assert usernames == sorted(usernames)


class TestListUserGroups:
    """Tests for GET /auth/users/{user_id}/groups."""

    @pytest.mark.asyncio
    async def test_list_user_groups_basic(
        self, admin_client: AsyncClient, group_with_members: tuple[Group, list[User]]
    ) -> None:
        """Test listing groups for a user returns 200 with groups."""
        group, members = group_with_members
        member = members[0]

        response = await admin_client.get(f"{USERS_URL}/{member.id}/groups")

        assert response.status_code == 200

        data = response.json()
        assert "resources" in data
        assert len(data["resources"]) >= 1

        group_ids = [g["id"] for g in data["resources"]]
        assert str(group.id) in group_ids

    @pytest.mark.asyncio
    async def test_list_user_groups_response_schema(
        self, admin_client: AsyncClient, group_with_members: tuple[Group, list[User]]
    ) -> None:
        """Test each group in response includes required fields."""
        _group, members = group_with_members
        member = members[0]

        response = await admin_client.get(f"{USERS_URL}/{member.id}/groups")

        assert response.status_code == 200

        data = response.json()
        required_fields = ["id", "name", "created_at", "updated_at"]
        for group in data["resources"]:
            for field in required_fields:
                assert field in group, f"Missing required field: {field}"

    @pytest.mark.asyncio
    async def test_list_user_groups_only_default(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test listing groups for a user with only default group membership."""
        response = await admin_client.get(f"{USERS_URL}/{test_user.id}/groups")

        assert response.status_code == 200

        data = response.json()
        assert "resources" in data
        # test_user is added to the test-users group by conftest for authz
        assert len(data["resources"]) >= 1

    @pytest.mark.asyncio
    async def test_list_user_groups_user_not_found(self, admin_client: AsyncClient) -> None:
        """Test 404 when user does not exist."""
        fake_user_id = "99999999-9999-9999-9999-999999999999"

        response = await admin_client.get(f"{USERS_URL}/{fake_user_id}/groups")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_user_groups_unauthenticated(self, base_client: AsyncClient, test_user: User) -> None:
        """Test listing user groups requires authentication."""
        response = await base_client.get(f"{USERS_URL}/{test_user.id}/groups")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_add_then_list_roundtrip(self, admin_client: AsyncClient, test_group: Group, test_user: User) -> None:
        """Test adding a member then listing groups for that user shows the group."""
        # Add member
        add_response = await admin_client.post(
            f"{GROUPS_URL}/{test_group.id}/members",
            json={"user_id": str(test_user.id)},
        )
        assert add_response.status_code == 201

        # List user's groups
        list_response = await admin_client.get(f"{USERS_URL}/{test_user.id}/groups")
        assert list_response.status_code == 200

        data = list_response.json()
        group_ids = [g["id"] for g in data["resources"]]
        assert str(test_group.id) in group_ids

    @pytest.mark.asyncio
    async def test_add_and_remove_roundtrip(
        self, admin_client: AsyncClient, test_group: Group, test_user: User
    ) -> None:
        """Test add, verify membership, remove, verify removal."""
        # Add
        add_response = await admin_client.post(
            f"{GROUPS_URL}/{test_group.id}/members",
            json={"user_id": str(test_user.id)},
        )
        assert add_response.status_code == 201

        # Verify listed
        list_response = await admin_client.get(f"{GROUPS_URL}/{test_group.id}/members")
        assert list_response.status_code == 200
        member_ids = [m["id"] for m in list_response.json()["resources"]]
        assert str(test_user.id) in member_ids

        # Remove
        remove_response = await admin_client.delete(
            f"{GROUPS_URL}/{test_group.id}/members/{test_user.id}",
        )
        assert remove_response.status_code == 204

        # Verify removed
        list_response2 = await admin_client.get(f"{GROUPS_URL}/{test_group.id}/members")
        assert list_response2.status_code == 200
        member_ids2 = [m["id"] for m in list_response2.json()["resources"]]
        assert str(test_user.id) not in member_ids2


class TestSetUserGroups:
    """Tests for PUT /auth/users/{user_id}/groups."""

    @pytest.mark.asyncio
    async def test_set_user_groups_success(
        self, admin_client: AsyncClient, test_user: User, multiple_test_groups: list[Group]
    ) -> None:
        """Test declaratively setting user groups returns 200 with the groups."""
        desired = multiple_test_groups[:2]
        group_ids = [str(g.id) for g in desired]

        response = await admin_client.put(
            f"{USERS_URL}/{test_user.id}/groups",
            json={"group_ids": group_ids},
        )

        assert response.status_code == 200

        data = response.json()
        assert "resources" in data
        returned_names = {g["name"] for g in data["resources"]}
        assert returned_names == {g.name for g in desired} | {"authenticated"}

    @pytest.mark.asyncio
    async def test_set_user_groups_replaces_existing(
        self, admin_client: AsyncClient, group_with_members: tuple[Group, list[User]], multiple_test_groups: list[Group]
    ) -> None:
        """Test that PUT replaces existing memberships with the new list."""
        old_group, members = group_with_members
        member = members[0]

        # member currently belongs to old_group; replace with two new groups
        new_groups = multiple_test_groups[:2]
        new_ids = [str(g.id) for g in new_groups]

        response = await admin_client.put(
            f"{USERS_URL}/{member.id}/groups",
            json={"group_ids": new_ids},
        )

        assert response.status_code == 200

        data = response.json()
        returned_names = {g["name"] for g in data["resources"]}
        assert returned_names == {g.name for g in new_groups} | {"authenticated"}
        assert old_group.name not in returned_names

    @pytest.mark.asyncio
    async def test_set_user_groups_empty_clears_all(
        self, admin_client: AsyncClient, group_with_members: tuple[Group, list[User]]
    ) -> None:
        """Test that sending an empty list retains only the authenticated group."""
        _group, members = group_with_members
        member = members[0]

        response = await admin_client.put(
            f"{USERS_URL}/{member.id}/groups",
            json={"group_ids": []},
        )

        assert response.status_code == 200

        data = response.json()
        returned_names = {g["name"] for g in data["resources"]}
        assert returned_names == {"authenticated"}

    @pytest.mark.asyncio
    async def test_set_user_groups_idempotent(
        self, admin_client: AsyncClient, test_user: User, multiple_test_groups: list[Group]
    ) -> None:
        """Test that setting the same groups twice is idempotent."""
        group_ids = [str(g.id) for g in multiple_test_groups[:2]]

        response1 = await admin_client.put(
            f"{USERS_URL}/{test_user.id}/groups",
            json={"group_ids": group_ids},
        )
        assert response1.status_code == 200

        response2 = await admin_client.put(
            f"{USERS_URL}/{test_user.id}/groups",
            json={"group_ids": group_ids},
        )
        assert response2.status_code == 200

        assert response1.json()["resources"] == response2.json()["resources"]

    @pytest.mark.asyncio
    async def test_set_user_groups_nonexistent_group(self, admin_client: AsyncClient, test_user: User) -> None:
        """Test 404 when a group ID does not exist."""
        fake_group_id = "99999999-9999-9999-9999-999999999999"

        response = await admin_client.put(
            f"{USERS_URL}/{test_user.id}/groups",
            json={"group_ids": [fake_group_id]},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_set_user_groups_nonexistent_user(
        self, admin_client: AsyncClient, multiple_test_groups: list[Group]
    ) -> None:
        """Test 404 when user does not exist."""
        fake_user_id = "99999999-9999-9999-9999-999999999999"
        group_ids = [str(g.id) for g in multiple_test_groups[:1]]

        response = await admin_client.put(
            f"{USERS_URL}/{fake_user_id}/groups",
            json={"group_ids": group_ids},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_set_user_groups_non_local_user(
        self, admin_client: AsyncClient, non_local_user: User, multiple_test_groups: list[Group]
    ) -> None:
        """Test that groups can be set for a non-local (federated) user."""
        group_ids = [str(g.id) for g in multiple_test_groups[:1]]

        response = await admin_client.put(
            f"{USERS_URL}/{non_local_user.id}/groups",
            json={"group_ids": group_ids},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_set_user_groups_unauthenticated(
        self, base_client: AsyncClient, test_user: User, multiple_test_groups: list[Group]
    ) -> None:
        """Test setting user groups requires authentication."""
        group_ids = [str(g.id) for g in multiple_test_groups[:1]]

        response = await base_client.put(
            f"{USERS_URL}/{test_user.id}/groups",
            json={"group_ids": group_ids},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_set_user_groups_non_admin_forbidden(
        self,
        base_client: AsyncClient,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        multiple_test_groups: list[Group],
    ) -> None:
        """Non-admin user cannot set their own groups (privilege escalation guard)."""
        low_priv_user = await user_factory(username="lowpriv", email="lowpriv@test.com")
        auth_as(low_priv_user)

        group_ids = [str(g.id) for g in multiple_test_groups[:1]]
        response = await base_client.put(
            f"{USERS_URL}/{low_priv_user.id}/groups",
            json={"group_ids": group_ids},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_set_user_groups_non_admin_cannot_escalate_to_admins(
        self,
        base_client: AsyncClient,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_db_session: AsyncSession,
    ) -> None:
        """Non-admin user cannot add themselves to the admins group."""
        low_priv_user = await user_factory(username="escalator", email="escalator@test.com")
        auth_as(low_priv_user)

        admins_group = (await test_db_session.exec(select(Group).where(Group.name == "admins"))).one()

        response = await base_client.put(
            f"{USERS_URL}/{low_priv_user.id}/groups",
            json={"group_ids": [str(admins_group.id)]},
        )

        assert response.status_code == 403
