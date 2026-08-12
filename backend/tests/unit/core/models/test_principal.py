"""Unit tests for Principal model and __principal_type__ marker convention."""

from uuid import uuid4

from syntara.core.models.principal import (
    Principal,
    PrincipalType,
)
from syntara.core.models.user import User
from syntara.service_accounts.models.service_account import ServiceAccount


class TestPrincipalType:
    """Tests for PrincipalType enum."""

    def test_user_value(self) -> None:
        assert PrincipalType.USER.value == "user"

    def test_service_account_value(self) -> None:
        assert PrincipalType.SERVICE_ACCOUNT.value == "service_account"

    def test_is_str_enum(self) -> None:
        assert isinstance(PrincipalType.USER, str)
        assert str(PrincipalType.USER) == "user"


class TestPrincipalModel:
    """Tests for the Principal SQLModel."""

    def test_tablename(self) -> None:
        assert Principal.__tablename__ == "principals"

    def test_for_user(self) -> None:
        uid = uuid4()
        p = Principal.for_user(uid)
        assert p.id == uid
        assert p.principal_type == PrincipalType.USER

    def test_for_service_account(self) -> None:
        sa_id = uuid4()
        p = Principal.for_service_account(sa_id)
        assert p.id == sa_id
        assert p.principal_type == PrincipalType.SERVICE_ACCOUNT

    def test_has_principal_type_index(self) -> None:
        table = Principal.__table__  # type: ignore[attr-defined]
        index_names = {idx.name for idx in table.indexes}
        assert "ix_principals_principal_type" in index_names


class TestPrincipalTypeMarker:
    """Tests for the __principal_type__ convention on subtype models."""

    def test_user_has_principal_type(self) -> None:
        assert User.__principal_type__ == PrincipalType.USER

    def test_service_account_has_principal_type(self) -> None:
        assert ServiceAccount.__principal_type__ == PrincipalType.SERVICE_ACCOUNT

    def test_principal_itself_has_no_marker(self) -> None:
        assert not hasattr(Principal, "__principal_type__")
