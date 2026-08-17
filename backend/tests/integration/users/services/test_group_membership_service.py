"""Unit tests for GroupsService membership and CRUD operations.

Tests cover:
- Adding members to groups
- Removing members from groups
- Listing group members
- Listing user groups
- Declarative set_user_groups
- Group CRUD (create, update, delete)
- Helper methods (member counts, enrich, duplicate checks)
- Error conditions (not found, duplicate)
"""

from uuid import UUID, uuid4

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth.exceptions import (
    GroupNameConflictError,
    GroupNotFoundError,
    UserAlreadyInGroupError,
    UserNotFoundError,
    UserNotInGroupError,
)
from syntara.auth.passwords import hash_password
from syntara.auth.services.idp_group_sync import sync_idp_groups
from syntara.authz.resolver import AUTHENTICATED_GROUP_NAME
from syntara.core.exceptions import SafeValueError
from syntara.core.models import User, UserIdentity
from syntara.core.models.group import Group, user_groups, user_idp_groups
from syntara.identity_providers.models.identity_provider import IdentityProvider
from syntara.identity_providers.models.identity_provider_configuration import OIDCConfiguration
from syntara.identity_providers.models.idp_group_mapping import IdpGroupMappingEntry
from syntara.users.services.group_service import GroupsService

TEST_PASSWORD = "securepassword123"  # noqa: S105


async def _create_test_user(session: AsyncSession, username: str, email: str) -> User:
    """Create a test user directly in the database."""
    user = User(
        id=uuid4(),
        username=username,
        email=email,
        first_name="Test",
        last_name=username,
        password_hash=hash_password(TEST_PASSWORD),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _create_test_group(session: AsyncSession, name: str, created_by: User) -> Group:
    """Create a test group directly in the database."""
    group = Group(
        id=uuid4(),
        name=name,
        description=f"Test group {name}",
        created_by=created_by.id,
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


@pytest.mark.asyncio
async def test_add_member_success(test_db_session: AsyncSession, test_user: User) -> None:
    """Test successfully adding a user to a group."""
    service = GroupsService(test_db_session, test_user)
    group = await _create_test_group(test_db_session, "membership-group", test_user)
    member = await _create_test_user(test_db_session, "member1", "member1@example.com")

    await service.add_member(group.id, member.id)

    # Verify membership via list_members
    result = await service.list_members(group.id)
    assert len(result.resources) == 1
    assert result.resources[0].id == member.id


@pytest.mark.asyncio
async def test_add_member_already_exists(test_db_session: AsyncSession, test_user: User) -> None:
    """Test UserAlreadyInGroupError on duplicate membership."""
    service = GroupsService(test_db_session, test_user)
    group = await _create_test_group(test_db_session, "dup-group", test_user)
    member = await _create_test_user(test_db_session, "dupmember", "dupmember@example.com")

    await service.add_member(group.id, member.id)

    with pytest.raises(UserAlreadyInGroupError):
        await service.add_member(group.id, member.id)


@pytest.mark.asyncio
async def test_add_member_group_not_found(test_db_session: AsyncSession, test_user: User) -> None:
    """Test GroupNotFoundError when group does not exist."""
    service = GroupsService(test_db_session, test_user)

    with pytest.raises(GroupNotFoundError):
        await service.add_member(uuid4(), test_user.id)


@pytest.mark.asyncio
async def test_add_member_user_not_found(test_db_session: AsyncSession, test_user: User) -> None:
    """Test UserNotFoundError when user does not exist."""
    service = GroupsService(test_db_session, test_user)
    group = await _create_test_group(test_db_session, "nouser-group", test_user)

    with pytest.raises(UserNotFoundError):
        await service.add_member(group.id, uuid4())


@pytest.mark.asyncio
async def test_remove_member_success(test_db_session: AsyncSession, test_user: User) -> None:
    """Test successfully removing a member from a group."""
    service = GroupsService(test_db_session, test_user)
    group = await _create_test_group(test_db_session, "remove-group", test_user)
    member = await _create_test_user(test_db_session, "removemember", "remove@example.com")

    await service.add_member(group.id, member.id)
    await service.remove_member(group.id, member.id)

    # Verify membership removed
    result = await service.list_members(group.id)
    assert len(result.resources) == 0


@pytest.mark.asyncio
async def test_remove_member_not_a_member(test_db_session: AsyncSession, test_user: User) -> None:
    """Test UserNotInGroupError when user is not a member."""
    service = GroupsService(test_db_session, test_user)
    group = await _create_test_group(test_db_session, "notmember-group", test_user)

    with pytest.raises(UserNotInGroupError):
        await service.remove_member(group.id, test_user.id)


@pytest.mark.asyncio
async def test_remove_member_group_not_found(test_db_session: AsyncSession, test_user: User) -> None:
    """Test GroupNotFoundError when group does not exist."""
    service = GroupsService(test_db_session, test_user)

    with pytest.raises(GroupNotFoundError):
        await service.remove_member(uuid4(), test_user.id)


@pytest.mark.asyncio
async def test_list_members_empty(test_db_session: AsyncSession, test_user: User) -> None:
    """Test listing members of a group with no members."""
    service = GroupsService(test_db_session, test_user)
    group = await _create_test_group(test_db_session, "empty-group", test_user)

    result = await service.list_members(group.id)

    assert len(result.resources) == 0
    assert result.next is None


@pytest.mark.asyncio
async def test_list_members_with_results(test_db_session: AsyncSession, test_user: User) -> None:
    """Test listing members returns correct users."""
    service = GroupsService(test_db_session, test_user)
    group = await _create_test_group(test_db_session, "populated-group", test_user)

    members = []
    for i in range(3):
        member = await _create_test_user(test_db_session, f"listmember{i}", f"listmember{i}@example.com")
        await service.add_member(group.id, member.id)
        members.append(member)

    result = await service.list_members(group.id)

    assert len(result.resources) == 3
    result_ids = {r.id for r in result.resources}
    for m in members:
        assert m.id in result_ids


@pytest.mark.asyncio
async def test_list_members_pagination(test_db_session: AsyncSession, test_user: User) -> None:
    """Test pagination of group members."""
    service = GroupsService(test_db_session, test_user)
    group = await _create_test_group(test_db_session, "paginate-group", test_user)

    for i in range(5):
        member = await _create_test_user(test_db_session, f"pagemember{i}", f"pagemember{i}@example.com")
        await service.add_member(group.id, member.id)

    # Get first page
    result1 = await service.list_members(group.id, limit=2)
    assert len(result1.resources) == 2
    assert result1.next is not None

    # Get second page using cursor
    result2 = await service.list_members(group.id, limit=2, cursor=result1.next)
    assert len(result2.resources) == 2
    assert result2.next is not None

    # Verify no overlap
    page1_ids = {r.id for r in result1.resources}
    page2_ids = {r.id for r in result2.resources}
    assert page1_ids.isdisjoint(page2_ids)


@pytest.mark.asyncio
async def test_list_members_sorted_by_username(test_db_session: AsyncSession, test_user: User) -> None:
    """Test members are sorted by username."""
    service = GroupsService(test_db_session, test_user)
    group = await _create_test_group(test_db_session, "sort-group", test_user)

    # Create users with specific usernames to verify sorting
    for name in ["charlie_sort", "alice_sort", "bob_sort"]:
        member = await _create_test_user(test_db_session, name, f"{name}@example.com")
        await service.add_member(group.id, member.id)

    result = await service.list_members(group.id)
    usernames = [r.username for r in result.resources]
    assert usernames == sorted(usernames)


@pytest.mark.asyncio
async def test_list_members_group_not_found(test_db_session: AsyncSession, test_user: User) -> None:
    """Test GroupNotFoundError when listing members of non-existent group."""
    service = GroupsService(test_db_session, test_user)

    with pytest.raises(GroupNotFoundError):
        await service.list_members(uuid4())


@pytest.mark.asyncio
async def test_list_user_groups_empty(test_db_session: AsyncSession, test_user: User) -> None:
    """Test listing groups for a user with no explicit memberships returns only authenticated."""
    service = GroupsService(test_db_session, test_user)

    result = await service.list_user_groups(test_user.id)

    assert {g.name for g in result.resources} == {AUTHENTICATED_GROUP_NAME}
    assert result.next is None


@pytest.mark.asyncio
async def test_list_user_groups_with_results(test_db_session: AsyncSession, test_user: User) -> None:
    """Test listing groups for a user with memberships."""
    service = GroupsService(test_db_session, test_user)
    member = await _create_test_user(test_db_session, "groupsuser", "groupsuser@example.com")

    groups = []
    for i in range(3):
        group = await _create_test_group(test_db_session, f"usergroup{i}", test_user)
        await service.add_member(group.id, member.id)
        groups.append(group)

    result = await service.list_user_groups(member.id)

    assert len(result.resources) == 3
    result_ids = {r.id for r in result.resources}
    for g in groups:
        assert g.id in result_ids


@pytest.mark.asyncio
async def test_list_user_groups_pagination(test_db_session: AsyncSession, test_user: User) -> None:
    """Test pagination of user groups."""
    service = GroupsService(test_db_session, test_user)
    member = await _create_test_user(test_db_session, "pageuser", "pageuser@example.com")

    for i in range(5):
        group = await _create_test_group(test_db_session, f"pagegroup{i}", test_user)
        await service.add_member(group.id, member.id)

    # Get first page
    result1 = await service.list_user_groups(member.id, limit=2)
    assert len(result1.resources) == 2
    assert result1.next is not None

    # Get second page using cursor
    result2 = await service.list_user_groups(member.id, limit=2, cursor=result1.next)
    assert len(result2.resources) == 2
    assert result2.next is not None

    # Verify no overlap
    page1_ids = {r.id for r in result1.resources}
    page2_ids = {r.id for r in result2.resources}
    assert page1_ids.isdisjoint(page2_ids)


@pytest.mark.asyncio
async def test_list_user_groups_user_not_found(test_db_session: AsyncSession, test_user: User) -> None:
    """Test UserNotFoundError when listing groups for non-existent user."""
    service = GroupsService(test_db_session, test_user)

    with pytest.raises(UserNotFoundError):
        await service.list_user_groups(uuid4())


@pytest.mark.asyncio
async def test_list_user_groups_sorted_by_name(test_db_session: AsyncSession, test_user: User) -> None:
    """Test user groups are sorted by group name."""
    service = GroupsService(test_db_session, test_user)
    member = await _create_test_user(test_db_session, "sortgroupuser", "sortgroupuser@example.com")

    for name in ["Gamma Group", "Alpha Group", "Beta Group"]:
        group = await _create_test_group(test_db_session, name, test_user)
        await service.add_member(group.id, member.id)

    result = await service.list_user_groups(member.id)
    names = [r.name for r in result.resources]
    assert names == sorted(names)


# ============================================================================
# set_user_groups tests
# ============================================================================


@pytest.mark.asyncio
async def test_set_user_groups_success(test_db_session: AsyncSession, test_user: User) -> None:
    """Test declaratively setting user groups adds new and removes old memberships."""
    service = GroupsService(test_db_session, test_user)
    member = await _create_test_user(test_db_session, "setuser", "setuser@example.com")

    group_a = await _create_test_group(test_db_session, "set-group-a", test_user)
    group_b = await _create_test_group(test_db_session, "set-group-b", test_user)
    group_c = await _create_test_group(test_db_session, "set-group-c", test_user)

    # Start with group_a membership
    await service.add_member(group_a.id, member.id)

    # Set to group_b and group_c (should add b, c and remove a)
    result = await service.set_user_groups(member.id, [group_b.id, group_c.id])

    result_ids = {r.id for r in result.resources}
    assert group_b.id in result_ids
    assert group_c.id in result_ids
    assert group_a.id not in result_ids


@pytest.mark.asyncio
async def test_set_user_groups_empty_clears_all(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that setting empty list removes all memberships except authenticated."""
    service = GroupsService(test_db_session, test_user)
    member = await _create_test_user(test_db_session, "clearuser", "clearuser@example.com")

    group = await _create_test_group(test_db_session, "clear-group", test_user)
    await service.add_member(group.id, member.id)

    result = await service.set_user_groups(member.id, [])

    assert {g.name for g in result.resources} == {AUTHENTICATED_GROUP_NAME}


@pytest.mark.asyncio
async def test_set_user_groups_user_not_found(test_db_session: AsyncSession, test_user: User) -> None:
    """Test UserNotFoundError when user does not exist."""
    service = GroupsService(test_db_session, test_user)
    group = await _create_test_group(test_db_session, "orphan-group", test_user)

    with pytest.raises(UserNotFoundError):
        await service.set_user_groups(uuid4(), [group.id])


@pytest.mark.asyncio
async def test_set_user_groups_group_not_found(test_db_session: AsyncSession, test_user: User) -> None:
    """Test GroupNotFoundError when a group ID does not exist."""
    service = GroupsService(test_db_session, test_user)

    with pytest.raises(GroupNotFoundError):
        await service.set_user_groups(test_user.id, [uuid4()])


@pytest.mark.asyncio
async def test_set_user_groups_idempotent(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that setting the same groups twice is a no-op."""
    service = GroupsService(test_db_session, test_user)
    member = await _create_test_user(test_db_session, "idempotentuser", "idempotent@example.com")

    group_a = await _create_test_group(test_db_session, "idem-group-a", test_user)
    group_b = await _create_test_group(test_db_session, "idem-group-b", test_user)

    desired = [group_a.id, group_b.id]

    result1 = await service.set_user_groups(member.id, desired)
    result2 = await service.set_user_groups(member.id, desired)

    ids1 = {r.id for r in result1.resources}
    ids2 = {r.id for r in result2.resources}
    assert ids1 == ids2


# ============================================================================
# Group CRUD tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_group_success(test_db_session: AsyncSession, test_user: User) -> None:
    """Test creating a group via the service."""
    service = GroupsService(test_db_session, test_user)

    group = await service.create_group(name="new-group", description="A test group")

    assert group.name == "new-group"
    assert group.description == "A test group"
    assert group.created_by == test_user.id


@pytest.mark.asyncio
async def test_create_group_duplicate_name(test_db_session: AsyncSession, test_user: User) -> None:
    """Test GroupNameConflictError on duplicate group name."""
    service = GroupsService(test_db_session, test_user)

    await service.create_group(name="unique-group", description=None)

    with pytest.raises(GroupNameConflictError):
        await service.create_group(name="unique-group", description=None)


@pytest.mark.asyncio
async def test_update_group_name(test_db_session: AsyncSession, test_user: User) -> None:
    """Test updating a group's name."""
    service = GroupsService(test_db_session, test_user)
    group = await service.create_group(name="old-name", description=None)

    updated = await service.update_group(group.id, name="new-name")

    assert updated.name == "new-name"


@pytest.mark.asyncio
async def test_update_group_description(test_db_session: AsyncSession, test_user: User) -> None:
    """Test updating a group's description."""
    service = GroupsService(test_db_session, test_user)
    group = await service.create_group(name="desc-group", description="old desc")

    updated = await service.update_group(group.id, description="new desc")

    assert updated.description == "new desc"


@pytest.mark.asyncio
async def test_update_group_empty_name_raises(test_db_session: AsyncSession, test_user: User) -> None:
    """Test SafeValueError when setting group name to empty string."""
    service = GroupsService(test_db_session, test_user)
    group = await service.create_group(name="valid-name", description=None)

    with pytest.raises(SafeValueError, match="cannot be empty"):
        await service.update_group(group.id, name="")


@pytest.mark.asyncio
async def test_update_group_not_found(test_db_session: AsyncSession, test_user: User) -> None:
    """Test GroupNotFoundError when updating non-existent group."""
    service = GroupsService(test_db_session, test_user)

    with pytest.raises(GroupNotFoundError):
        await service.update_group(uuid4(), name="whatever")


@pytest.mark.asyncio
async def test_update_group_duplicate_name(test_db_session: AsyncSession, test_user: User) -> None:
    """Test GroupNameConflictError when renaming to an existing name."""
    service = GroupsService(test_db_session, test_user)
    await service.create_group(name="taken-name", description=None)
    group = await service.create_group(name="other-name", description=None)

    with pytest.raises(GroupNameConflictError):
        await service.update_group(group.id, name="taken-name")


@pytest.mark.asyncio
async def test_delete_group(test_db_session: AsyncSession, test_user: User) -> None:
    """Test soft deleting a group."""
    service = GroupsService(test_db_session, test_user)
    group = await service.create_group(name="delete-me", description=None)

    await service.delete_group(group.id)

    # Should not be findable after soft delete
    with pytest.raises(GroupNotFoundError):
        await service.get_group_by_id(group.id)


@pytest.mark.asyncio
async def test_delete_group_not_found(test_db_session: AsyncSession, test_user: User) -> None:
    """Test GroupNotFoundError when deleting non-existent group."""
    service = GroupsService(test_db_session, test_user)

    with pytest.raises(GroupNotFoundError):
        await service.delete_group(uuid4())


# ============================================================================
# Helper method tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_member_count(test_db_session: AsyncSession, test_user: User) -> None:
    """Test getting member count for a single group."""
    service = GroupsService(test_db_session, test_user)
    group = await service.create_group(name="count-group", description=None)

    assert await service.get_member_count(group) == 0

    member = await _create_test_user(test_db_session, "countuser", "count@example.com")
    await service.add_member(group.id, member.id)

    assert await service.get_member_count(group) == 1


@pytest.mark.asyncio
async def test_get_member_counts_empty(test_db_session: AsyncSession, test_user: User) -> None:
    """Test get_member_counts with empty list."""
    service = GroupsService(test_db_session, test_user)

    result = await service.get_member_counts([])
    assert result == {}


@pytest.mark.asyncio
async def test_get_member_counts_multiple_groups(test_db_session: AsyncSession, test_user: User) -> None:
    """Test get_member_counts returns correct counts for multiple groups."""
    service = GroupsService(test_db_session, test_user)
    group_a = await service.create_group(name="count-a", description=None)
    group_b = await service.create_group(name="count-b", description=None)

    member1 = await _create_test_user(test_db_session, "cntuser1", "cnt1@example.com")
    member2 = await _create_test_user(test_db_session, "cntuser2", "cnt2@example.com")

    await service.add_member(group_a.id, member1.id)
    await service.add_member(group_a.id, member2.id)
    await service.add_member(group_b.id, member1.id)

    counts = await service.get_member_counts([group_a.id, group_b.id])
    assert counts[group_a.id] == 2
    assert counts[group_b.id] == 1


@pytest.mark.asyncio
async def test_enrich_group_read(test_db_session: AsyncSession, test_user: User) -> None:
    """Test enrich_group_read converts Group to GroupRead with member_count."""
    service = GroupsService(test_db_session, test_user)
    group = await service.create_group(name="enrich-group", description="test")

    read = service.enrich_group_read(group, member_count=42)

    assert read.name == "enrich-group"
    assert read.member_count == 42


@pytest.mark.asyncio
async def test_convert_resource_mixin(test_db_session: AsyncSession, test_user: User) -> None:
    """Test GroupConvertResourceMixin.convert_resource."""
    service = GroupsService(test_db_session, test_user)
    group = await service.create_group(name="convert-group", description="test")

    read = service.convert_resource_mixin.convert_resource(group)

    assert read.name == "convert-group"
    assert read.id == group.id


# ============================================================================
# Membership source tests
# ============================================================================


async def _create_identity_provider(session: AsyncSession, name: str, created_by: User) -> IdentityProvider:
    """Create a test identity provider."""
    provider = IdentityProvider(
        id=uuid4(),
        name=name,
        description=f"Test provider {name}",
        enabled=True,
        configuration=OIDCConfiguration(
            provider_type="oidc",
            issuer_url=f"https://{name}.example.com",
            client_id="test-client",
            client_secret="test-secret",  # noqa: S106
            redirect_uri="http://localhost:8000/callback",
        ),
        created_by=created_by.id,
        updated_by=created_by.id,
    )
    session.add(provider)
    await session.commit()
    await session.refresh(provider)
    return provider


@pytest.mark.asyncio
async def test_list_members_manual_source(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that manually added members have 'manual' membership source."""
    service = GroupsService(test_db_session, test_user)
    group = await _create_test_group(test_db_session, "source-manual-group", test_user)
    member = await _create_test_user(test_db_session, "src-manual", "srcmanual@example.com")

    await service.add_member(group.id, member.id)

    result = await service.list_members(group.id)
    assert len(result.resources) == 1
    assert len(result.resources[0].membership_sources) == 1
    assert result.resources[0].membership_sources[0].type == "manual"
    assert result.resources[0].membership_sources[0].provider_name is None


@pytest.mark.asyncio
async def test_list_members_idp_source(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that IdP-tracked members have 'idp' membership source with provider info."""
    service = GroupsService(test_db_session, test_user)
    group = await _create_test_group(test_db_session, "source-idp-group", test_user)
    member = await _create_test_user(test_db_session, "src-idp", "srcidp@example.com")
    provider = await _create_identity_provider(test_db_session, "azure-idp", test_user)

    await service.add_member(group.id, member.id)

    # Simulate IdP tracking entry
    await test_db_session.exec(
        user_idp_groups.insert().values(
            user_id=member.id,
            identity_provider_id=provider.id,
            group_id=group.id,
        )
    )
    await test_db_session.commit()

    result = await service.list_members(group.id)
    assert len(result.resources) == 1
    sources = result.resources[0].membership_sources
    assert any(s.type == "idp" and s.provider_name == "azure-idp" for s in sources)


@pytest.mark.asyncio
async def test_list_user_groups_manual_source(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that user groups without IdP tracking show 'manual' source."""
    service = GroupsService(test_db_session, test_user)
    group = await _create_test_group(test_db_session, "usr-src-manual", test_user)
    member = await _create_test_user(test_db_session, "usr-manual", "usrmanual@example.com")

    await service.add_member(group.id, member.id)

    result = await service.list_user_groups(member.id)
    assert len(result.resources) == 1
    assert len(result.resources[0].membership_sources) == 1
    assert result.resources[0].membership_sources[0].type == "manual"


@pytest.mark.asyncio
async def test_list_user_groups_idp_source(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that user groups with IdP tracking show 'idp' source."""
    service = GroupsService(test_db_session, test_user)
    group = await _create_test_group(test_db_session, "usr-src-idp", test_user)
    member = await _create_test_user(test_db_session, "usr-idp", "usridp@example.com")
    provider = await _create_identity_provider(test_db_session, "keycloak-idp", test_user)

    await service.add_member(group.id, member.id)

    await test_db_session.exec(
        user_idp_groups.insert().values(
            user_id=member.id,
            identity_provider_id=provider.id,
            group_id=group.id,
        )
    )
    await test_db_session.commit()

    result = await service.list_user_groups(member.id)
    assert len(result.resources) == 1
    sources = result.resources[0].membership_sources
    assert any(s.type == "idp" and s.provider_name == "keycloak-idp" for s in sources)


@pytest.mark.asyncio
async def test_membership_sources_empty_groups(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that _get_membership_sources returns empty dict for empty group list."""
    service = GroupsService(test_db_session, test_user)
    result = await service._get_membership_sources(test_user.id, [])
    assert result == {}


@pytest.mark.asyncio
async def test_member_sources_empty_users(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that _get_member_sources returns empty dict for empty user list."""
    service = GroupsService(test_db_session, test_user)
    result = await service._get_member_sources(uuid4(), [])
    assert result == {}


# ============================================================================
# sync_idp_groups integration tests (real DB)
# ============================================================================


async def _create_user_identity(session: AsyncSession, user: User, provider: IdentityProvider) -> UserIdentity:
    """Create a UserIdentity linking a user to a provider."""
    identity = UserIdentity(
        id=uuid4(),
        user_id=user.id,
        identity_provider_id=provider.id,
        issuer=provider.configuration.issuer_url,
        subject=f"sub-{user.username}",
    )
    session.add(identity)
    await session.commit()
    await session.refresh(identity)
    return identity


async def _create_mapping_entry(
    session: AsyncSession,
    provider_id: UUID,
    idp_value: str,
    group_id: UUID,
) -> IdpGroupMappingEntry:
    """Create an IdP group mapping entry."""
    entry = IdpGroupMappingEntry(
        identity_provider_id=provider_id,
        idp_group_value=idp_value,
        mapped_group_id=group_id,
    )
    session.add(entry)
    await session.commit()
    return entry


async def _get_user_group_ids(session: AsyncSession, user_id: UUID) -> set[UUID]:
    """Get all group IDs a user belongs to."""
    result = await session.exec(select(user_groups.c.group_id).where(user_groups.c.user_id == user_id))
    return set(result.all())


async def _get_user_idp_group_ids(
    session: AsyncSession,
    user_id: UUID,
    provider_id: UUID,
) -> set[UUID]:
    """Get group IDs tracked by a specific provider for a user."""
    result = await session.exec(
        select(user_idp_groups.c.group_id).where(
            user_idp_groups.c.user_id == user_id,
            user_idp_groups.c.identity_provider_id == provider_id,
        )
    )
    return set(result.all())


@pytest.mark.asyncio
async def test_sync_idp_groups_adds_memberships(test_db_session: AsyncSession, test_user: User) -> None:
    """sync_idp_groups should add user to matched groups and track in user_idp_groups."""
    provider = await _create_identity_provider(test_db_session, "sync-add-idp", test_user)
    member = await _create_test_user(test_db_session, "sync-add-user", "syncadd@example.com")
    identity = await _create_user_identity(test_db_session, member, provider)

    group_a = await _create_test_group(test_db_session, "sync-group-a", test_user)
    group_b = await _create_test_group(test_db_session, "sync-group-b", test_user)

    await _create_mapping_entry(test_db_session, provider.id, "idp-admins", group_a.id)
    await _create_mapping_entry(test_db_session, provider.id, "idp-devs", group_b.id)

    config = OIDCConfiguration(
        provider_type="oidc",
        issuer_url=provider.configuration.issuer_url,
        client_id="c",
        client_secret="s",  # noqa: S106
        redirect_uri="http://localhost/cb",
        group_jmespath_expression="groups[*]",
    )

    result = await sync_idp_groups(
        test_db_session,
        member,
        identity,
        {"groups": ["idp-admins", "idp-devs"]},
        config,
    )
    await test_db_session.commit()

    assert result is True
    assert await _get_user_group_ids(test_db_session, member.id) == {group_a.id, group_b.id}
    assert await _get_user_idp_group_ids(test_db_session, member.id, provider.id) == {group_a.id, group_b.id}


@pytest.mark.asyncio
async def test_sync_idp_groups_removes_stale_memberships(test_db_session: AsyncSession, test_user: User) -> None:
    """sync_idp_groups should remove groups no longer in the token."""
    provider = await _create_identity_provider(test_db_session, "sync-rm-idp", test_user)
    member = await _create_test_user(test_db_session, "sync-rm-user", "syncrm@example.com")
    identity = await _create_user_identity(test_db_session, member, provider)

    group_keep = await _create_test_group(test_db_session, "sync-keep", test_user)
    group_remove = await _create_test_group(test_db_session, "sync-remove", test_user)

    await _create_mapping_entry(test_db_session, provider.id, "keep-role", group_keep.id)
    await _create_mapping_entry(test_db_session, provider.id, "remove-role", group_remove.id)

    config = OIDCConfiguration(
        provider_type="oidc",
        issuer_url=provider.configuration.issuer_url,
        client_id="c",
        client_secret="s",  # noqa: S106
        redirect_uri="http://localhost/cb",
        group_jmespath_expression="groups[*]",
    )

    # First sync: both groups
    await sync_idp_groups(
        test_db_session,
        member,
        identity,
        {"groups": ["keep-role", "remove-role"]},
        config,
    )
    await test_db_session.commit()
    assert await _get_user_group_ids(test_db_session, member.id) == {group_keep.id, group_remove.id}

    # Second sync: only keep-role in token
    result = await sync_idp_groups(
        test_db_session,
        member,
        identity,
        {"groups": ["keep-role"]},
        config,
    )
    await test_db_session.commit()

    assert result is True
    assert await _get_user_group_ids(test_db_session, member.id) == {group_keep.id}
    assert await _get_user_idp_group_ids(test_db_session, member.id, provider.id) == {group_keep.id}


@pytest.mark.asyncio
async def test_sync_idp_groups_no_match_returns_false(test_db_session: AsyncSession, test_user: User) -> None:
    """sync_idp_groups should return False when no mapping entries match."""
    provider = await _create_identity_provider(test_db_session, "sync-nomatch-idp", test_user)
    member = await _create_test_user(test_db_session, "sync-nomatch-user", "syncnomatch@example.com")
    identity = await _create_user_identity(test_db_session, member, provider)

    group = await _create_test_group(test_db_session, "sync-nomatch-group", test_user)
    await _create_mapping_entry(test_db_session, provider.id, "admin-role", group.id)

    config = OIDCConfiguration(
        provider_type="oidc",
        issuer_url=provider.configuration.issuer_url,
        client_id="c",
        client_secret="s",  # noqa: S106
        redirect_uri="http://localhost/cb",
        group_jmespath_expression="groups[*]",
    )

    result = await sync_idp_groups(
        test_db_session,
        member,
        identity,
        {"groups": ["unrelated-role"]},
        config,
    )
    await test_db_session.commit()

    assert result is False
    assert await _get_user_group_ids(test_db_session, member.id) == set()


@pytest.mark.asyncio
async def test_sync_idp_groups_wildcard_matching(test_db_session: AsyncSession, test_user: User) -> None:
    """sync_idp_groups should support glob wildcard patterns in mapping entries."""
    provider = await _create_identity_provider(test_db_session, "sync-wild-idp", test_user)
    member = await _create_test_user(test_db_session, "sync-wild-user", "syncwild@example.com")
    identity = await _create_user_identity(test_db_session, member, provider)

    group = await _create_test_group(test_db_session, "sync-wild-group", test_user)
    await _create_mapping_entry(test_db_session, provider.id, "team-*", group.id)

    config = OIDCConfiguration(
        provider_type="oidc",
        issuer_url=provider.configuration.issuer_url,
        client_id="c",
        client_secret="s",  # noqa: S106
        redirect_uri="http://localhost/cb",
        group_jmespath_expression="groups[*]",
    )

    result = await sync_idp_groups(
        test_db_session,
        member,
        identity,
        {"groups": ["team-platform", "other"]},
        config,
    )
    await test_db_session.commit()

    assert result is True
    assert await _get_user_group_ids(test_db_session, member.id) == {group.id}


@pytest.mark.asyncio
async def test_sync_idp_groups_session_scoped_clears_other_provider(
    test_db_session: AsyncSession, test_user: User
) -> None:
    """Logging in with provider B should remove groups from provider A (session-scoped)."""
    provider_a = await _create_identity_provider(test_db_session, "session-idp-a", test_user)
    provider_b = await _create_identity_provider(test_db_session, "session-idp-b", test_user)
    member = await _create_test_user(test_db_session, "session-user", "session@example.com")
    identity_a = await _create_user_identity(test_db_session, member, provider_a)
    identity_b = await _create_user_identity(test_db_session, member, provider_b)

    group_a = await _create_test_group(test_db_session, "group-from-a", test_user)
    group_b = await _create_test_group(test_db_session, "group-from-b", test_user)

    await _create_mapping_entry(test_db_session, provider_a.id, "role-a", group_a.id)
    await _create_mapping_entry(test_db_session, provider_b.id, "role-b", group_b.id)

    config_a = OIDCConfiguration(
        provider_type="oidc",
        issuer_url=provider_a.configuration.issuer_url,
        client_id="c",
        client_secret="s",  # noqa: S106
        redirect_uri="http://localhost/cb",
        group_jmespath_expression="groups[*]",
    )
    config_b = OIDCConfiguration(
        provider_type="oidc",
        issuer_url=provider_b.configuration.issuer_url,
        client_id="c",
        client_secret="s",  # noqa: S106
        redirect_uri="http://localhost/cb",
        group_jmespath_expression="groups[*]",
    )

    # Login with provider A
    await sync_idp_groups(test_db_session, member, identity_a, {"groups": ["role-a"]}, config_a)
    await test_db_session.commit()
    assert await _get_user_group_ids(test_db_session, member.id) == {group_a.id}

    # Login with provider B — provider A's groups should be removed
    result = await sync_idp_groups(test_db_session, member, identity_b, {"groups": ["role-b"]}, config_b)
    await test_db_session.commit()

    assert result is True
    assert await _get_user_group_ids(test_db_session, member.id) == {group_b.id}
    assert await _get_user_idp_group_ids(test_db_session, member.id, provider_a.id) == set()
    assert await _get_user_idp_group_ids(test_db_session, member.id, provider_b.id) == {group_b.id}


@pytest.mark.asyncio
async def test_sync_idp_groups_preserves_manual_groups(test_db_session: AsyncSession, test_user: User) -> None:
    """Manually assigned groups should persist across IdP logins."""
    provider = await _create_identity_provider(test_db_session, "manual-keep-idp", test_user)
    member = await _create_test_user(test_db_session, "manual-keep-user", "manualkeep@example.com")
    identity = await _create_user_identity(test_db_session, member, provider)

    idp_group = await _create_test_group(test_db_session, "idp-assigned", test_user)
    manual_group = await _create_test_group(test_db_session, "manually-assigned", test_user)

    # Manually assign a group (insert directly into user_groups, no user_idp_groups entry)
    await test_db_session.exec(user_groups.insert().values(user_id=member.id, group_id=manual_group.id))
    await test_db_session.commit()

    await _create_mapping_entry(test_db_session, provider.id, "idp-role", idp_group.id)

    config = OIDCConfiguration(
        provider_type="oidc",
        issuer_url=provider.configuration.issuer_url,
        client_id="c",
        client_secret="s",  # noqa: S106
        redirect_uri="http://localhost/cb",
        group_jmespath_expression="groups[*]",
    )

    result = await sync_idp_groups(test_db_session, member, identity, {"groups": ["idp-role"]}, config)
    await test_db_session.commit()

    assert result is True
    assert await _get_user_group_ids(test_db_session, member.id) == {idp_group.id, manual_group.id}


@pytest.mark.asyncio
async def test_sync_idp_groups_session_scoped_all_idp_tracking_cleared(
    test_db_session: AsyncSession, test_user: User
) -> None:
    """After login with provider B, user_idp_groups should have no rows for provider A."""
    provider_a = await _create_identity_provider(test_db_session, "track-clear-a", test_user)
    provider_b = await _create_identity_provider(test_db_session, "track-clear-b", test_user)
    member = await _create_test_user(test_db_session, "track-clear-user", "trackclear@example.com")
    identity_a = await _create_user_identity(test_db_session, member, provider_a)
    identity_b = await _create_user_identity(test_db_session, member, provider_b)

    group_a = await _create_test_group(test_db_session, "track-group-a", test_user)
    group_b = await _create_test_group(test_db_session, "track-group-b", test_user)

    await _create_mapping_entry(test_db_session, provider_a.id, "track-a", group_a.id)
    await _create_mapping_entry(test_db_session, provider_b.id, "track-b", group_b.id)

    config_a = OIDCConfiguration(
        provider_type="oidc",
        issuer_url=provider_a.configuration.issuer_url,
        client_id="c",
        client_secret="s",  # noqa: S106
        redirect_uri="http://localhost/cb",
        group_jmespath_expression="groups[*]",
    )
    config_b = OIDCConfiguration(
        provider_type="oidc",
        issuer_url=provider_b.configuration.issuer_url,
        client_id="c",
        client_secret="s",  # noqa: S106
        redirect_uri="http://localhost/cb",
        group_jmespath_expression="groups[*]",
    )

    # Login with provider A
    await sync_idp_groups(test_db_session, member, identity_a, {"groups": ["track-a"]}, config_a)
    await test_db_session.commit()
    assert await _get_user_idp_group_ids(test_db_session, member.id, provider_a.id) == {group_a.id}

    # Login with provider B
    await sync_idp_groups(test_db_session, member, identity_b, {"groups": ["track-b"]}, config_b)
    await test_db_session.commit()

    # Provider A tracking should be completely cleared
    assert await _get_user_idp_group_ids(test_db_session, member.id, provider_a.id) == set()
    assert await _get_user_idp_group_ids(test_db_session, member.id, provider_b.id) == {group_b.id}


async def _get_all_user_idp_tracking_rows(session: AsyncSession, user_id: UUID) -> set[UUID]:
    """Get all group IDs tracked by any provider for a user."""
    result = await session.exec(select(user_idp_groups.c.group_id).where(user_idp_groups.c.user_id == user_id))
    return set(result.all())


@pytest.mark.asyncio
async def test_sync_idp_groups_overlapping_group_between_providers(
    test_db_session: AsyncSession, test_user: User
) -> None:
    """When providers A and B both map to the same group, login with B should retain that group."""
    provider_a = await _create_identity_provider(test_db_session, "overlap-idp-a", test_user)
    provider_b = await _create_identity_provider(test_db_session, "overlap-idp-b", test_user)
    member = await _create_test_user(test_db_session, "overlap-user", "overlap@example.com")
    identity_a = await _create_user_identity(test_db_session, member, provider_a)
    identity_b = await _create_user_identity(test_db_session, member, provider_b)

    shared_group = await _create_test_group(test_db_session, "shared-group", test_user)
    exclusive_a = await _create_test_group(test_db_session, "only-a-group", test_user)

    await _create_mapping_entry(test_db_session, provider_a.id, "shared-role", shared_group.id)
    await _create_mapping_entry(test_db_session, provider_a.id, "a-only-role", exclusive_a.id)
    await _create_mapping_entry(test_db_session, provider_b.id, "shared-role", shared_group.id)

    config_a = OIDCConfiguration(
        provider_type="oidc",
        issuer_url=provider_a.configuration.issuer_url,
        client_id="c",
        client_secret="s",  # noqa: S106
        redirect_uri="http://localhost/cb",
        group_jmespath_expression="groups[*]",
    )
    config_b = OIDCConfiguration(
        provider_type="oidc",
        issuer_url=provider_b.configuration.issuer_url,
        client_id="c",
        client_secret="s",  # noqa: S106
        redirect_uri="http://localhost/cb",
        group_jmespath_expression="groups[*]",
    )

    # Login with provider A — user gets shared_group + exclusive_a
    await sync_idp_groups(test_db_session, member, identity_a, {"groups": ["shared-role", "a-only-role"]}, config_a)
    await test_db_session.commit()
    assert await _get_user_group_ids(test_db_session, member.id) == {shared_group.id, exclusive_a.id}

    # Login with provider B — shared_group should survive (delete+re-insert), exclusive_a removed
    result = await sync_idp_groups(test_db_session, member, identity_b, {"groups": ["shared-role"]}, config_b)
    await test_db_session.commit()

    assert result is True
    assert await _get_user_group_ids(test_db_session, member.id) == {shared_group.id}
    assert await _get_user_idp_group_ids(test_db_session, member.id, provider_a.id) == set()
    assert await _get_user_idp_group_ids(test_db_session, member.id, provider_b.id) == {shared_group.id}


@pytest.mark.asyncio
async def test_sync_idp_groups_deny_clears_only_authenticating_provider(
    test_db_session: AsyncSession, test_user: User
) -> None:
    """When the token resolves no groups, only the authenticating provider's IdP-managed memberships are removed."""
    provider_a = await _create_identity_provider(test_db_session, "empty-idp-a", test_user)
    provider_b = await _create_identity_provider(test_db_session, "empty-idp-b", test_user)
    member = await _create_test_user(test_db_session, "empty-user", "empty@example.com")
    identity_a = await _create_user_identity(test_db_session, member, provider_a)
    identity_b = await _create_user_identity(test_db_session, member, provider_b)

    group_a = await _create_test_group(test_db_session, "empty-group-a", test_user)
    manual_group = await _create_test_group(test_db_session, "empty-manual", test_user)

    await _create_mapping_entry(test_db_session, provider_a.id, "role-a", group_a.id)

    # Manually assign a group (no user_idp_groups tracking)
    await test_db_session.exec(user_groups.insert().values(user_id=member.id, group_id=manual_group.id))
    await test_db_session.commit()

    config_a = OIDCConfiguration(
        provider_type="oidc",
        issuer_url=provider_a.configuration.issuer_url,
        client_id="c",
        client_secret="s",  # noqa: S106
        redirect_uri="http://localhost/cb",
        group_jmespath_expression="groups[*]",
    )
    config_b = OIDCConfiguration(
        provider_type="oidc",
        issuer_url=provider_b.configuration.issuer_url,
        client_id="c",
        client_secret="s",  # noqa: S106
        redirect_uri="http://localhost/cb",
        group_jmespath_expression="groups[*]",
    )

    # Login with provider A — user gets group_a (+ manual_group persists)
    await sync_idp_groups(test_db_session, member, identity_a, {"groups": ["role-a"]}, config_a)
    await test_db_session.commit()
    assert await _get_user_group_ids(test_db_session, member.id) == {group_a.id, manual_group.id}

    # Provider B has mapping entries but token matches nothing — deny path
    # triggers provider-scoped clear (only provider B's groups removed).
    await _create_mapping_entry(test_db_session, provider_b.id, "nonexistent-role", group_a.id)
    result = await sync_idp_groups(test_db_session, member, identity_b, {"groups": ["no-match"]}, config_b)
    await test_db_session.commit()

    assert result is False
    # Provider-scoped deny: only provider B's groups cleared; provider A's group_a persists
    assert await _get_user_group_ids(test_db_session, member.id) == {group_a.id, manual_group.id}
    assert await _get_user_idp_group_ids(test_db_session, member.id, provider_a.id) == {group_a.id}
    assert await _get_user_idp_group_ids(test_db_session, member.id, provider_b.id) == set()
