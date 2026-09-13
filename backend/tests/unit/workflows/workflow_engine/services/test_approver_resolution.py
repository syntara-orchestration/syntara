"""Unit tests for ApproverResolutionService."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import Group, User
from syntara.workflows.workflow_engine.services.approver_resolution import ApproverResolutionService


@pytest.fixture
async def service(test_db_session: AsyncSession) -> ApproverResolutionService:
    """Create ApproverResolutionService instance."""
    return ApproverResolutionService(test_db_session)


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
async def test_groups(test_db_session: AsyncSession) -> dict[str, Group]:
    """Create test groups."""
    groups = {
        "approvers": Group(name="approvers", description="Approvers group"),
        "admins": Group(name="admins", description="Admins group"),
    }

    for group in groups.values():
        test_db_session.add(group)

    await test_db_session.commit()

    for group in groups.values():
        await test_db_session.refresh(group)

    return groups


class TestResolveUsernamesToIds:
    """Test the resolve_usernames_to_ids method."""

    @pytest.mark.asyncio
    async def test_resolve_existing_usernames(self, service: ApproverResolutionService, test_users: dict[str, User]):
        """Test resolving existing usernames to IDs."""
        alice = test_users["alice"]
        bob = test_users["bob"]

        result = await service.resolve_usernames_to_ids(["alice", "bob"])

        assert len(result) == 2
        assert alice.id in result
        assert bob.id in result

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_list(self, service: ApproverResolutionService):
        """Test that empty username list returns empty result."""
        result = await service.resolve_usernames_to_ids([])

        assert result == []

    @pytest.mark.asyncio
    async def test_nonexistent_username_filtered_out(
        self, service: ApproverResolutionService, test_users: dict[str, User]
    ):
        """Test that non-existent usernames are silently filtered out."""
        alice = test_users["alice"]

        result = await service.resolve_usernames_to_ids(["alice", "nonexistent"])

        # Only alice should be returned
        assert len(result) == 1
        assert alice.id in result

    @pytest.mark.asyncio
    async def test_deleted_user_not_found(self, service: ApproverResolutionService, test_users: dict[str, User]):
        """Test that non-existent usernames (e.g. hard-deleted users) are not resolved."""
        alice = test_users["alice"]

        result = await service.resolve_usernames_to_ids(["alice", "charlie"])

        # Only alice should be returned (charlie does not exist)
        assert len(result) == 1
        assert alice.id in result

    @pytest.mark.asyncio
    async def test_case_sensitive_usernames(self, service: ApproverResolutionService, test_users: dict[str, User]):
        """Test that username resolution is case-sensitive."""
        result = await service.resolve_usernames_to_ids(["Alice"])  # Capital A

        # Should not match "alice" (lowercase)
        assert result == []

    @pytest.mark.asyncio
    async def test_mix_of_valid_and_invalid_usernames(
        self, service: ApproverResolutionService, test_users: dict[str, User]
    ):
        """Test with mix of valid, invalid, and deleted usernames."""
        alice = test_users["alice"]
        bob = test_users["bob"]

        result = await service.resolve_usernames_to_ids(["alice", "nonexistent", "bob", "charlie", "another-fake"])

        # Only alice and bob should be returned (charlie and others do not exist)
        assert len(result) == 2
        assert alice.id in result
        assert bob.id in result

    @pytest.mark.asyncio
    async def test_filtering_behavior_with_nonexistent_users(
        self, service: ApproverResolutionService, test_users: dict[str, User]
    ):
        """Test that nonexistent usernames are filtered correctly."""
        alice = test_users["alice"]

        # Should filter out non-existent usernames
        result = await service.resolve_usernames_to_ids(["alice", "nonexistent", "charlie"])

        # Only alice should be returned (charlie and nonexistent don't exist)
        assert len(result) == 1
        assert alice.id in result

    @pytest.mark.asyncio
    async def test_all_usernames_successfully_resolved(
        self, service: ApproverResolutionService, test_users: dict[str, User]
    ):
        """Test that all valid usernames are successfully resolved."""
        alice = test_users["alice"]
        bob = test_users["bob"]

        result = await service.resolve_usernames_to_ids(["alice", "bob"])

        # Both alice and bob should be returned
        assert len(result) == 2
        assert alice.id in result
        assert bob.id in result


class TestResolveGroupNamesToIds:
    """Test the resolve_group_names_to_ids method."""

    @pytest.mark.asyncio
    async def test_resolve_existing_group_names(
        self, service: ApproverResolutionService, test_groups: dict[str, Group]
    ):
        """Test resolving existing group names to IDs."""
        approvers = test_groups["approvers"]
        admins = test_groups["admins"]

        result = await service.resolve_group_names_to_ids(["approvers", "admins"])

        assert len(result) == 2
        assert approvers.id in result
        assert admins.id in result

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_list(self, service: ApproverResolutionService):
        """Test that empty group name list returns empty result."""
        result = await service.resolve_group_names_to_ids([])

        assert result == []

    @pytest.mark.asyncio
    async def test_nonexistent_group_name_filtered_out(
        self, service: ApproverResolutionService, test_groups: dict[str, Group]
    ):
        """Test that non-existent group names are silently filtered out."""
        approvers = test_groups["approvers"]

        result = await service.resolve_group_names_to_ids(["approvers", "nonexistent"])

        # Only approvers should be returned
        assert len(result) == 1
        assert approvers.id in result

    @pytest.mark.asyncio
    async def test_deleted_group_not_found(self, service: ApproverResolutionService, test_groups: dict[str, Group]):
        """Test that non-existent groups (e.g. hard-deleted) are not resolved."""
        approvers = test_groups["approvers"]

        result = await service.resolve_group_names_to_ids(["approvers", "deleted-group"])

        # Only approvers should be returned (deleted-group does not exist)
        assert len(result) == 1
        assert approvers.id in result

    @pytest.mark.asyncio
    async def test_case_sensitive_group_names(self, service: ApproverResolutionService, test_groups: dict[str, Group]):
        """Test that group name resolution is case-sensitive."""
        result = await service.resolve_group_names_to_ids(["Approvers"])  # Capital A

        # Should not match "approvers" (lowercase)
        assert result == []

    @pytest.mark.asyncio
    async def test_mix_of_valid_and_invalid_group_names(
        self, service: ApproverResolutionService, test_groups: dict[str, Group]
    ):
        """Test with mix of valid, invalid, and deleted group names."""
        approvers = test_groups["approvers"]
        admins = test_groups["admins"]

        result = await service.resolve_group_names_to_ids(
            ["approvers", "nonexistent", "admins", "deleted-group", "another-fake"]
        )

        # Only approvers and admins should be returned (others do not exist)
        assert len(result) == 2
        assert approvers.id in result
        assert admins.id in result

    @pytest.mark.asyncio
    async def test_filtering_behavior_with_nonexistent_groups(
        self, service: ApproverResolutionService, test_groups: dict[str, Group]
    ):
        """Test that nonexistent group names are filtered correctly."""
        approvers = test_groups["approvers"]

        # Should filter out non-existent group names
        result = await service.resolve_group_names_to_ids(["approvers", "nonexistent", "deleted-group"])

        # Only approvers should be returned (deleted-group and nonexistent don't exist)
        assert len(result) == 1
        assert approvers.id in result

    @pytest.mark.asyncio
    async def test_all_group_names_successfully_resolved(
        self, service: ApproverResolutionService, test_groups: dict[str, Group]
    ):
        """Test that all valid group names are successfully resolved."""
        approvers = test_groups["approvers"]
        admins = test_groups["admins"]

        result = await service.resolve_group_names_to_ids(["approvers", "admins"])

        # Both approvers and admins should be returned
        assert len(result) == 2
        assert approvers.id in result
        assert admins.id in result
