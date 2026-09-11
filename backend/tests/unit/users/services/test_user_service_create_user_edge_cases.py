"""Unit tests covering error/edge-case branches in UsersService.create_user (AAP-87156).

These tests target uncovered lines in:
- _flush_user_with_duplicate_check (duplicate username, email, unknown integrity error)
- _get_or_create_default_users_group (race-loss retry, unrecoverable race)
- _is_duplicate_name_error (pattern matching)
- create_user (missing authenticated group, explicit group_names with missing groups)
"""

# mypy: disable-error-code="attr-defined"

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.models.audit_event import EventCategory
from syntara.auth.exceptions import (
    GroupNamesNotFoundError,
    UserEmailConflictError,
    UserUsernameConflictError,
)
from syntara.authz.audit.group_membership import GroupMembershipEvent, GroupMembershipHandler
from syntara.authz.resolver import AUTHENTICATED_GROUP_NAME
from syntara.core.models import User
from syntara.core.models.group import Group
from syntara.users.services.user_service import (
    DEFAULT_LOCAL_USERS_GROUP_NAME,
    UsersService,
)

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent

_FAKE_PW_HASH = "fake-pw-hash-for-tests"


@pytest.fixture
def test_user() -> User:
    """Lightweight mock User for unit tests — no DB required."""
    pw_hash = _FAKE_PW_HASH
    return User(
        id=uuid4(),
        username="fixture-actor",
        email="actor@example.com",
        first_name="Fixture",
        password_hash=pw_hash,
        is_enabled=True,
    )


class _AsyncNoopContextManager:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


# ============================================================================
# _flush_user_with_duplicate_check
# ============================================================================


class TestFlushUserWithDuplicateCheck:
    """Tests for _flush_user_with_duplicate_check error branches."""

    @pytest.mark.asyncio
    @patch("syntara.users.services.user_service.hash_password", return_value="hashed")
    async def test_raises_username_conflict_on_duplicate_username(self, mock_hash: Mock, test_user: User) -> None:
        assert mock_hash.return_value == "hashed"
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.add = Mock()
        mock_session.rollback = AsyncMock()
        mock_session.flush = AsyncMock(
            side_effect=IntegrityError("ix_users_username_unique violated", None, BaseException())
        )

        service = UsersService(session=mock_session, user=test_user)
        with pytest.raises(UserUsernameConflictError):
            await service._flush_user_with_duplicate_check("dupuser")

    @pytest.mark.asyncio
    @patch("syntara.users.services.user_service.hash_password", return_value="hashed")
    async def test_raises_email_conflict_on_duplicate_email(self, mock_hash: Mock, test_user: User) -> None:
        assert mock_hash.return_value == "hashed"
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.add = Mock()
        mock_session.rollback = AsyncMock()
        mock_session.flush = AsyncMock(
            side_effect=IntegrityError("ix_users_email_unique violated", None, BaseException())
        )

        service = UsersService(session=mock_session, user=test_user)
        with pytest.raises(UserEmailConflictError):
            await service._flush_user_with_duplicate_check("anyuser", email="dup@example.com")

    @pytest.mark.asyncio
    @patch("syntara.users.services.user_service.hash_password", return_value="hashed")
    async def test_reraises_unknown_integrity_error(self, mock_hash: Mock, test_user: User) -> None:
        assert mock_hash.return_value == "hashed"
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.add = Mock()
        mock_session.rollback = AsyncMock()
        mock_session.flush = AsyncMock(
            side_effect=IntegrityError("some_other_constraint violated", None, BaseException())
        )

        service = UsersService(session=mock_session, user=test_user)
        with pytest.raises(IntegrityError, match="some_other_constraint"):
            await service._flush_user_with_duplicate_check("anyuser")


# ============================================================================
# _get_or_create_default_users_group
# ============================================================================


class TestGetOrCreateDefaultUsersGroup:
    """Tests for _get_or_create_default_users_group fallback paths."""

    @pytest.mark.asyncio
    @patch("syntara.users.services.user_service.hash_password", return_value="hashed")
    async def test_returns_existing_group_on_race_loss(self, mock_hash: Mock, test_user: User) -> None:
        """When savepoint flush raises duplicate name error, re-query returns existing group."""
        assert mock_hash.return_value == "hashed"
        existing_group = Group(
            id=uuid4(),
            name=DEFAULT_LOCAL_USERS_GROUP_NAME,
            description="Default group for local users.",
            is_builtin=True,
            labels={},
        )

        integrity_error = IntegrityError("ix_groups_name_unique violated", None, BaseException())

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.add = Mock()
        mock_session.begin_nested = Mock(return_value=_AsyncNoopContextManager())
        mock_session.flush = AsyncMock(side_effect=integrity_error)

        requery_result = Mock()
        requery_result.one_or_none.return_value = existing_group
        mock_session.exec = AsyncMock(return_value=requery_result)

        service = UsersService(session=mock_session, user=test_user)
        result = await service._get_or_create_default_users_group()

        assert result.id == existing_group.id
        assert result.name == DEFAULT_LOCAL_USERS_GROUP_NAME

    @pytest.mark.asyncio
    @patch("syntara.users.services.user_service.hash_password", return_value="hashed")
    async def test_raises_runtime_error_when_requery_finds_nothing(self, mock_hash: Mock, test_user: User) -> None:
        """When savepoint race-loss occurs but re-query returns None, raise RuntimeError."""
        assert mock_hash.return_value == "hashed"
        integrity_error = IntegrityError("ix_groups_name_unique violated", None, BaseException())

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.add = Mock()
        mock_session.flush = AsyncMock(side_effect=integrity_error)
        mock_session.begin_nested = Mock(return_value=_AsyncNoopContextManager())

        requery_result = Mock()
        requery_result.one_or_none.return_value = None
        mock_session.exec = AsyncMock(return_value=requery_result)

        service = UsersService(session=mock_session, user=test_user)

        with pytest.raises(RuntimeError, match="could not be reloaded"):
            await service._get_or_create_default_users_group()

    @pytest.mark.asyncio
    @patch("syntara.users.services.user_service.hash_password", return_value="hashed")
    async def test_reraises_non_duplicate_integrity_error(self, mock_hash: Mock, test_user: User) -> None:
        """When savepoint raises non-duplicate IntegrityError, re-raise it."""
        assert mock_hash.return_value == "hashed"
        integrity_error = IntegrityError("fk_constraint_on_something_else violated", None, BaseException())

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.add = Mock()
        mock_session.flush = AsyncMock(side_effect=integrity_error)
        mock_session.begin_nested = Mock(return_value=_AsyncNoopContextManager())

        service = UsersService(session=mock_session, user=test_user)

        with pytest.raises(IntegrityError, match="fk_constraint_on_something_else"):
            await service._get_or_create_default_users_group()

    @pytest.mark.asyncio
    @patch("syntara.users.services.user_service.hash_password", return_value="hashed")
    async def test_creates_and_returns_new_group_on_success(self, mock_hash: Mock, test_user: User) -> None:
        """Happy path: savepoint flush succeeds, newly created group is returned."""
        assert mock_hash.return_value == "hashed"
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.add = Mock()
        mock_session.flush = AsyncMock()
        mock_session.begin_nested = Mock(return_value=_AsyncNoopContextManager())

        service = UsersService(session=mock_session, user=test_user)
        result = await service._get_or_create_default_users_group()

        assert result.name == DEFAULT_LOCAL_USERS_GROUP_NAME
        assert result.is_builtin is True
        assert result.description == "Default group for local users."


# ============================================================================
# _is_duplicate_name_error
# ============================================================================


class TestIsDuplicateNameError:
    """Tests for _is_duplicate_name_error pattern matching."""

    def _service(self, test_user: User) -> UsersService:
        mock_session = AsyncMock(spec=AsyncSession)
        return UsersService(session=mock_session, user=test_user)

    def test_matches_ix_groups_name_unique(self, test_user: User) -> None:
        service = self._service(test_user)
        e = IntegrityError("ix_groups_name_unique violated", None, BaseException())
        assert service._is_duplicate_name_error(e) is True

    def test_matches_full_violation_with_groups_name(self, test_user: User) -> None:
        service = self._service(test_user)
        e = IntegrityError(
            "duplicate key value violates unique constraint on groups.name",
            None,
            BaseException(),
        )
        assert service._is_duplicate_name_error(e) is True

    def test_matches_key_name_pattern(self, test_user: User) -> None:
        service = self._service(test_user)
        e = IntegrityError(
            'duplicate key value violates unique constraint "ix_groups_name" Key (name)=(users) already exists',
            None,
            BaseException(),
        )
        assert service._is_duplicate_name_error(e) is True

    def test_does_not_match_unrelated_constraint(self, test_user: User) -> None:
        service = self._service(test_user)
        e = IntegrityError(
            "duplicate key value violates unique constraint on users.email",
            None,
            BaseException(),
        )
        assert service._is_duplicate_name_error(e) is False

    def test_does_not_match_generic_fk_violation(self, test_user: User) -> None:
        service = self._service(test_user)
        e = IntegrityError("foreign key constraint fk_user_group violated", None, BaseException())
        assert service._is_duplicate_name_error(e) is False


# ============================================================================
# create_user — default group auto-creation path
# ============================================================================


class TestCreateUserAutoCreatesDefaultGroup:
    """Test that create_user calls _get_or_create_default_users_group when users group is missing."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({GroupMembershipEvent: GroupMembershipHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    @patch("syntara.users.services.user_service.hash_password", return_value="hashed")
    async def test_auto_creates_users_group_when_not_found(
        self,
        mock_hash: Mock,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """When group_names=None and users group not in DB, auto-create it."""
        assert mock_hash.return_value == "hashed"
        auth_group = Group(
            id=uuid4(),
            name=AUTHENTICATED_GROUP_NAME,
            description="auth",
            is_builtin=True,
            labels={},
        )

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.add = Mock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.begin_nested = Mock(return_value=_AsyncNoopContextManager())

        initial_group_query_result = Mock()
        initial_group_query_result.all.return_value = [auth_group]

        membership_insert_result = Mock()
        mock_session.exec = AsyncMock(side_effect=[initial_group_query_result, membership_insert_result])

        service = UsersService(session=mock_session, user=test_user)
        plaintext = "fixture-only-value"
        created = await service.create_user(
            username="autocreate",
            first_name="Auto",
            password=plaintext,
        )

        assert mock_do_emit.call_count == 2
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        group_names_in_events = {e.structured_data.group_name for e in events}
        assert group_names_in_events == {AUTHENTICATED_GROUP_NAME, DEFAULT_LOCAL_USERS_GROUP_NAME}
        assert all(e.structured_data.user_id == str(created.id) for e in events)


# ============================================================================
# create_user — missing authenticated group
# ============================================================================


class TestCreateUserMissingAuthenticatedGroup:
    """Test that create_user raises RuntimeError when authenticated group is missing."""

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    @patch("syntara.users.services.user_service.hash_password", return_value="hashed")
    async def test_raises_runtime_error_when_authenticated_group_missing(
        self,
        mock_hash: Mock,
        mock_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """If authenticated group doesn't exist in DB, raise RuntimeError."""
        assert mock_hash.return_value == "hashed"
        users_group = Group(
            id=uuid4(),
            name="users",
            description="users",
            is_builtin=True,
            labels={},
        )

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.add = Mock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.begin_nested = Mock(return_value=_AsyncNoopContextManager())

        groups_result = Mock()
        groups_result.all.return_value = [users_group]
        mock_session.exec = AsyncMock(return_value=groups_result)

        service = UsersService(session=mock_session, user=test_user)

        plaintext = "fixture-only-value"
        with pytest.raises(RuntimeError, match=r"authenticated.*missing"):
            await service.create_user(
                username="noauthgroup",
                first_name="NoAuth",
                password=plaintext,
            )
        assert mock_emit.call_count == 0


# ============================================================================
# create_user — explicit group_names with missing groups
# ============================================================================


class TestCreateUserExplicitGroupNamesNotFound:
    """Test that create_user raises GroupNamesNotFoundError for missing explicit groups."""

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    @patch("syntara.users.services.user_service.hash_password", return_value="hashed")
    async def test_raises_group_names_not_found_error(
        self,
        mock_hash: Mock,
        mock_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """If explicit group_names references groups that don't exist, raise error."""
        assert mock_hash.return_value == "hashed"
        auth_group = Group(
            id=uuid4(),
            name=AUTHENTICATED_GROUP_NAME,
            description="auth",
            is_builtin=True,
            labels={},
        )

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.add = Mock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.begin_nested = Mock(return_value=_AsyncNoopContextManager())

        groups_result = Mock()
        groups_result.all.return_value = [auth_group]
        mock_session.exec = AsyncMock(return_value=groups_result)

        service = UsersService(session=mock_session, user=test_user)

        plaintext = "fixture-only-value"
        with pytest.raises(GroupNamesNotFoundError):
            await service.create_user(
                username="missinggroups",
                first_name="Missing",
                password=plaintext,
                group_names=["developers", "nonexistent"],
            )
        assert mock_emit.call_count == 0


# ============================================================================
# create_user — empty group_names
# ============================================================================


class TestCreateUserWithEmptyGroupNames:
    """Test that create_user with explicit empty list only adds authenticated group."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({GroupMembershipEvent: GroupMembershipHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    @patch("syntara.users.services.user_service.hash_password", return_value="hashed")
    async def test_empty_group_names_only_adds_authenticated(
        self,
        mock_hash: Mock,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Explicit empty list means no explicit groups — only authenticated is added."""
        assert mock_hash.return_value == "hashed"
        auth_group = Group(
            id=uuid4(),
            name=AUTHENTICATED_GROUP_NAME,
            description="auth",
            is_builtin=True,
            labels={},
        )

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.add = Mock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.begin_nested = Mock(return_value=_AsyncNoopContextManager())

        groups_result = Mock()
        groups_result.all.return_value = [auth_group]
        mock_session.exec = AsyncMock(return_value=groups_result)

        service = UsersService(session=mock_session, user=test_user)

        plaintext = "fixture-only-value"
        await service.create_user(
            username="emptygroups",
            first_name="Empty",
            password=plaintext,
            group_names=[],
        )

        assert mock_do_emit.call_count == 1
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        assert events[0].event_action == "group_member_added"
        assert events[0].event_category == EventCategory.SECURITY_EVENT
        assert events[0].structured_data.group_name == AUTHENTICATED_GROUP_NAME


class TestCreateUserBlankFirstName:
    """create_user should persist an empty string when first_name is omitted."""

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    @patch("syntara.users.services.user_service.hash_password", return_value="hashed")
    async def test_none_first_name_stored_as_empty_string(
        self,
        mock_hash: Mock,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        assert mock_hash.return_value == "hashed"
        auth_group = Group(
            id=uuid4(),
            name=AUTHENTICATED_GROUP_NAME,
            description="auth",
            is_builtin=True,
            labels={},
        )
        users_group = Group(
            id=uuid4(),
            name=DEFAULT_LOCAL_USERS_GROUP_NAME,
            description="users",
            is_builtin=True,
            labels={},
        )

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.add = Mock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.begin_nested = Mock(return_value=_AsyncNoopContextManager())

        groups_result = Mock()
        groups_result.all.return_value = [auth_group, users_group]
        mock_session.exec = AsyncMock(return_value=groups_result)

        service = UsersService(session=mock_session, user=test_user)
        plaintext = "fixture-only-value"
        created = await service.create_user(
            username="nofirst",
            first_name=None,
            password=plaintext,
        )

        added_user = mock_session.add.call_args[0][0]
        assert added_user.first_name == ""
        assert created.first_name == ""
        assert mock_do_emit.call_count == 2
