"""Unit tests for GroupMembershipService."""

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import Group, User
from syntara.core.models.group import user_groups
from syntara.core.services import GroupMembershipService


@pytest.fixture
async def service(test_db_session: AsyncSession) -> GroupMembershipService:
    """Create GroupMembershipService instance."""
    return GroupMembershipService(test_db_session)


@pytest.fixture
async def test_users(test_db_session: AsyncSession) -> dict[str, User]:
    """Create test users."""
    from syntara.auth.passwords import hash_password

    users = {
        "alice": User(
            username="alice",
            email="alice@example.com",
            first_name="Alice",
            password_hash=hash_password("password"),
            is_enabled=True,
        ),
        "bob": User(
            username="bob",
            email="bob@example.com",
            first_name="Bob",
            password_hash=hash_password("password"),
            is_enabled=True,
        ),
    }

    for user in users.values():
        test_db_session.add(user)

    await test_db_session.commit()

    for user in users.values():
        await test_db_session.refresh(user)

    return users


@pytest.fixture
async def test_groups(test_db_session: AsyncSession, test_users: dict[str, User]) -> dict[str, Group]:
    """Create test groups with user memberships."""
    groups = {
        "approvers": Group(name="test-approvers", description="Approvers group"),
        "admins": Group(name="test-admins", description="Admins group"),
        "developers": Group(name="test-developers", description="Developers group"),
    }

    for group in groups.values():
        test_db_session.add(group)

    await test_db_session.commit()

    for group in groups.values():
        await test_db_session.refresh(group)

    # Add alice to approvers and admins
    alice = test_users["alice"]
    await test_db_session.execute(user_groups.insert().values(user_id=alice.id, group_id=groups["approvers"].id))
    await test_db_session.execute(user_groups.insert().values(user_id=alice.id, group_id=groups["admins"].id))

    # Add bob to developers only
    bob = test_users["bob"]
    await test_db_session.execute(user_groups.insert().values(user_id=bob.id, group_id=groups["developers"].id))

    await test_db_session.commit()

    return groups


class TestGroupMembershipService:
    """Tests for GroupMembershipService."""

    async def test_user_in_single_group(
        self, service: GroupMembershipService, test_users: dict[str, User], test_groups: dict[str, Group]
    ):
        """Test that user in a single group returns True."""
        alice = test_users["alice"]
        result = await service.is_user_in_any_group(alice.id, ["test-approvers"])

        assert result is True

    async def test_user_in_multiple_groups(
        self, service: GroupMembershipService, test_users: dict[str, User], test_groups: dict[str, Group]
    ):
        """Test that user in multiple groups returns True."""
        alice = test_users["alice"]
        result = await service.is_user_in_any_group(alice.id, ["test-approvers", "test-admins"])

        assert result is True

    async def test_user_in_any_of_multiple_groups(
        self, service: GroupMembershipService, test_users: dict[str, User], test_groups: dict[str, Group]
    ):
        """Test that user in any of the specified groups returns True."""
        alice = test_users["alice"]
        # Alice is in "test-approvers" but not "test-developers"
        result = await service.is_user_in_any_group(alice.id, ["test-approvers", "test-developers"])

        assert result is True

    async def test_user_not_in_any_group(
        self, service: GroupMembershipService, test_users: dict[str, User], test_groups: dict[str, Group]
    ):
        """Test that user not in any of the specified groups returns False."""
        bob = test_users["bob"]
        # Bob is only in "test-developers", not in "test-approvers" or "test-admins"
        result = await service.is_user_in_any_group(bob.id, ["test-approvers", "test-admins"])

        assert result is False

    async def test_empty_group_list_returns_false(
        self, service: GroupMembershipService, test_users: dict[str, User], test_groups: dict[str, Group]
    ):
        """Test that empty group list returns False."""
        alice = test_users["alice"]
        result = await service.is_user_in_any_group(alice.id, [])

        assert result is False

    async def test_nonexistent_group_returns_false(
        self, service: GroupMembershipService, test_users: dict[str, User], test_groups: dict[str, Group]
    ):
        """Test that nonexistent group name returns False."""
        alice = test_users["alice"]
        result = await service.is_user_in_any_group(alice.id, ["nonexistent-group"])

        assert result is False

    async def test_case_sensitive_group_names(
        self, service: GroupMembershipService, test_users: dict[str, User], test_groups: dict[str, Group]
    ):
        """Test that group names are case-sensitive."""
        alice = test_users["alice"]
        # "Test-Approvers" (capital letters) should not match "test-approvers" (lowercase)
        result = await service.is_user_in_any_group(alice.id, ["Test-Approvers"])

        assert result is False

    async def test_mixed_existing_and_nonexistent_groups(
        self, service: GroupMembershipService, test_users: dict[str, User], test_groups: dict[str, Group]
    ):
        """Test with mix of existing and nonexistent groups."""
        alice = test_users["alice"]
        # Alice is in "test-approvers" but "fake-group" doesn't exist
        result = await service.is_user_in_any_group(alice.id, ["test-approvers", "fake-group"])

        assert result is True  # Should return True because alice is in "approvers"


class TestIsUserInAnyGroupByIds:
    """Test the is_user_in_any_group_by_ids method (ID-based lookup).

    This method is used by ApprovalService._is_user_authorized_approver for
    group-based authorization.
    """

    @pytest.mark.asyncio
    async def test_user_in_one_group(
        self, service: GroupMembershipService, test_users: dict[str, User], test_groups: dict[str, Group]
    ):
        """Test user is in one of the provided groups (by ID)."""
        alice = test_users["alice"]
        approvers_group = test_groups["approvers"]

        # Alice is a member of test-approvers group
        result = await service.is_user_in_any_group_by_ids(alice.id, [approvers_group.id])

        assert result is True

    @pytest.mark.asyncio
    async def test_user_in_multiple_groups(
        self, service: GroupMembershipService, test_users: dict[str, User], test_groups: dict[str, Group]
    ):
        """Test user in multiple groups."""
        alice = test_users["alice"]
        approvers_group = test_groups["approvers"]
        admins_group = test_groups["admins"]

        # Check if alice is in either group (she should be in both)
        result = await service.is_user_in_any_group_by_ids(alice.id, [approvers_group.id, admins_group.id])

        assert result is True

    @pytest.mark.asyncio
    async def test_user_not_in_any_group(
        self, service: GroupMembershipService, test_users: dict[str, User], test_groups: dict[str, Group]
    ):
        """Test user not in any of the provided groups."""
        bob = test_users["bob"]
        approvers_group = test_groups["approvers"]

        # Bob is NOT in test-approvers
        result = await service.is_user_in_any_group_by_ids(bob.id, [approvers_group.id])

        assert result is False

    @pytest.mark.asyncio
    async def test_nonexistent_group_ids(self, service: GroupMembershipService, test_users: dict[str, User]):
        """Test with non-existent group IDs."""
        from uuid import uuid4

        alice = test_users["alice"]
        fake_group_id = uuid4()

        # Fake group doesn't exist
        result = await service.is_user_in_any_group_by_ids(alice.id, [fake_group_id])

        assert result is False

    @pytest.mark.asyncio
    async def test_mixed_existing_and_nonexistent_group_ids(
        self, service: GroupMembershipService, test_users: dict[str, User], test_groups: dict[str, Group]
    ):
        """Test with mix of existing and nonexistent group IDs."""
        from uuid import uuid4

        alice = test_users["alice"]
        approvers_group = test_groups["approvers"]
        fake_group_id = uuid4()

        # Alice is in approvers but fake group doesn't exist
        result = await service.is_user_in_any_group_by_ids(alice.id, [approvers_group.id, fake_group_id])

        assert result is True

    @pytest.mark.asyncio
    async def test_empty_group_list(self, service: GroupMembershipService, test_users: dict[str, User]):
        """Test with empty group ID list."""
        alice = test_users["alice"]

        # Empty list should return False
        result = await service.is_user_in_any_group_by_ids(alice.id, [])

        assert result is False
