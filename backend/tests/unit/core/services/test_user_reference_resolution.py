"""Unit tests for shared user reference resolution helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from syntara.core.models.user_reference import UserReference
from syntara.core.services.user_reference_resolution import (
    UserReferenceMixin,
    lookup_users,
    resolve_user_references,
)


class _MixinHost(UserReferenceMixin):
    def __init__(self, session: MagicMock) -> None:
        self.session = session


@pytest.fixture
def mock_session() -> MagicMock:
    return MagicMock()


class TestLookupUsers:
    """Tests for the batch user lookup helper."""

    @pytest.mark.asyncio
    async def test_returns_empty_map_when_no_user_ids(self, mock_session: MagicMock) -> None:
        obj = SimpleNamespace(created_by=None, updated_by=None)
        result = await lookup_users(mock_session, [obj])
        assert result == {}
        mock_session.exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_on_oserror(self, mock_session: MagicMock) -> None:
        mock_session.exec = AsyncMock(side_effect=OSError("network"))
        obj = SimpleNamespace(created_by=uuid4(), updated_by=None)
        assert await lookup_users(mock_session, [obj]) is None

    @pytest.mark.asyncio
    async def test_honors_custom_field_names(self, mock_session: MagicMock) -> None:
        uid = uuid4()
        mock_session.exec = AsyncMock(return_value=[(uid, "carol")])
        obj = SimpleNamespace(owner=uid, created_by=uuid4())
        result = await lookup_users(mock_session, [obj], field_names=("owner",))
        assert result is not None
        assert uid in result
        assert result[uid] == (uid, "carol")


class TestResolveUserReferencesHelper:
    """Tests for in-place UserReference assignment."""

    @pytest.mark.asyncio
    async def test_leaves_none_fields_untouched(self, mock_session: MagicMock) -> None:
        mock_session.exec = AsyncMock(return_value=[])
        obj = SimpleNamespace(created_by=None, updated_by=None)
        await resolve_user_references(mock_session, [obj])
        assert obj.created_by is None
        assert obj.updated_by is None
        mock_session.exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_clears_fields_when_lookup_raises(self, mock_session: MagicMock) -> None:
        mock_session.exec = AsyncMock(side_effect=SQLAlchemyError("db down"))
        uid = uuid4()
        obj = SimpleNamespace(created_by=uid, updated_by=uid)
        await resolve_user_references(mock_session, [obj])
        assert obj.created_by is None
        assert obj.updated_by is None


class TestUserReferenceMixin:
    """Tests for the service mixin aliases."""

    @pytest.mark.asyncio
    async def test_mixin_delegates_to_helper(self, mock_session: MagicMock) -> None:
        uid = uuid4()
        mock_session.exec = AsyncMock(return_value=[(uid, "dana")])
        host = _MixinHost(mock_session)
        obj = SimpleNamespace(created_by=uid, updated_by=None)
        await host.resolve_user_references([obj])
        assert isinstance(obj.created_by, UserReference)
        assert obj.created_by.name == "dana"
