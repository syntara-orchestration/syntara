"""Unit tests for user identity endpoints in users_router."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from syntara.auth.exceptions import UserIdentityNotFoundError
from syntara.core.models.user_identity_schemas import UserIdentityAttach, UserIdentityListResponse, UserIdentityRead
from syntara.users.users_router import (
    attach_user_identity,
    detach_user_identity,
    list_user_identities,
)


def _make_identity_read(*, user_id=None, identity_id=None, provider_name="Azure") -> UserIdentityRead:
    """Build a UserIdentityRead instance."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return UserIdentityRead(
        id=identity_id or uuid4(),
        user_id=user_id or uuid4(),
        identity_provider_id=uuid4(),
        issuer="https://login.microsoftonline.com/tenant",
        subject="oidc-sub-abc",
        created_at=now,
        updated_at=now,
        provider_name=provider_name,
    )


class TestListUserIdentities:
    """Tests for the GET /{user_id}/identities endpoint."""

    @pytest.mark.asyncio
    async def test_returns_identities_for_user(self) -> None:
        """Should return a list of identities from the service."""
        user_id = uuid4()
        identities = [
            _make_identity_read(user_id=user_id, provider_name="Azure"),
            _make_identity_read(user_id=user_id, provider_name="Okta"),
        ]
        service = AsyncMock()
        service.list_for_user.return_value = UserIdentityListResponse(resources=identities)

        result = await list_user_identities(user_id, service)

        assert len(result.resources) == 2
        service.list_for_user.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_identities(self) -> None:
        """Should return empty list when user has no identities."""
        user_id = uuid4()
        service = AsyncMock()
        service.list_for_user.return_value = UserIdentityListResponse(resources=[])

        result = await list_user_identities(user_id, service)

        assert result.resources == []


class TestAttachUserIdentity:
    """Tests for the POST /{user_id}/identities endpoint."""

    @pytest.mark.asyncio
    async def test_attaches_identity_and_returns_it(self) -> None:
        """Should call attach_identity and return the result directly."""
        user_id = uuid4()
        identity_id = uuid4()

        identity_read = _make_identity_read(user_id=user_id, identity_id=identity_id)

        service = AsyncMock()
        service.attach_identity.return_value = identity_read
        db = AsyncMock()

        request = UserIdentityAttach(identity_id=identity_id)
        result = await attach_user_identity(user_id, request, service, db)

        assert result.id == identity_id
        service.attach_identity.assert_called_once_with(identity_id, user_id)
        db.commit.assert_called_once()


class TestDetachUserIdentity:
    """Tests for the DELETE /{user_id}/identities/{identity_id} endpoint."""

    @pytest.mark.asyncio
    async def test_calls_delete_with_expected_user_id(self) -> None:
        """Should call delete_identity with expected_user_id for IDOR protection."""
        user_id = uuid4()
        identity_id = uuid4()
        service = AsyncMock()
        db = AsyncMock()

        await detach_user_identity(user_id, identity_id, service, db)

        service.delete_identity.assert_called_once_with(identity_id, expected_user_id=user_id)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_when_identity_not_found(self) -> None:
        """Should propagate UserIdentityNotFoundError from service."""
        user_id = uuid4()
        identity_id = uuid4()
        service = AsyncMock()
        db = AsyncMock()
        service.delete_identity.side_effect = UserIdentityNotFoundError(identity_id)

        with pytest.raises(UserIdentityNotFoundError):
            await detach_user_identity(user_id, identity_id, service, db)

    @pytest.mark.asyncio
    async def test_raises_when_identity_belongs_to_different_user(self) -> None:
        """Should raise when identity doesn't belong to the specified user."""
        user_id = uuid4()
        identity_id = uuid4()
        service = AsyncMock()
        db = AsyncMock()
        service.delete_identity.side_effect = UserIdentityNotFoundError(identity_id)

        with pytest.raises(UserIdentityNotFoundError):
            await detach_user_identity(user_id, identity_id, service, db)
