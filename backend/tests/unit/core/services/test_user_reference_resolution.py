"""Unit tests for the shared user reference resolver."""

from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from syntara.core.models.principal import KNOWN_SERVICE_CNS, service_principal_id
from syntara.core.models.user_reference import UserReference, UserReferenceType
from syntara.core.services.user_reference_resolution import (
    UserReferenceResolver,
    UserReferenceResolverMixin,
    user_reference_fields,
)


class _MixinHost(UserReferenceResolverMixin):
    def __init__(self, session: MagicMock) -> None:
        self.session = session


class _OwnerSchema:
    """A schema declaring a non-default user-reference field."""

    USER_REFERENCE_FIELDS: ClassVar[tuple[str, ...]] = ("owner",)

    def __init__(self, owner: object, created_by: object = None) -> None:
        self.owner = owner
        self.created_by = created_by


def _row(
    principal_id: object, username: str | None = None, sa_name: str | None = None
) -> tuple[object, str, str | None, None, None, str | None]:
    """Build a lookup row: (principal_id, principal_type, username, first_name, last_name, service_account_name).

    The principal type follows from which child-table columns are populated.
    """
    if username is not None:
        ptype = "user"
    elif sa_name is not None:
        ptype = "service_account"
    else:
        ptype = "service"
    return (principal_id, ptype, username, None, None, sa_name)


@pytest.fixture
def mock_session() -> MagicMock:
    return MagicMock()


class TestUserReferenceFields:
    """Field names come from the schema, not from the caller."""

    def test_defaults_to_audit_pair(self) -> None:
        assert user_reference_fields(SimpleNamespace()) == ("created_by", "updated_by")

    def test_reads_declaration_from_schema(self) -> None:
        assert user_reference_fields(_OwnerSchema(owner=None)) == ("owner",)


class TestLookup:
    """Tests for the batch principal lookup."""

    @pytest.mark.asyncio
    async def test_returns_empty_map_when_no_ids(self, mock_session: MagicMock) -> None:
        obj = SimpleNamespace(created_by=None, updated_by=None)
        assert await UserReferenceResolver(mock_session).lookup([obj]) == {}
        mock_session.exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_on_oserror(self, mock_session: MagicMock) -> None:
        mock_session.exec = AsyncMock(side_effect=OSError("network"))
        obj = SimpleNamespace(created_by=uuid4(), updated_by=None)
        assert await UserReferenceResolver(mock_session).lookup([obj]) is None

    @pytest.mark.asyncio
    async def test_extracts_ids_from_existing_user_references(self, mock_session: MagicMock) -> None:
        uid = uuid4()
        mock_session.exec = AsyncMock(return_value=[_row(uid, "erin")])
        obj = SimpleNamespace(
            created_by=UserReference(id=uid, name="stale", type=UserReferenceType.USER), updated_by=None
        )
        result = await UserReferenceResolver(mock_session).lookup([obj])
        assert result == {uid: ("erin", "user")}

    @pytest.mark.asyncio
    async def test_honors_declared_field_names(self, mock_session: MagicMock) -> None:
        uid = uuid4()
        mock_session.exec = AsyncMock(return_value=[_row(uid, "carol")])
        # created_by is set but not declared, so it must not be looked up.
        result = await UserReferenceResolver(mock_session).lookup([_OwnerSchema(owner=uid, created_by=uuid4())])
        assert result == {uid: ("carol", "user")}


class TestResolve:
    """Tests for in-place UserReference assignment."""

    @pytest.mark.asyncio
    async def test_leaves_none_fields_untouched(self, mock_session: MagicMock) -> None:
        mock_session.exec = AsyncMock(return_value=[])
        obj = SimpleNamespace(created_by=None, updated_by=None)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert obj.created_by is None
        assert obj.updated_by is None
        mock_session.exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_clears_fields_when_lookup_raises(self, mock_session: MagicMock) -> None:
        mock_session.exec = AsyncMock(side_effect=SQLAlchemyError("db down"))
        uid = uuid4()
        obj = SimpleNamespace(created_by=uid, updated_by=uid)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert obj.created_by is None
        assert obj.updated_by is None

    @pytest.mark.asyncio
    async def test_resolves_only_declared_fields(self, mock_session: MagicMock) -> None:
        uid, other = uuid4(), uuid4()
        mock_session.exec = AsyncMock(return_value=[_row(uid, "carol")])
        obj = _OwnerSchema(owner=uid, created_by=other)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert isinstance(obj.owner, UserReference)
        assert obj.created_by == other

    @pytest.mark.asyncio
    async def test_mixin_delegates_to_resolver(self, mock_session: MagicMock) -> None:
        uid = uuid4()
        mock_session.exec = AsyncMock(return_value=[_row(uid, "dana")])
        obj = SimpleNamespace(created_by=uid, updated_by=None)
        await _MixinHost(mock_session).resolve_user_references([obj])
        assert isinstance(obj.created_by, UserReference)
        assert obj.created_by.name == "dana"


class TestDisplayName:
    """UserReference.name is the principal's display name, matching User.display_name."""

    @pytest.mark.asyncio
    async def test_prefers_full_name_over_username(self, mock_session: MagicMock) -> None:
        uid = uuid4()
        mock_session.exec = AsyncMock(return_value=[(uid, "user", "gwen", "Gwen", "Stacy", None)])
        obj = SimpleNamespace(created_by=uid, updated_by=None)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert obj.created_by.name == "Gwen Stacy"

    @pytest.mark.asyncio
    async def test_falls_back_to_username_when_names_blank(self, mock_session: MagicMock) -> None:
        uid = uuid4()
        mock_session.exec = AsyncMock(return_value=[(uid, "user", "gwen", "  ", None, None)])
        obj = SimpleNamespace(created_by=uid, updated_by=None)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert obj.created_by.name == "gwen"

    @pytest.mark.asyncio
    async def test_uses_single_name_part_when_only_one_present(self, mock_session: MagicMock) -> None:
        uid = uuid4()
        mock_session.exec = AsyncMock(return_value=[(uid, "user", "gwen", None, "Stacy", None)])
        obj = SimpleNamespace(created_by=uid, updated_by=None)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert obj.created_by.name == "Stacy"


class TestNonUserPrincipals:
    """created_by/updated_by reference principals.id, not users.id.

    Service accounts and internal service principals have a ``principals`` row
    but no ``users`` row, so a users-only lookup silently dropped them.
    """

    @pytest.mark.asyncio
    async def test_resolves_service_account_by_name(self, mock_session: MagicMock) -> None:
        sa_id = uuid4()
        mock_session.exec = AsyncMock(return_value=[_row(sa_id, sa_name="ci-runner")])
        obj = SimpleNamespace(created_by=sa_id, updated_by=None)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert isinstance(obj.created_by, UserReference)
        assert obj.created_by.id == sa_id
        assert obj.created_by.name == "ci-runner"

    @pytest.mark.asyncio
    async def test_resolves_internal_service_principal_by_cn(self, mock_session: MagicMock) -> None:
        cn = KNOWN_SERVICE_CNS[0]
        svc_id = service_principal_id(cn)
        # A SERVICE principal has neither a users nor a service_accounts row.
        mock_session.exec = AsyncMock(return_value=[_row(svc_id)])
        obj = SimpleNamespace(created_by=svc_id, updated_by=svc_id)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert obj.created_by.name == cn
        assert obj.updated_by.name == cn

    @pytest.mark.asyncio
    async def test_falls_back_to_raw_id_for_unknown_principal(self, mock_session: MagicMock) -> None:
        pid = uuid4()
        mock_session.exec = AsyncMock(return_value=[_row(pid)])
        obj = SimpleNamespace(created_by=pid, updated_by=None)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert obj.created_by.name == str(pid)

    @pytest.mark.asyncio
    async def test_missing_principal_row_yields_none(self, mock_session: MagicMock) -> None:
        mock_session.exec = AsyncMock(return_value=[])
        obj = SimpleNamespace(created_by=uuid4(), updated_by=None)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert obj.created_by is None


class TestStringIdNormalisation:
    """The Read models still permit a str id; it must not be silently dropped."""

    @pytest.mark.asyncio
    async def test_resolves_uuid_shaped_string(self, mock_session: MagicMock) -> None:
        uid = uuid4()
        mock_session.exec = AsyncMock(return_value=[_row(uid, "frank")])
        obj = SimpleNamespace(created_by=str(uid), updated_by=None)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert isinstance(obj.created_by, UserReference)
        assert obj.created_by.id == uid
        assert obj.created_by.name == "frank"

    @pytest.mark.asyncio
    async def test_non_uuid_string_is_cleared(self, mock_session: MagicMock) -> None:
        mock_session.exec = AsyncMock(return_value=[])
        obj = SimpleNamespace(created_by="not-a-uuid", updated_by=None)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert obj.created_by == "not-a-uuid"


def _typed_row(
    principal_id: object,
    principal_type: str,
    username: str | None = None,
    sa_name: str | None = None,
) -> tuple[object, str, str | None, None, None, str | None]:
    """Build a lookup row carrying the principal type.

    Shape: (principal_id, principal_type, username, first_name, last_name, service_account_name).
    """
    return (principal_id, principal_type, username, None, None, sa_name)


class TestPrincipalType:
    """A UserReference says what kind of principal it points at.

    Only ``user`` principals have a detail page, so clients need the type to
    decide whether to link. A hard-deleted user keeps its ``principals`` row
    (``delete_user`` relies on it for FK integrity) but loses its ``users`` row,
    and must not surface as a raw UUID.
    """

    @pytest.mark.asyncio
    async def test_deleted_user_is_named_deleted_user_not_raw_uuid(self, mock_session: MagicMock) -> None:
        pid = uuid4()
        # principals.principal_type == "user" but no users row joined.
        mock_session.exec = AsyncMock(return_value=[_typed_row(pid, "user")])
        obj = SimpleNamespace(created_by=pid, updated_by=None)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert obj.created_by.name == "Deleted user"
        assert obj.created_by.type == "deleted_user"

    @pytest.mark.asyncio
    async def test_service_account_reference_carries_principal_type(self, mock_session: MagicMock) -> None:
        sa_id = uuid4()
        mock_session.exec = AsyncMock(return_value=[_typed_row(sa_id, "service_account", sa_name="ci-runner")])
        obj = SimpleNamespace(created_by=sa_id, updated_by=None)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert obj.created_by.name == "ci-runner"
        assert obj.created_by.type == "service_account"

    @pytest.mark.asyncio
    async def test_live_user_reference_carries_user_type(self, mock_session: MagicMock) -> None:
        uid = uuid4()
        mock_session.exec = AsyncMock(return_value=[_typed_row(uid, "user", username="erin")])
        obj = SimpleNamespace(created_by=uid, updated_by=None)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert obj.created_by.name == "erin"
        assert obj.created_by.type == "user"


class TestNamelessPrincipals:
    """Principals with no child row must never surface as a raw UUID.

    Legacy ``system`` rows have no child table at all, and
    ``delete_service_account`` keeps the ``principals`` row while dropping the
    ``service_accounts`` row, exactly like ``delete_user`` does for users.
    """

    @pytest.mark.asyncio
    async def test_system_principal_is_named_system(self, mock_session: MagicMock) -> None:
        pid = uuid4()
        mock_session.exec = AsyncMock(return_value=[_typed_row(pid, "system")])
        obj = SimpleNamespace(created_by=pid, updated_by=None)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert obj.created_by.name == "System"
        assert obj.created_by.type == "system"

    @pytest.mark.asyncio
    async def test_deleted_service_account_is_named_not_raw_uuid(self, mock_session: MagicMock) -> None:
        sa_id = uuid4()
        # principals.principal_type == "service_account" but no service_accounts row joined.
        mock_session.exec = AsyncMock(return_value=[_typed_row(sa_id, "service_account")])
        obj = SimpleNamespace(created_by=sa_id, updated_by=None)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert obj.created_by.name == "Deleted service account"
        assert obj.created_by.type == "deleted_service_account"

    @pytest.mark.asyncio
    async def test_internal_service_reference_carries_service_type(self, mock_session: MagicMock) -> None:
        cn = KNOWN_SERVICE_CNS[0]
        svc_id = service_principal_id(cn)
        mock_session.exec = AsyncMock(return_value=[_typed_row(svc_id, "service")])
        obj = SimpleNamespace(created_by=svc_id, updated_by=None)
        await UserReferenceResolver(mock_session).resolve([obj])
        assert obj.created_by.name == cn
        assert obj.created_by.type == "service"
