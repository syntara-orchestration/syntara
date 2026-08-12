"""Unit tests for user CRUD endpoints in users_router."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from syntara.core.models import User
from syntara.core.models.user_schemas import UserCreate, UserRead, UserUpdate
from syntara.users.users_router import (
    create_user,
    delete_user,
    get_user,
    update_user,
)


def _make_user(**kwargs: object) -> User:
    defaults = {
        "id": uuid4(),
        "username": "testuser",
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "is_enabled": True,
        "password_hash": "hashed",
    }
    defaults.update(kwargs)
    return User(**defaults)


class TestCreateUserEndpoint:
    """Tests for the POST /users endpoint."""

    @pytest.mark.asyncio
    async def test_creates_user_and_returns_read(self) -> None:
        user = _make_user()
        service = AsyncMock()
        service.create_user = AsyncMock(return_value=user)
        service.to_read = AsyncMock(
            return_value=UserRead(
                id=user.id,
                username=user.username,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                is_enabled=user.is_enabled,
                auth_type="local",
                created_at=user.created_at,
                updated_at=user.updated_at,
            )
        )

        request = UserCreate(
            username="newuser",
            email="new@example.com",
            first_name="New",
            last_name="User",
            password=SecretStr("ValidPassword123!"),
        )

        result = await create_user(request, service)

        assert result.username == user.username
        service.create_user.assert_called_once()
        service.to_read.assert_called_once_with(user)


class TestGetUserEndpoint:
    """Tests for the GET /users/{user_id} endpoint."""

    @pytest.mark.asyncio
    async def test_returns_user_read(self) -> None:
        user = _make_user()
        service = AsyncMock()
        service.get_user_by_id = AsyncMock(return_value=user)
        service.to_read = AsyncMock(
            return_value=UserRead(
                id=user.id,
                username=user.username,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                is_enabled=user.is_enabled,
                auth_type="local",
                created_at=user.created_at,
                updated_at=user.updated_at,
            )
        )

        result = await get_user(user.id, service)

        assert result.id == user.id
        service.get_user_by_id.assert_called_once_with(user.id)


class TestUpdateUserEndpoint:
    """Tests for the PATCH /users/{user_id} endpoint."""

    @pytest.mark.asyncio
    async def test_updates_user_and_returns_read(self) -> None:
        updated_user = _make_user(first_name="Updated")
        actor = _make_user(username="admin")
        service = AsyncMock()
        service.update_user = AsyncMock(return_value=updated_user)
        service.to_read = AsyncMock(
            return_value=UserRead(
                id=updated_user.id,
                username=updated_user.username,
                email=updated_user.email,
                first_name=updated_user.first_name,
                last_name=updated_user.last_name,
                is_enabled=updated_user.is_enabled,
                auth_type="local",
                created_at=updated_user.created_at,
                updated_at=updated_user.updated_at,
            )
        )
        db = AsyncMock()

        mock_store = AsyncMock()

        request = UserUpdate(first_name="Updated")
        with patch("syntara.users.users_router.create_session_store", return_value=mock_store):
            result = await update_user(updated_user.id, request, service, actor, db)

        assert result.first_name == "Updated"
        service.update_user.assert_called_once()

    @pytest.mark.asyncio
    async def test_revokes_sessions_on_password_change(self) -> None:
        user = _make_user()
        actor = _make_user(username="admin")
        service = AsyncMock()
        service.update_user = AsyncMock(return_value=user)
        db = AsyncMock()

        mock_store = AsyncMock()

        request = UserUpdate(password=SecretStr("NewPassword123!"))

        with patch("syntara.users.users_router.create_session_store", return_value=mock_store):
            await update_user(user.id, request, service, actor, db)

        mock_store.revoke_all_for_user.assert_called_once_with(user.id)

    @pytest.mark.asyncio
    async def test_rejects_weak_password_with_validation_error(self) -> None:
        """PATCH /users/{id} rejects weak passwords (FastAPI returns 422)."""
        with pytest.raises(ValidationError, match=r"at least 3.*character classes"):
            UserUpdate(password=SecretStr("weakpasswordonly!!"))


@pytest.mark.usefixtures("mock_session_store")
class TestDeleteUserEndpoint:
    """Tests for the DELETE /users/{user_id} endpoint."""

    @pytest.mark.asyncio
    async def test_calls_delete(self) -> None:
        user_id = uuid4()
        service = AsyncMock()
        db = AsyncMock()
        mock_store = AsyncMock()

        with patch("syntara.users.users_router.create_session_store", return_value=mock_store):
            await delete_user(user_id, service, db)

        service.delete_user.assert_called_once_with(user_id)
