# ruff: noqa: S106
"""Unit tests for UserIdentityService."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from syntara.auth.exceptions import (
    IdentityOnBuiltinUserError,
    LastSignInMethodError,
    UserIdentityNotFoundError,
    UserNotFoundError,
)
from syntara.core.models.user import AuthType
from syntara.users.services.user_identity_service import UserIdentityService

_PATCH_SESSION_STORE = "syntara.users.services.user_identity_service.create_session_store"


def _make_identity(*, user_id: UUID | None = None, identity_id: UUID | None = None) -> MagicMock:
    """Build a mock UserIdentity."""
    identity = MagicMock()
    identity.id = identity_id or uuid4()
    identity.user_id = user_id or uuid4()
    identity.identity_provider_id = uuid4()
    identity.issuer = "https://idp.example.com"
    identity.subject = "sub-123"
    return identity


def _make_user(
    *,
    user_id: UUID | None = None,
    password_hash: str | None = None,
    auth_type: AuthType = AuthType.FEDERATED,
    is_builtin: bool = False,
) -> MagicMock:
    """Build a mock User."""
    user = MagicMock()
    user.id = user_id or uuid4()
    user.deleted_at = None
    user.password_hash = password_hash
    user.auth_type = auth_type
    user.is_builtin = is_builtin
    return user


class TestListForUser:
    """Tests for UserIdentityService.list_for_user."""

    @pytest.mark.asyncio
    async def test_returns_identities_with_provider_names(self) -> None:
        """Should return list of UserIdentityRead with provider_name populated."""
        user_id = uuid4()
        identity = _make_identity(user_id=user_id)
        identity.created_at = MagicMock()
        identity.updated_at = MagicMock()
        identity.last_used_at = None

        session = AsyncMock()
        # First exec: user exists check
        user_result = MagicMock()
        user_result.one_or_none.return_value = _make_user(user_id=user_id)
        # Second exec: identity join query
        identity_result = MagicMock()
        identity_result.all.return_value = [(identity, "Azure")]
        session.exec.side_effect = [user_result, identity_result]

        service = UserIdentityService(session)
        result = await service.list_for_user(user_id)

        assert len(result.resources) == 1
        assert result.resources[0].id == identity.id
        assert result.resources[0].provider_name == "Azure"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_identities(self) -> None:
        """Should return empty list when user has no federated identities."""
        user_id = uuid4()
        session = AsyncMock()
        user_result = MagicMock()
        user_result.one_or_none.return_value = _make_user(user_id=user_id)
        identity_result = MagicMock()
        identity_result.all.return_value = []
        session.exec.side_effect = [user_result, identity_result]

        service = UserIdentityService(session)
        result = await service.list_for_user(user_id)

        assert result.resources == []

    @pytest.mark.asyncio
    async def test_raises_when_user_not_found(self) -> None:
        """Should raise UserNotFoundError when user doesn't exist."""
        session = AsyncMock()
        user_result = MagicMock()
        user_result.one_or_none.return_value = None
        session.exec.return_value = user_result

        service = UserIdentityService(session)
        with pytest.raises(UserNotFoundError):
            await service.list_for_user(uuid4())


@pytest.mark.usefixtures("mock_session_store")
class TestDeleteIdentity:
    """Tests for UserIdentityService.delete_identity."""

    @pytest.mark.asyncio
    async def test_deletes_identity_successfully(self) -> None:
        """Should delete identity when it exists and other identities remain."""
        identity = _make_identity()
        other_identity = _make_identity(user_id=identity.user_id)
        session = AsyncMock()
        identity_result = MagicMock()
        identity_result.one_or_none.return_value = identity
        remaining_result = MagicMock()
        remaining_result.all.return_value = [identity, other_identity]
        session.exec.side_effect = [identity_result, remaining_result]

        mock_store = AsyncMock()
        mock_store.revoke_all_for_user.return_value = 0

        service = UserIdentityService(session)
        with patch(_PATCH_SESSION_STORE, return_value=mock_store):
            await service.delete_identity(identity.id)

        session.delete.assert_called_once_with(identity)
        session.flush.assert_called()
        mock_store.revoke_all_for_user.assert_called_once_with(identity.user_id)
        mock_store.increment_token_version.assert_called_once_with(identity.user_id)

    @pytest.mark.asyncio
    async def test_raises_when_identity_not_found(self) -> None:
        """Should raise UserIdentityNotFoundError when identity doesn't exist."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        session.exec.return_value = mock_result

        service = UserIdentityService(session)
        with pytest.raises(UserIdentityNotFoundError):
            await service.delete_identity(uuid4())

    @pytest.mark.asyncio
    async def test_deletes_when_expected_user_id_matches(self) -> None:
        """Should delete identity when expected_user_id matches the identity's user_id."""
        user_id = uuid4()
        identity = _make_identity(user_id=user_id)
        other_identity = _make_identity(user_id=user_id)
        session = AsyncMock()
        identity_result = MagicMock()
        identity_result.one_or_none.return_value = identity
        remaining_result = MagicMock()
        remaining_result.all.return_value = [identity, other_identity]
        session.exec.side_effect = [identity_result, remaining_result]

        service = UserIdentityService(session)
        with patch(_PATCH_SESSION_STORE, return_value=AsyncMock()):
            await service.delete_identity(identity.id, expected_user_id=user_id)

        session.delete.assert_called_once_with(identity)

    @pytest.mark.asyncio
    async def test_raises_when_expected_user_id_does_not_match(self) -> None:
        """Should raise UserIdentityNotFoundError when identity belongs to a different user."""
        identity = _make_identity(user_id=uuid4())
        different_user_id = uuid4()

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = identity
        session.exec.return_value = mock_result

        service = UserIdentityService(session)
        with pytest.raises(UserIdentityNotFoundError):
            await service.delete_identity(identity.id, expected_user_id=different_user_id)

        session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_last_sign_in_method_when_only_identity(self) -> None:
        """Should raise LastSignInMethodError when deleting the only identity."""
        user_id = uuid4()
        identity = _make_identity(user_id=user_id)

        session = AsyncMock()
        identity_result = MagicMock()
        identity_result.one_or_none.return_value = identity
        remaining_result = MagicMock()
        remaining_result.all.return_value = [identity]
        session.exec.side_effect = [identity_result, remaining_result]

        service = UserIdentityService(session)
        with pytest.raises(LastSignInMethodError):
            await service.delete_identity(identity.id)

        session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_delete_when_multiple_identities_remain(self) -> None:
        """Should allow deleting an identity when other identities remain."""
        user_id = uuid4()
        identity = _make_identity(user_id=user_id)
        other_identity = _make_identity(user_id=user_id)

        session = AsyncMock()
        identity_result = MagicMock()
        identity_result.one_or_none.return_value = identity
        remaining_result = MagicMock()
        remaining_result.all.return_value = [identity, other_identity]
        session.exec.side_effect = [identity_result, remaining_result]

        service = UserIdentityService(session)
        with patch(_PATCH_SESSION_STORE, return_value=AsyncMock()):
            await service.delete_identity(identity.id)

        session.delete.assert_called_once_with(identity)

    @pytest.mark.asyncio
    async def test_force_skips_last_sign_in_check(self) -> None:
        """Should skip last-sign-in-method check when force=True."""
        user_id = uuid4()
        identity = _make_identity(user_id=user_id)

        session = AsyncMock()
        identity_result = MagicMock()
        identity_result.one_or_none.return_value = identity
        session.exec.return_value = identity_result

        service = UserIdentityService(session)
        with patch(_PATCH_SESSION_STORE, return_value=AsyncMock()):
            await service.delete_identity(identity.id, force=True)

        session.delete.assert_called_once_with(identity)

    @pytest.mark.asyncio
    async def test_skips_user_id_check_when_not_provided(self) -> None:
        """Should not check user_id when expected_user_id is None (default)."""
        identity = _make_identity()
        other_identity = _make_identity(user_id=identity.user_id)
        session = AsyncMock()
        identity_result = MagicMock()
        identity_result.one_or_none.return_value = identity
        remaining_result = MagicMock()
        remaining_result.all.return_value = [identity, other_identity]
        session.exec.side_effect = [identity_result, remaining_result]

        service = UserIdentityService(session)
        with patch(_PATCH_SESSION_STORE, return_value=AsyncMock()):
            await service.delete_identity(identity.id)

        session.delete.assert_called_once_with(identity)

    @pytest.mark.asyncio
    async def test_flushes_transaction(self) -> None:
        """Should flush (but not commit) the transaction after deleting."""
        identity = _make_identity()
        other_identity = _make_identity(user_id=identity.user_id)
        session = AsyncMock()
        identity_result = MagicMock()
        identity_result.one_or_none.return_value = identity
        remaining_result = MagicMock()
        remaining_result.all.return_value = [identity, other_identity]
        session.exec.side_effect = [identity_result, remaining_result]

        service = UserIdentityService(session)
        with patch(_PATCH_SESSION_STORE, return_value=AsyncMock()):
            await service.delete_identity(identity.id)

        session.flush.assert_called()
        session.commit.assert_not_called()


class TestFindByIssuerAndSubject:
    """Tests for UserIdentityService.find_by_issuer_and_subject."""

    @pytest.mark.asyncio
    async def test_returns_identity_when_found(self) -> None:
        """Should return identity when (issuer, subject) pair exists."""
        identity = _make_identity()
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = identity
        session.exec.return_value = mock_result

        service = UserIdentityService(session)
        result = await service.find_by_issuer_and_subject("https://idp.example.com", "sub-123")

        assert result == identity

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        """Should return None when no identity matches."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        session.exec.return_value = mock_result

        service = UserIdentityService(session)
        result = await service.find_by_issuer_and_subject("https://idp.example.com", "nonexistent")

        assert result is None


class TestCreateIdentity:
    """Tests for UserIdentityService.create_identity."""

    @pytest.mark.asyncio
    async def test_creates_and_returns_identity(self) -> None:
        """Should create a new identity and flush to DB."""
        user_id = uuid4()
        provider_id = uuid4()
        user = _make_user(user_id=user_id, auth_type=AuthType.FEDERATED)

        session = AsyncMock()
        user_result = MagicMock()
        user_result.one_or_none.return_value = user
        session.exec.side_effect = [user_result]

        service = UserIdentityService(session)
        result = await service.create_identity(
            user_id=user_id,
            identity_provider_id=provider_id,
            issuer="https://idp.example.com",
            subject="new-sub",
        )

        assert result.user_id == user_id
        assert result.identity_provider_id == provider_id
        assert result.issuer == "https://idp.example.com"
        assert result.subject == "new-sub"
        session.add.assert_called_once()
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_identity_on_builtin_user(self) -> None:
        """Should raise IdentityOnBuiltinUserError when user is builtin."""
        user_id = uuid4()
        user = _make_user(user_id=user_id, auth_type=AuthType.LOCAL, is_builtin=True)

        session = AsyncMock()
        user_result = MagicMock()
        user_result.one_or_none.return_value = user
        session.exec.side_effect = [user_result]

        service = UserIdentityService(session)
        with pytest.raises(IdentityOnBuiltinUserError):
            await service.create_identity(
                user_id=user_id,
                identity_provider_id=uuid4(),
                issuer="https://idp.example.com",
                subject="sub-123",
            )

        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_converts_local_user_to_federated_on_create(self) -> None:
        """Should convert a non-builtin local user to federated when creating an identity."""
        user_id = uuid4()
        provider_id = uuid4()
        user = _make_user(
            user_id=user_id,
            auth_type=AuthType.LOCAL,
            password_hash="$argon2id$hashed",
            is_builtin=False,
        )

        session = AsyncMock()
        user_result = MagicMock()
        user_result.one_or_none.return_value = user
        session.exec.side_effect = [user_result]

        mock_store = AsyncMock()
        mock_store.revoke_all_for_user.return_value = 2

        service = UserIdentityService(session)
        with patch(_PATCH_SESSION_STORE, return_value=mock_store):
            result = await service.create_identity(
                user_id=user_id,
                identity_provider_id=provider_id,
                issuer="https://idp.example.com",
                subject="new-sub",
            )

        assert result.user_id == user_id
        assert user.auth_type == AuthType.FEDERATED
        assert user.password_hash is None
        mock_store.revoke_all_for_user.assert_called_once_with(user_id)
        mock_store.increment_token_version.assert_called_once_with(user_id)


@pytest.mark.usefixtures("mock_session_store")
class TestAttachIdentity:
    """Tests for UserIdentityService.attach_identity."""

    @pytest.mark.asyncio
    async def test_moves_identity_to_target_user(self) -> None:
        """Should update identity's user_id to the target user and return UserIdentityRead."""
        source_user_id = uuid4()
        target_user_id = uuid4()
        identity = _make_identity(user_id=source_user_id)
        target_user = _make_user(user_id=target_user_id, auth_type=AuthType.FEDERATED)

        session = AsyncMock()
        identity_join_result = MagicMock()
        identity_join_result.one_or_none.return_value = (identity, "Azure")
        target_result = MagicMock()
        target_result.one_or_none.return_value = target_user
        session.exec.side_effect = [identity_join_result, target_result]

        mock_store = AsyncMock()
        mock_store.revoke_all_for_user.return_value = 0

        service = UserIdentityService(session)
        with patch(_PATCH_SESSION_STORE, return_value=mock_store):
            result = await service.attach_identity(identity.id, target_user_id)

        assert result.user_id == target_user_id
        assert result.provider_name == "Azure"
        session.flush.assert_called_once()
        session.commit.assert_not_called()
        # Sessions revoked for both source and target users
        assert mock_store.revoke_all_for_user.call_count == 2
        mock_store.revoke_all_for_user.assert_any_call(source_user_id)
        mock_store.revoke_all_for_user.assert_any_call(target_user_id)
        # Token versions incremented for both users
        assert mock_store.increment_token_version.call_count == 2
        mock_store.increment_token_version.assert_any_call(source_user_id)
        mock_store.increment_token_version.assert_any_call(target_user_id)

    @pytest.mark.asyncio
    async def test_rejects_attach_to_builtin_user(self) -> None:
        """Should raise IdentityOnBuiltinUserError when target user is builtin."""
        target_user_id = uuid4()
        identity = _make_identity()
        target_user = _make_user(user_id=target_user_id, auth_type=AuthType.LOCAL, is_builtin=True)

        session = AsyncMock()
        identity_join_result = MagicMock()
        identity_join_result.one_or_none.return_value = (identity, "Azure")
        target_result = MagicMock()
        target_result.one_or_none.return_value = target_user
        session.exec.side_effect = [identity_join_result, target_result]

        service = UserIdentityService(session)
        with pytest.raises(IdentityOnBuiltinUserError):
            await service.attach_identity(identity.id, target_user_id)

    @pytest.mark.asyncio
    async def test_converts_local_user_to_federated_on_attach(self) -> None:
        """Should convert a non-builtin local target user to federated when attaching an identity."""
        source_user_id = uuid4()
        target_user_id = uuid4()
        identity = _make_identity(user_id=source_user_id)
        target_user = _make_user(
            user_id=target_user_id,
            auth_type=AuthType.LOCAL,
            password_hash="$argon2id$hashed",
            is_builtin=False,
        )

        session = AsyncMock()
        identity_join_result = MagicMock()
        identity_join_result.one_or_none.return_value = (identity, "Azure")
        target_result = MagicMock()
        target_result.one_or_none.return_value = target_user
        session.exec.side_effect = [identity_join_result, target_result]

        mock_store = AsyncMock()
        mock_store.revoke_all_for_user.return_value = 1

        service = UserIdentityService(session)
        with patch(_PATCH_SESSION_STORE, return_value=mock_store):
            result = await service.attach_identity(identity.id, target_user_id)

        assert result.user_id == target_user_id
        assert target_user.auth_type == AuthType.FEDERATED
        assert target_user.password_hash is None
        # revoke_all_for_user: source user + _convert_to_federated (target)
        assert mock_store.revoke_all_for_user.call_count == 2
        # Token versions: source (attach_identity) + target (_convert_to_federated)
        assert mock_store.increment_token_version.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_when_identity_not_found(self) -> None:
        """Should raise UserIdentityNotFoundError when identity doesn't exist."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        session.exec.return_value = mock_result

        service = UserIdentityService(session)
        with pytest.raises(UserIdentityNotFoundError):
            await service.attach_identity(uuid4(), uuid4())

    @pytest.mark.asyncio
    async def test_raises_when_target_user_not_found(self) -> None:
        """Should raise UserNotFoundError when target user doesn't exist."""
        identity = _make_identity()
        session = AsyncMock()

        identity_join_result = MagicMock()
        identity_join_result.one_or_none.return_value = (identity, "Okta")
        target_result = MagicMock()
        target_result.one_or_none.return_value = None
        session.exec.side_effect = [identity_join_result, target_result]

        service = UserIdentityService(session)
        with pytest.raises(UserNotFoundError):
            await service.attach_identity(identity.id, uuid4())

    @pytest.mark.asyncio
    async def test_preserves_source_user_after_attach(self) -> None:
        """Should NOT soft-delete the source user even if they have no remaining identities."""
        source_user_id = uuid4()
        target_user_id = uuid4()
        identity = _make_identity(user_id=source_user_id)
        target_user = _make_user(user_id=target_user_id, auth_type=AuthType.FEDERATED)

        session = AsyncMock()
        identity_join_result = MagicMock()
        identity_join_result.one_or_none.return_value = (identity, "Azure")
        target_result = MagicMock()
        target_result.one_or_none.return_value = target_user
        session.exec.side_effect = [identity_join_result, target_result]

        service = UserIdentityService(session)
        with patch(_PATCH_SESSION_STORE, return_value=AsyncMock()):
            await service.attach_identity(identity.id, target_user_id)

        # Source user should not be soft-deleted — preserved for audit
        session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_revokes_target_user_sessions(self) -> None:
        """Should revoke target user sessions so they re-authenticate with updated identity."""
        source_user_id = uuid4()
        target_user_id = uuid4()
        identity = _make_identity(user_id=source_user_id)
        target_user = _make_user(user_id=target_user_id, auth_type=AuthType.FEDERATED)

        session = AsyncMock()
        identity_join_result = MagicMock()
        identity_join_result.one_or_none.return_value = (identity, "Azure")
        target_result = MagicMock()
        target_result.one_or_none.return_value = target_user
        session.exec.side_effect = [identity_join_result, target_result]

        mock_store = AsyncMock()
        mock_store.revoke_all_for_user.return_value = 3

        service = UserIdentityService(session)
        with patch(_PATCH_SESSION_STORE, return_value=mock_store):
            await service.attach_identity(identity.id, target_user_id)

        mock_store.revoke_all_for_user.assert_any_call(target_user_id)

    @pytest.mark.asyncio
    async def test_increments_token_version_for_both_users(self) -> None:
        """Should increment token_version for both source and target users."""
        source_user_id = uuid4()
        target_user_id = uuid4()
        identity = _make_identity(user_id=source_user_id)
        target_user = _make_user(user_id=target_user_id, auth_type=AuthType.FEDERATED)

        session = AsyncMock()
        identity_join_result = MagicMock()
        identity_join_result.one_or_none.return_value = (identity, "Azure")
        target_result = MagicMock()
        target_result.one_or_none.return_value = target_user
        session.exec.side_effect = [identity_join_result, target_result]

        mock_store = AsyncMock()
        mock_store.revoke_all_for_user.return_value = 0

        service = UserIdentityService(session)
        with patch(_PATCH_SESSION_STORE, return_value=mock_store):
            await service.attach_identity(identity.id, target_user_id)

        assert mock_store.increment_token_version.call_count == 2
        mock_store.increment_token_version.assert_any_call(source_user_id)
        mock_store.increment_token_version.assert_any_call(target_user_id)
