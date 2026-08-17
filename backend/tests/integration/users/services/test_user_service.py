"""Unit tests for UsersService.

Tests cover:
- CRUD operations (create, read, update)
- Duplicate username/email handling
- Admin self-disable restriction
- Error conditions and edge cases
- auth_sources population and auth_source filtering
"""

import warnings
from uuid import uuid4

import pytest
from sqlalchemy import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth.exceptions import (
    AdminDeleteError,
    AdminDisableNoOtherAdminsError,
    AdminModifyError,
    GroupNamesNotFoundError,
    UserEmailConflictError,
    UserNotFoundError,
    UserUsernameConflictError,
)
from syntara.auth.passwords import hash_password, verify_password
from syntara.core.models import User
from syntara.core.models.group import Group, user_groups
from syntara.core.models.user import AuthType
from syntara.core.models.user_identity import UserIdentity
from syntara.core.models.user_schemas import UserRead
from syntara.identity_providers.models.identity_provider import IdentityProvider
from syntara.identity_providers.models.identity_provider_configuration import OIDCConfiguration
from syntara.users.services.user_service import UsersService


async def _get_or_create_admins_group(session: AsyncSession) -> Group:
    """Return the seeded 'admins' group or create one if absent."""
    result = await session.exec(select(Group).where(Group.name == "admins", Group.deleted_at.is_(None)))  # type: ignore[union-attr]
    group = result.first()
    if group is not None:
        return group
    group = Group(id=uuid4(), name="admins", is_builtin=True, labels={})
    session.add(group)
    await session.flush()
    return group


async def _get_or_create_builtin_admin(session: AsyncSession) -> User:
    """Return the seeded builtin admin user or create one if absent."""
    result = await session.exec(select(User).where(User.is_builtin == True, User.deleted_at.is_(None)))  # type: ignore[union-attr]  # noqa: E712
    user = result.first()
    if user is not None:
        return user
    user = User(
        id=uuid4(),
        username="admin",
        first_name="Admin",
        email="admin@example.com",
        password_hash=hash_password("adminpassword"),
        is_builtin=True,
    )
    session.add(user)
    await session.flush()
    return user


TEST_PASSWORD = "SecurePassword123!"  # noqa: S105


@pytest.mark.asyncio
async def test_create_user_success(test_db_session: AsyncSession, test_user: User) -> None:
    """Test successful user creation."""
    service = UsersService(test_db_session, test_user)

    user = await service.create_user(
        username="newuser",
        email="newuser@example.com",
        first_name="New",
        password=TEST_PASSWORD,
        last_name="User",
    )

    assert user.username == "newuser"
    assert user.email == "newuser@example.com"
    assert user.first_name == "New"
    assert user.last_name == "User"
    assert user.is_enabled is True
    assert user.id is not None
    assert user.password_hash is not None
    assert verify_password(TEST_PASSWORD, user.password_hash)


@pytest.mark.asyncio
async def test_create_user_inactive(test_db_session: AsyncSession, test_user: User) -> None:
    """Test user creation with is_enabled=False."""
    service = UsersService(test_db_session, test_user)

    user = await service.create_user(
        username="inactiveuser",
        email="inactive@example.com",
        first_name="Inactive",
        password=TEST_PASSWORD,
        last_name="User",
        is_enabled=False,
    )

    assert user.is_enabled is False


@pytest.mark.asyncio
async def test_create_user_duplicate_username(test_db_session: AsyncSession, test_user: User) -> None:
    """Test UserUsernameConflictError on duplicate username."""
    service = UsersService(test_db_session, test_user)

    await service.create_user(
        username="dupuser",
        email="dup1@example.com",
        first_name="Dup",
        password=TEST_PASSWORD,
        last_name="User 1",
    )

    with pytest.raises(UserUsernameConflictError):
        await service.create_user(
            username="dupuser",
            email="dup2@example.com",
            first_name="Dup",
            password=TEST_PASSWORD,
            last_name="User 2",
        )


@pytest.mark.asyncio
async def test_create_user_duplicate_email_rejected(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that duplicate emails are rejected (email must be unique)."""
    service = UsersService(test_db_session, test_user)

    await service.create_user(
        username="emailuser1",
        email="same@example.com",
        first_name="Email",
        password=TEST_PASSWORD,
        last_name="User 1",
    )

    with pytest.raises(UserEmailConflictError):
        await service.create_user(
            username="emailuser2",
            email="same@example.com",
            first_name="Email",
            password=TEST_PASSWORD,
            last_name="User 2",
        )


@pytest.mark.asyncio
async def test_get_user_by_id_success(test_db_session: AsyncSession, test_user: User) -> None:
    """Test successful user retrieval by ID."""
    service = UsersService(test_db_session, test_user)

    created = await service.create_user(
        username="getuser",
        email="getuser@example.com",
        first_name="Get",
        password=TEST_PASSWORD,
        last_name="User",
    )

    fetched = await service.get_user_by_id(created.id)

    assert fetched.id == created.id
    assert fetched.username == "getuser"
    assert fetched.email == "getuser@example.com"


@pytest.mark.asyncio
async def test_get_user_by_id_not_found(test_db_session: AsyncSession, test_user: User) -> None:
    """Test UserNotFoundError for non-existent user."""
    service = UsersService(test_db_session, test_user)

    with pytest.raises(UserNotFoundError):
        await service.get_user_by_id(uuid4())


@pytest.mark.asyncio
async def test_update_user_first_name(test_db_session: AsyncSession, test_user: User) -> None:
    """Test successful first_name update."""
    service = UsersService(test_db_session, test_user)

    user = await service.create_user(
        username="updatename",
        email="updatename@example.com",
        first_name="Original",
        password=TEST_PASSWORD,
        last_name="Name",
    )

    updated = await service.update_user(user.id, first_name="Updated", last_name="Name")

    assert updated.first_name == "Updated"
    assert updated.last_name == "Name"
    assert updated.email == "updatename@example.com"


@pytest.mark.asyncio
async def test_update_user_clear_last_name(test_db_session: AsyncSession, test_user: User) -> None:
    """Test clearing last_name to None via explicit None."""
    service = UsersService(test_db_session, test_user)

    user = await service.create_user(
        username="clearlast",
        email="clearlast@example.com",
        first_name="Clear",
        password=TEST_PASSWORD,
        last_name="Last",
    )
    assert user.last_name == "Last"

    updated = await service.update_user(user.id, last_name=None)

    assert updated.last_name is None
    assert updated.first_name == "Clear"


@pytest.mark.asyncio
async def test_update_user_preserves_last_name_when_omitted(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that omitting last_name from update preserves it."""
    service = UsersService(test_db_session, test_user)

    user = await service.create_user(
        username="keeplast",
        email="keeplast@example.com",
        first_name="Keep",
        password=TEST_PASSWORD,
        last_name="Existing",
    )

    updated = await service.update_user(user.id, first_name="Updated")

    assert updated.first_name == "Updated"
    assert updated.last_name == "Existing"


@pytest.mark.asyncio
async def test_update_user_email(test_db_session: AsyncSession, test_user: User) -> None:
    """Test successful email update."""
    service = UsersService(test_db_session, test_user)

    user = await service.create_user(
        username="updateemail",
        email="old@example.com",
        first_name="Update",
        last_name="Email User",
        password=TEST_PASSWORD,
    )

    updated = await service.update_user(user.id, email="new@example.com")

    assert updated.email == "new@example.com"


@pytest.mark.asyncio
async def test_update_user_email_normalizes_case(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that email is normalized to lowercase on update."""
    service = UsersService(test_db_session, test_user)

    user = await service.create_user(
        username="emailcase",
        email="original@example.com",
        first_name="Email",
        last_name="Case User",
        password=TEST_PASSWORD,
    )

    updated = await service.update_user(user.id, email="New@Example.COM")

    assert updated.email == "new@example.com"


@pytest.mark.asyncio
async def test_update_user_is_enabled(test_db_session: AsyncSession, test_user: User) -> None:
    """Test disabling a user."""
    service = UsersService(test_db_session, test_user)

    # Seed an admins group with a member so the guard allows disabling other users
    admins_group = await _get_or_create_admins_group(test_db_session)
    await test_db_session.exec(insert(user_groups).values(user_id=test_user.id, group_id=admins_group.id))
    await test_db_session.flush()

    user = await service.create_user(
        username="disableuser",
        email="disable@example.com",
        first_name="Disable",
        last_name="User",
        password=TEST_PASSWORD,
    )

    updated = await service.update_user(user.id, is_enabled=False)

    assert updated.is_enabled is False


@pytest.mark.asyncio
async def test_update_user_duplicate_email_rejected(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that updating to a duplicate email is rejected (email must be unique)."""
    service = UsersService(test_db_session, test_user)

    await service.create_user(
        username="emailconflict1",
        email="taken@example.com",
        first_name="Conflict",
        last_name="User 1",
        password=TEST_PASSWORD,
    )

    user = await service.create_user(
        username="emailconflict2",
        email="original@example.com",
        first_name="Conflict",
        last_name="User 2",
        password=TEST_PASSWORD,
    )

    with pytest.raises(UserEmailConflictError):
        await service.update_user(user.id, email="taken@example.com")


@pytest.mark.asyncio
async def test_update_user_not_found(test_db_session: AsyncSession, test_user: User) -> None:
    """Test UserNotFoundError when updating non-existent user."""
    service = UsersService(test_db_session, test_user)

    with pytest.raises(UserNotFoundError):
        await service.update_user(uuid4(), first_name="New", last_name="Name")


@pytest.mark.asyncio
async def test_update_user_updates_timestamp(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that updated_at changes after update."""
    service = UsersService(test_db_session, test_user)

    user = await service.create_user(
        username="tsuser",
        email="tsuser@example.com",
        first_name="TS",
        last_name="User",
        password=TEST_PASSWORD,
    )
    original_ts = user.updated_at

    updated = await service.update_user(user.id, first_name="TS", last_name="Updated")

    assert updated.updated_at > original_ts


@pytest.mark.asyncio
async def test_admin_self_disable_allowed(test_db_session: AsyncSession) -> None:
    """Test builtin admin can disable itself when other admins exist."""
    admin = await _get_or_create_builtin_admin(test_db_session)

    # Create another admin user so the guard allows disabling
    other_admin = User(
        id=uuid4(),
        username="otheradmin",
        email="other@example.com",
        first_name="Other",
        last_name="Admin",
        password_hash=hash_password("otherpassword"),
    )
    test_db_session.add(other_admin)

    # Seed admins group with both members (clear any pre-seeded memberships first)
    admins_group = await _get_or_create_admins_group(test_db_session)
    await test_db_session.exec(user_groups.delete().where(user_groups.c.group_id == admins_group.id))
    await test_db_session.flush()
    await test_db_session.exec(insert(user_groups).values(user_id=admin.id, group_id=admins_group.id))
    await test_db_session.exec(insert(user_groups).values(user_id=other_admin.id, group_id=admins_group.id))
    await test_db_session.commit()

    # Service running as admin
    service = UsersService(test_db_session, admin)

    updated = await service.update_user(admin.id, is_enabled=False)

    assert updated.is_enabled is False


@pytest.mark.asyncio
async def test_non_admin_cannot_disable_admin(test_db_session: AsyncSession, test_user: User) -> None:
    """Test non-admin user cannot modify the built-in admin."""
    admin = await _get_or_create_builtin_admin(test_db_session)

    # Service running as non-admin test_user
    service = UsersService(test_db_session, test_user)

    with pytest.raises(AdminModifyError):
        await service.update_user(admin.id, is_enabled=False)


@pytest.mark.asyncio
async def test_non_admin_cannot_modify_admin_fields(test_db_session: AsyncSession, test_user: User) -> None:
    """Test non-admin cannot modify the built-in admin's fields."""
    admin = await _get_or_create_builtin_admin(test_db_session)

    service = UsersService(test_db_session, test_user)

    with pytest.raises(AdminModifyError):
        await service.update_user(admin.id, first_name="Updated", last_name="Admin")


@pytest.mark.asyncio
async def test_admin_self_can_update_email(test_db_session: AsyncSession) -> None:
    """Builtin admin may replace the bootstrap email placeholder on itself."""
    admin = await _get_or_create_builtin_admin(test_db_session)
    service = UsersService(test_db_session, admin)

    updated = await service.update_user(admin.id, email="ops-admin@example.com")

    assert updated.email == "ops-admin@example.com"


@pytest.mark.asyncio
async def test_admin_self_cannot_update_name(test_db_session: AsyncSession) -> None:
    """Builtin admin still cannot change protected display-name fields."""
    admin = await _get_or_create_builtin_admin(test_db_session)
    service = UsersService(test_db_session, admin)

    with pytest.raises(AdminModifyError):
        await service.update_user(admin.id, first_name="Renamed")


@pytest.mark.asyncio
async def test_list_users_cursor(test_db_session: AsyncSession, test_user: User) -> None:
    """Test listing users with cursor-based pagination."""
    service = UsersService(test_db_session, test_user)

    for i in range(5):
        await service.create_user(
            username=f"listuser{i}",
            email=f"listuser{i}@example.com",
            first_name="List",
            last_name=f"User {i}",
            password=TEST_PASSWORD,
        )

    result = await service.list_users_cursor(limit=3)

    assert len(result.resources) == 3
    assert result.next is not None


@pytest.mark.asyncio
async def test_create_user_normalizes_case(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that username and email are normalized to lowercase on creation."""
    service = UsersService(test_db_session, test_user)

    user = await service.create_user(
        username="BobSmith",
        email="Bob@Example.COM",
        first_name="Bob",
        last_name="Smith",
        password=TEST_PASSWORD,
    )

    assert user.username == "bobsmith"
    assert user.email == "bob@example.com"


@pytest.mark.asyncio
async def test_is_duplicate_username_error(test_db_session: AsyncSession, test_user: User) -> None:
    """Test _is_duplicate_username_error detects username constraint violations."""
    from sqlalchemy.exc import IntegrityError

    service = UsersService(test_db_session, test_user)

    # Should detect constraint name
    e1 = IntegrityError("ix_users_username_unique violated", None, BaseException())
    assert service._is_duplicate_username_error(e1) is True

    # Should detect Key (username) pattern from DETAIL
    e2 = IntegrityError("DETAIL: Key (username)=(test) already exists.", None, BaseException())
    assert service._is_duplicate_username_error(e2) is True

    # Should not match unrelated errors
    e3 = IntegrityError("foreign key constraint violated on user_id", None, BaseException())
    assert service._is_duplicate_username_error(e3) is False

    # Should not match email constraint
    e4 = IntegrityError("ix_users_email_unique violated", None, BaseException())
    assert service._is_duplicate_username_error(e4) is False


@pytest.mark.asyncio
async def test_update_user_rejects_password_on_federated_user(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that setting a password on a federated user raises PasswordOnFederatedUserError."""
    from syntara.auth.exceptions import PasswordOnFederatedUserError
    from syntara.core.models.user import AuthType

    service = UsersService(test_db_session, test_user)

    federated_user = User(
        id=uuid4(),
        username="feduser",
        email="fed@example.com",
        first_name="Federated",
        last_name="User",
        password_hash=None,
        auth_type=AuthType.FEDERATED,
    )
    test_db_session.add(federated_user)
    await test_db_session.commit()
    await test_db_session.refresh(federated_user)

    with pytest.raises(PasswordOnFederatedUserError):
        await service.update_user(federated_user.id, password="shouldfail123")  # noqa: S106


@pytest.mark.asyncio
async def test_to_read_sets_auth_type_local(test_db_session: AsyncSession, test_user: User) -> None:
    """Test to_read sets auth_type='local' for users with a password hash."""
    service = UsersService(test_db_session, test_user)

    user = await service.create_user(
        username="withpass",
        email="withpass@example.com",
        first_name="With",
        last_name="Password",
        password=TEST_PASSWORD,
    )

    result = await service.to_read(user)

    assert isinstance(result, UserRead)
    assert result.auth_type == "local"
    assert isinstance(result.auth_type, AuthType)
    assert result.auth_sources == ["Local"]
    assert result.username == "withpass"


@pytest.mark.asyncio
async def test_to_read_sets_auth_type_federated(test_db_session: AsyncSession, test_user: User) -> None:
    """Test to_read sets auth_type='federated' for users without a password hash."""
    service = UsersService(test_db_session, test_user)

    user = User(
        id=uuid4(),
        username="oidcuser",
        email="oidc@example.com",
        first_name="OIDC",
        last_name="User",
        password_hash=None,
        auth_type=AuthType.FEDERATED,
    )
    test_db_session.add(user)
    await test_db_session.commit()
    await test_db_session.refresh(user)

    result = await service.to_read(user)

    assert isinstance(result, UserRead)
    assert result.auth_type == "federated"
    assert isinstance(result.auth_type, AuthType)
    assert result.auth_sources == []


@pytest.mark.asyncio
async def test_to_read_serialization_no_enum_warning(test_db_session: AsyncSession, test_user: User) -> None:
    """Ensure serializing UserRead does not emit PydanticSerializationUnexpectedValue for auth_type."""
    service = UsersService(test_db_session, test_user)

    user = await service.create_user(
        username="sercheck",
        email="sercheck@example.com",
        first_name="Serialization",
        last_name="Check",
        password=TEST_PASSWORD,
    )

    result = await service.to_read(user)

    with warnings.catch_warnings():
        warnings.filterwarnings("error", message="Expected `enum`")
        result.model_dump()
        result.model_dump(mode="json")


@pytest.mark.asyncio
async def test_delete_user_success(test_db_session: AsyncSession, test_user: User) -> None:
    """Test successful soft deletion of a user."""
    service = UsersService(test_db_session, test_user)

    user = await service.create_user(
        username="todelete",
        email="todelete@example.com",
        first_name="To",
        last_name="Delete",
        password=TEST_PASSWORD,
    )

    # Need an admins group with the test_user so _ensure_other_admins_exist passes
    admins_group = await _get_or_create_admins_group(test_db_session)
    await test_db_session.exec(insert(user_groups).values(user_id=test_user.id, group_id=admins_group.id))
    await test_db_session.flush()

    await service.delete_user(user.id)

    await test_db_session.refresh(user)
    assert user.deleted_at is not None


@pytest.mark.asyncio
async def test_delete_user_anonymizes_email(test_db_session: AsyncSession, test_user: User) -> None:
    """Test that deleting a user anonymizes their email to prevent reuse attacks.

    Security: Prevents attacker from engineering account deletion and then
    registering with victim's email to intercept password resets.
    """
    service = UsersService(test_db_session, test_user)

    original_email = "victim@example.com"
    user = await service.create_user(
        username="victim",
        email=original_email,
        first_name="Victim",
        last_name="User",
        password=TEST_PASSWORD,
    )

    # Need an admins group with the test_user so _ensure_other_admins_exist passes
    admins_group = await _get_or_create_admins_group(test_db_session)
    await test_db_session.exec(insert(user_groups).values(user_id=test_user.id, group_id=admins_group.id))
    await test_db_session.flush()

    # Verify email exists before deletion
    assert user.email == original_email

    await service.delete_user(user.id)

    await test_db_session.refresh(user)
    assert user.deleted_at is not None
    assert user.email is None  # Email should be anonymized

    # Verify the email can now be reused by a new user (no unique constraint violation)
    new_user = await service.create_user(  # type: ignore[unreachable]
        username="newuser",
        email=original_email,  # Same email as deleted user
        first_name="New",
        password=TEST_PASSWORD,
        last_name="User",
    )
    assert new_user.email == original_email
    assert new_user.id != user.id


@pytest.mark.asyncio
async def test_delete_builtin_user_raises_admin_delete_error(test_db_session: AsyncSession, test_user: User) -> None:
    """Test deleting the built-in admin raises AdminDeleteError."""
    admin = await _get_or_create_builtin_admin(test_db_session)

    service = UsersService(test_db_session, test_user)

    with pytest.raises(AdminDeleteError):
        await service.delete_user(admin.id)


@pytest.mark.asyncio
async def test_list_users_with_id_restriction(test_db_session: AsyncSession, test_user: User) -> None:
    """Test listing users with id_restriction returns only matching users."""
    service = UsersService(test_db_session, test_user)

    user1 = await service.create_user(
        username="restricted1",
        email="r1@example.com",
        first_name="R1",
        password=TEST_PASSWORD,
    )
    await service.create_user(
        username="restricted2",
        email="r2@example.com",
        first_name="R2",
        password=TEST_PASSWORD,
    )

    result = await service.list_users_cursor(id_restriction=[user1.id])
    assert len(result.resources) == 1
    assert result.resources[0].id == user1.id


@pytest.mark.asyncio
async def test_list_users_with_empty_id_restriction(test_db_session: AsyncSession, test_user: User) -> None:
    """Test listing users with empty id_restriction returns no users."""
    service = UsersService(test_db_session, test_user)

    await service.create_user(
        username="noaccess",
        email="no@example.com",
        first_name="No",
        password=TEST_PASSWORD,
    )

    result = await service.list_users_cursor(id_restriction=[])
    assert len(result.resources) == 0


@pytest.mark.asyncio
async def test_list_users_with_none_id_restriction(test_db_session: AsyncSession, test_user: User) -> None:
    """Test listing users with id_restriction=None returns all users."""
    service = UsersService(test_db_session, test_user)

    for i in range(3):
        await service.create_user(
            username=f"allaccess{i}",
            email=f"all{i}@example.com",
            first_name=f"All {i}",
            password=TEST_PASSWORD,
        )

    result = await service.list_users_cursor(id_restriction=None)
    assert len(result.resources) >= 3


@pytest.mark.asyncio
async def test_delete_last_admin_raises_error(test_db_session: AsyncSession) -> None:
    """Test deleting the last admin raises AdminDisableNoOtherAdminsError."""
    sole_admin = User(
        id=uuid4(),
        username="soleadmin",
        email="sole@example.com",
        first_name="Sole",
        last_name="Admin",
        password_hash=hash_password("adminpassword"),
    )
    test_db_session.add(sole_admin)

    admins_group = await _get_or_create_admins_group(test_db_session)
    await test_db_session.exec(user_groups.delete().where(user_groups.c.group_id == admins_group.id))
    await test_db_session.exec(insert(user_groups).values(user_id=sole_admin.id, group_id=admins_group.id))
    await test_db_session.commit()

    service = UsersService(test_db_session, sole_admin)

    with pytest.raises(AdminDisableNoOtherAdminsError):
        await service.delete_user(sole_admin.id)


# ============================================================================
# Group assignment on user creation
# ============================================================================


async def _create_group(session: AsyncSession, name: str) -> Group:
    group = Group(id=uuid4(), name=name, is_builtin=False, labels={})
    session.add(group)
    await session.flush()
    return group


async def _user_group_names(session: AsyncSession, user: User) -> set[str]:
    rows = await session.exec(
        select(Group.name).join(user_groups, user_groups.c.group_id == Group.id).where(user_groups.c.user_id == user.id)
    )
    return set(rows.all())


@pytest.mark.asyncio
async def test_create_user_no_groups_by_default(test_db_session: AsyncSession, test_user: User) -> None:
    """When group_names is omitted, only the authenticated group is assigned."""
    service = UsersService(test_db_session, test_user)
    user = await service.create_user(
        username="defaultuser",
        first_name="Default",
        last_name="User",
        password=TEST_PASSWORD,
    )

    names = await _user_group_names(test_db_session, user)
    assert names == {"authenticated"}


@pytest.mark.asyncio
async def test_create_user_explicit_groups(test_db_session: AsyncSession, test_user: User) -> None:
    """When group_names has specific values, those groups are used plus the authenticated group."""
    g1 = await _create_group(test_db_session, "team-alpha")
    g2 = await _create_group(test_db_session, "team-beta")
    await test_db_session.commit()

    service = UsersService(test_db_session, test_user)
    user = await service.create_user(
        username="teamuser",
        first_name="Team",
        last_name="User",
        password=TEST_PASSWORD,
        group_names=["team-alpha", "team-beta"],
    )

    names = await _user_group_names(test_db_session, user)
    assert names == {g1.name, g2.name, "authenticated"}


@pytest.mark.asyncio
async def test_create_user_nonexistent_group_raises(test_db_session: AsyncSession, test_user: User) -> None:
    """When a requested group name doesn't exist, raise GroupNamesNotFoundError."""
    service = UsersService(test_db_session, test_user)

    with pytest.raises(GroupNamesNotFoundError, match="no-such-group"):
        await service.create_user(
            username="baduser",
            first_name="Bad",
            last_name="User",
            password=TEST_PASSWORD,
            group_names=["no-such-group"],
        )


# ============================================================================
# auth_sources population and auth_source filtering
# ============================================================================


def _make_oidc_config() -> OIDCConfiguration:
    return OIDCConfiguration(
        issuer_url="https://idp.example.com",
        client_id="test-client",
        redirect_uri="http://localhost/callback",
    )


async def _create_idp(session: AsyncSession, name: str, user: User) -> IdentityProvider:
    """Create and persist an identity provider."""
    idp = IdentityProvider(
        id=uuid4(),
        name=name,
        configuration=_make_oidc_config(),
        enabled=True,
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(idp)
    await session.flush()
    return idp


async def _create_federated_user(
    session: AsyncSession,
    username: str,
    idps: list[IdentityProvider],
) -> User:
    """Create a federated user linked to the given identity providers."""
    user = User(
        id=uuid4(),
        username=username,
        email=f"{username}@example.com",
        first_name=username.title(),
        password_hash=None,
        auth_type=AuthType.FEDERATED,
    )
    session.add(user)
    await session.flush()
    for idp in idps:
        identity = UserIdentity(
            id=uuid4(),
            user_id=user.id,
            identity_provider_id=idp.id,
            issuer=idp.configuration.issuer_url,
            subject=f"sub-{user.id.hex[:8]}-{idp.id.hex[:8]}",
        )
        session.add(identity)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_to_read_federated_user_with_provider(test_db_session: AsyncSession, test_user: User) -> None:
    """Test to_read populates auth_sources with provider name for federated users."""
    service = UsersService(test_db_session, test_user)

    idp = await _create_idp(test_db_session, "AAP", test_user)
    user = await _create_federated_user(test_db_session, "fedwithidp", [idp])
    await test_db_session.commit()
    await test_db_session.refresh(user)

    result = await service.to_read(user)

    assert result.auth_sources == ["AAP"]


@pytest.mark.asyncio
async def test_to_read_federated_user_with_multiple_providers(test_db_session: AsyncSession, test_user: User) -> None:
    """Test to_read returns sorted provider names for users linked to multiple IdPs."""
    service = UsersService(test_db_session, test_user)

    idp_azure = await _create_idp(test_db_session, "Azure AD", test_user)
    idp_aap = await _create_idp(test_db_session, "AAP", test_user)
    user = await _create_federated_user(test_db_session, "multiidp", [idp_azure, idp_aap])
    await test_db_session.commit()
    await test_db_session.refresh(user)

    result = await service.to_read(user)

    assert result.auth_sources == ["AAP", "Azure AD"]


@pytest.mark.asyncio
async def test_list_users_populates_auth_sources(test_db_session: AsyncSession, test_user: User) -> None:
    """Test list_users_cursor batch-populates auth_sources for all users."""
    service = UsersService(test_db_session, test_user)

    local_user = await service.create_user(
        username="locallist",
        first_name="Local",
        last_name="List",
        password=TEST_PASSWORD,
    )

    idp = await _create_idp(test_db_session, "AAP", test_user)
    fed_user = await _create_federated_user(test_db_session, "fedlist", [idp])
    await test_db_session.commit()

    result = await service.list_users_cursor(limit=100)
    by_id = {r.id: r for r in result.resources}

    assert by_id[local_user.id].auth_sources == ["Local"]
    assert by_id[fed_user.id].auth_sources == ["AAP"]


@pytest.mark.asyncio
async def test_list_users_filter_auth_source_local(test_db_session: AsyncSession, test_user: User) -> None:
    """Test auth_source=Local filter returns only local users."""
    service = UsersService(test_db_session, test_user)

    local_user = await service.create_user(
        username="localfilter",
        first_name="Local",
        last_name="Filter",
        password=TEST_PASSWORD,
    )

    idp = await _create_idp(test_db_session, "AAP", test_user)
    await _create_federated_user(test_db_session, "fedfilter", [idp])
    await test_db_session.commit()

    result = await service.list_users_cursor(
        query_params_items=[("auth_source", "Local")],
    )

    usernames = {r.username for r in result.resources}
    assert local_user.username in usernames
    assert "fedfilter" not in usernames
    for r in result.resources:
        assert r.auth_type == AuthType.LOCAL


@pytest.mark.asyncio
async def test_list_users_filter_auth_source_provider(test_db_session: AsyncSession, test_user: User) -> None:
    """Test auth_source=<provider> filter returns only users linked to that provider."""
    service = UsersService(test_db_session, test_user)

    await service.create_user(
        username="localexcluded",
        first_name="Local",
        last_name="Excluded",
        password=TEST_PASSWORD,
    )

    idp_aap = await _create_idp(test_db_session, "AAP", test_user)
    idp_azure = await _create_idp(test_db_session, "Azure AD", test_user)
    aap_user = await _create_federated_user(test_db_session, "aaponly", [idp_aap])
    await _create_federated_user(test_db_session, "azureonly", [idp_azure])
    await test_db_session.commit()

    result = await service.list_users_cursor(
        query_params_items=[("auth_source", "AAP")],
    )

    assert len(result.resources) == 1
    assert result.resources[0].id == aap_user.id
    assert result.resources[0].auth_sources == ["AAP"]


@pytest.mark.asyncio
async def test_list_users_filter_auth_source_nonexistent(test_db_session: AsyncSession, test_user: User) -> None:
    """Test filtering by a non-existent provider returns no results."""
    service = UsersService(test_db_session, test_user)

    await service.create_user(
        username="nofilter",
        first_name="No",
        last_name="Filter",
        password=TEST_PASSWORD,
    )

    result = await service.list_users_cursor(
        query_params_items=[("auth_source", "NonExistent")],
    )

    assert len(result.resources) == 0


@pytest.mark.asyncio
async def test_list_users_filter_auth_source_with_id_restriction(
    test_db_session: AsyncSession, test_user: User
) -> None:
    """Test auth_source filter intersects correctly with id_restriction."""
    service = UsersService(test_db_session, test_user)

    idp = await _create_idp(test_db_session, "AAP", test_user)
    user_a = await _create_federated_user(test_db_session, "visible", [idp])
    await _create_federated_user(test_db_session, "hidden", [idp])
    await test_db_session.commit()

    result = await service.list_users_cursor(
        query_params_items=[("auth_source", "AAP")],
        id_restriction=[user_a.id],
    )

    assert len(result.resources) == 1
    assert result.resources[0].id == user_a.id


@pytest.mark.asyncio
async def test_update_user_strips_control_chars_from_names(test_db_session: AsyncSession, test_user: User) -> None:
    """Control characters in first/last name are stripped on update."""
    service = UsersService(test_db_session, test_user)

    user = await service.create_user(
        username="ctrlchar",
        email="ctrlchar@example.com",
        first_name="Clean",
        password=TEST_PASSWORD,
        last_name="Name",
    )

    updated = await service.update_user(
        user.id,
        first_name="Al\x00ice",
        last_name="Smi\x0dth",
    )

    assert updated.first_name == "Alice"
    assert updated.last_name == "Smith"


@pytest.mark.asyncio
async def test_update_user_strips_control_chars_from_username(test_db_session: AsyncSession, test_user: User) -> None:
    """Control characters in username are stripped on update."""
    service = UsersService(test_db_session, test_user)

    user = await service.create_user(
        username="ctrluser",
        email="ctrluser@example.com",
        first_name="Ctrl",
        password=TEST_PASSWORD,
    )

    updated = await service.update_user(user.id, username="new\x00user")

    assert updated.username == "newuser"
