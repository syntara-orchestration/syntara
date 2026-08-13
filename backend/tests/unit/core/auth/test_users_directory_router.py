"""Unit tests for users directory endpoint."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.core.models.user import User
from syntara.users.users_directory_router import (
    UserDirectoryEntry,
    UserDirectoryListResponse,
    _UserDirectoryService,
    list_users_directory,
)


def _make_user(**kwargs: object) -> User:
    defaults = {
        "id": uuid4(),
        "username": "testuser",
        "first_name": "Test",
        "last_name": "User",
        "is_enabled": True,
        "password_hash": "hashed",
    }
    defaults.update(kwargs)
    return User(**defaults)


class TestListUsersDirectory:
    """Tests for GET /users_directory."""

    @pytest.mark.asyncio
    async def test_returns_lightweight_entries(self) -> None:
        u1 = _make_user(username="alice")
        u2 = _make_user(username="bob")
        expected = UserDirectoryListResponse(
            resources=[
                UserDirectoryEntry(id=u1.id, username="alice"),
                UserDirectoryEntry(id=u2.id, username="bob"),
            ],
            next=None,
            prev=None,
            total=None,
        )

        service = AsyncMock(spec=_UserDirectoryService)
        service.list_directory = AsyncMock(return_value=expected)

        request = MagicMock()
        request.query_params.items.return_value = []

        params = MagicMock()
        params.limit = 20
        params.cursor = None
        params.sort = None
        params.include_total = False

        result = await list_users_directory(request, service, params)

        assert len(result.resources) == 2
        assert result.resources[0].username == "alice"
        assert result.resources[1].username == "bob"
        service.list_directory.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_pagination_params(self) -> None:
        expected = UserDirectoryListResponse(resources=[], next=None, prev=None, total=5)
        service = AsyncMock(spec=_UserDirectoryService)
        service.list_directory = AsyncMock(return_value=expected)

        request = MagicMock()
        request.query_params.items.return_value = [("username[contains]", "test")]

        params = MagicMock()
        params.limit = 10
        params.cursor = "abc123"
        params.sort = "-username"
        params.include_total = True

        result = await list_users_directory(request, service, params)

        service.list_directory.assert_called_once_with(
            limit=10,
            cursor="abc123",
            sort="-username",
            query_params_items=[("username[contains]", "test")],
            include_total=True,
        )
        assert result.total == 5

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        expected = UserDirectoryListResponse(resources=[], next=None, prev=None, total=0)
        service = AsyncMock(spec=_UserDirectoryService)
        service.list_directory = AsyncMock(return_value=expected)

        request = MagicMock()
        request.query_params.items.return_value = []

        params = MagicMock()
        params.limit = 20
        params.cursor = None
        params.sort = None
        params.include_total = True

        result = await list_users_directory(request, service, params)

        assert result.resources == []
        assert result.total == 0


class TestUserDirectoryEntry:
    """Tests for the UserDirectoryEntry schema."""

    def test_fields(self) -> None:
        uid = uuid4()
        entry = UserDirectoryEntry(id=uid, username="alice")
        assert entry.id == uid
        assert entry.username == "alice"
