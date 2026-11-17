"""Unit tests for ServiceAccount model."""

from uuid import uuid4

from syntara.core.models.base.base_resource import AuditLevel
from syntara.service_accounts.models.service_account import (
    ServiceAccount,
    ServiceAccountStatus,
)


class TestServiceAccountStatus:
    """Tests for ServiceAccountStatus enum values."""

    def test_active_value(self) -> None:
        assert ServiceAccountStatus.ACTIVE.value == "active"

    def test_disabled_value(self) -> None:
        assert ServiceAccountStatus.DISABLED.value == "disabled"

    def test_only_two_statuses(self) -> None:
        assert set(ServiceAccountStatus) == {
            ServiceAccountStatus.ACTIVE,
            ServiceAccountStatus.DISABLED,
        }


class TestServiceAccountModel:
    """Unit tests for the ServiceAccount SQLModel."""

    def test_tablename(self) -> None:
        assert ServiceAccount.__tablename__ == "service_accounts"

    def test_is_table_model(self) -> None:
        table = ServiceAccount.__table__  # type: ignore[attr-defined]
        pk_cols = [col.name for col in table.primary_key.columns]
        assert pk_cols == ["id"]

    def test_has_expected_columns(self) -> None:
        table = ServiceAccount.__table__  # type: ignore[attr-defined]
        column_names = {col.name for col in table.columns}
        expected = {
            "id",
            "name",
            "description",
            "status",
            "project_id",
            "token_version",
            "last_authenticated_at",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "labels",
        }
        assert column_names == expected

    def test_project_context_is_nullable_and_cleared_on_project_delete(self) -> None:
        project_id = ServiceAccount.__table__.c.project_id  # type: ignore[attr-defined]
        assert project_id.nullable
        assert next(iter(project_id.foreign_keys)).ondelete == "SET NULL"

    def test_status_check_constraint(self) -> None:
        table = ServiceAccount.__table__  # type: ignore[attr-defined]
        constraint_names = [c.name for c in table.constraints if hasattr(c, "sqltext")]
        assert "ck_service_accounts_status_valid" in constraint_names

    def test_default_status_is_active(self) -> None:
        sa = ServiceAccount(
            name="test",
            created_by=uuid4(),
        )
        assert sa.status == ServiceAccountStatus.ACTIVE

    def test_optional_fields_default_none(self) -> None:
        sa = ServiceAccount(
            name="test",
            created_by=uuid4(),
        )
        assert sa.last_authenticated_at is None
        assert sa.updated_by is None


class TestServiceAccountAuditConfig:
    """Tests for audit configuration."""

    def test_audit_level_is_meta(self) -> None:
        assert ServiceAccount.__auditable__ == AuditLevel.META

    def test_auditable_fields_include_key_metadata(self) -> None:
        for field in ("name", "status"):
            assert field in ServiceAccount.__auditable_fields__
