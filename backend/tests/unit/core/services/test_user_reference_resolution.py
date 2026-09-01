"""Unit tests for shared user reference resolution helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from syntara.core.models.principal import KNOWN_SERVICE_CNS, service_principal_id
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
    async def test_extracts_ids_from_existing_user_references(self, mock_session: MagicMock) -> None:
        uid = uuid4()
        mock_session.exec = AsyncMock(return_value=[(uid, "erin", None)])
        obj = SimpleNamespace(created_by=UserReference(id=uid, name="stale"), updated_by=None)
        result = await lookup_users(mock_session, [obj])
        assert result is not None
        assert uid in result
        assert result[uid] == (uid, "erin")

    @pytest.mark.asyncio
    async def test_honors_custom_field_names(self, mock_session: MagicMock) -> None:
        uid = uuid4()
        mock_session.exec = AsyncMock(return_value=[(uid, "carol", None)])
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
        mock_session.exec = AsyncMock(return_value=[(uid, "dana", None)])
        host = _MixinHost(mock_session)
        obj = SimpleNamespace(created_by=uid, updated_by=None)
        await host.resolve_user_references([obj])
        assert isinstance(obj.created_by, UserReference)
        assert obj.created_by.name == "dana"


class TestNonUserPrincipals:
    """created_by/updated_by reference principals.id, not users.id.

    Service accounts and internal service principals have a ``principals`` row
    but no ``users`` row, so a users-only lookup silently dropped them.
    """

    @pytest.mark.asyncio
    async def test_resolves_service_account_by_name(self, mock_session: MagicMock) -> None:
        sa_id = uuid4()
        mock_session.exec = AsyncMock(return_value=[(sa_id, None, "ci-runner")])
        obj = SimpleNamespace(created_by=sa_id, updated_by=None)
        await resolve_user_references(mock_session, [obj])
        assert isinstance(obj.created_by, UserReference)
        assert obj.created_by.id == sa_id
        assert obj.created_by.name == "ci-runner"

    @pytest.mark.asyncio
    async def test_resolves_internal_service_principal_by_cn(self, mock_session: MagicMock) -> None:
        cn = KNOWN_SERVICE_CNS[0]
        svc_id = service_principal_id(cn)
        # A SERVICE principal has neither a users nor a service_accounts row.
        mock_session.exec = AsyncMock(return_value=[(svc_id, None, None)])
        obj = SimpleNamespace(created_by=svc_id, updated_by=svc_id)
        await resolve_user_references(mock_session, [obj])
        assert isinstance(obj.created_by, UserReference)
        assert obj.created_by.name == cn
        assert isinstance(obj.updated_by, UserReference)
        assert obj.updated_by.name == cn

    @pytest.mark.asyncio
    async def test_falls_back_to_raw_id_for_unknown_principal(self, mock_session: MagicMock) -> None:
        pid = uuid4()
        mock_session.exec = AsyncMock(return_value=[(pid, None, None)])
        obj = SimpleNamespace(created_by=pid, updated_by=None)
        await resolve_user_references(mock_session, [obj])
        assert isinstance(obj.created_by, UserReference)
        assert obj.created_by.name == str(pid)

    @pytest.mark.asyncio
    async def test_missing_principal_row_yields_none(self, mock_session: MagicMock) -> None:
        mock_session.exec = AsyncMock(return_value=[])
        obj = SimpleNamespace(created_by=uuid4(), updated_by=None)
        await resolve_user_references(mock_session, [obj])
        assert obj.created_by is None


class TestStringIdNormalisation:
    """The Read models still permit a str id; it must not be silently dropped."""

    @pytest.mark.asyncio
    async def test_resolves_uuid_shaped_string(self, mock_session: MagicMock) -> None:
        uid = uuid4()
        mock_session.exec = AsyncMock(return_value=[(uid, "frank", None)])
        obj = SimpleNamespace(created_by=str(uid), updated_by=None)
        await resolve_user_references(mock_session, [obj])
        assert isinstance(obj.created_by, UserReference)
        assert obj.created_by.id == uid
        assert obj.created_by.name == "frank"
