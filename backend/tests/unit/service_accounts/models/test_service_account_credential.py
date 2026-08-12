"""Unit tests for ServiceAccountCredential model."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from syntara.core.models.base.base_resource import AuditLevel
from syntara.service_accounts.models.service_account_credential import (
    ServiceAccountCredential,
    ServiceAccountCredentialStatus,
    ServiceAccountCredentialType,
)


class TestServiceAccountCredentialType:
    """Tests for ServiceAccountCredentialType enum values."""

    def test_client_credentials_value(self) -> None:
        assert ServiceAccountCredentialType.CLIENT_CREDENTIALS.value == "client_credentials"

    def test_only_expected_types(self) -> None:
        assert set(ServiceAccountCredentialType) == {
            ServiceAccountCredentialType.CLIENT_CREDENTIALS,
        }


class TestServiceAccountCredentialStatus:
    """Tests for ServiceAccountCredentialStatus enum values."""

    def test_active_value(self) -> None:
        assert ServiceAccountCredentialStatus.ACTIVE.value == "active"

    def test_disabled_value(self) -> None:
        assert ServiceAccountCredentialStatus.DISABLED.value == "disabled"


class TestServiceAccountCredentialModel:
    """Unit tests for the ServiceAccountCredential SQLModel."""

    def test_tablename(self) -> None:
        assert ServiceAccountCredential.__tablename__ == "service_account_credentials"

    def test_is_table_model(self) -> None:
        table = ServiceAccountCredential.__table__  # type: ignore[attr-defined]
        pk_cols = [col.name for col in table.primary_key.columns]
        assert pk_cols == ["id"]

    def test_has_expected_columns(self) -> None:
        table = ServiceAccountCredential.__table__  # type: ignore[attr-defined]
        column_names = {col.name for col in table.columns}
        expected = {
            "id",
            "service_account_id",
            "credential_type",
            "identifier",
            "hashed_secret",
            "old_hashed_secret",
            "old_secret_valid_until",
            "grace_period_seconds",
            "status",
            "expires_at",
            "last_used_at",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "labels",
        }
        assert column_names == expected

    def test_identifier_has_unique_index(self) -> None:
        table = ServiceAccountCredential.__table__  # type: ignore[attr-defined]
        unique_indexes = [idx.name for idx in table.indexes if idx.unique]
        assert "ix_sa_credentials_identifier_unique" in unique_indexes

    def test_status_check_constraint(self) -> None:
        table = ServiceAccountCredential.__table__  # type: ignore[attr-defined]
        constraint_names = [c.name for c in table.constraints if hasattr(c, "sqltext")]
        assert "ck_sa_credentials_status_valid" in constraint_names

    def test_grace_period_check_constraint(self) -> None:
        table = ServiceAccountCredential.__table__  # type: ignore[attr-defined]
        constraint_names = [c.name for c in table.constraints if hasattr(c, "sqltext")]
        assert "ck_sa_credentials_grace_period_range" in constraint_names

    def test_type_check_constraint(self) -> None:
        table = ServiceAccountCredential.__table__  # type: ignore[attr-defined]
        constraint_names = [c.name for c in table.constraints if hasattr(c, "sqltext")]
        assert "ck_sa_credentials_type_valid" in constraint_names

    def test_default_status_is_active(self) -> None:
        cred = ServiceAccountCredential(
            service_account_id=uuid4(),
            credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
            identifier="nx_sa_test123456789",
            hashed_secret="$argon2id$placeholder",  # noqa: S106
            created_by=uuid4(),
        )
        assert cred.status == ServiceAccountCredentialStatus.ACTIVE

    def test_default_grace_period(self) -> None:
        cred = ServiceAccountCredential(
            service_account_id=uuid4(),
            credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
            identifier="nx_sa_test123456789",
            hashed_secret="$argon2id$placeholder",  # noqa: S106
            created_by=uuid4(),
        )
        assert cred.grace_period_seconds == 3600

    def test_grace_period_rejects_negative(self) -> None:
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            ServiceAccountCredential(
                service_account_id=uuid4(),
                credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
                identifier="nx_sa_test123456789",
                hashed_secret="$argon2id$placeholder",  # noqa: S106
                created_by=uuid4(),
                grace_period_seconds=-1,
            )

    def test_grace_period_rejects_over_24h(self) -> None:
        with pytest.raises(ValidationError, match="less than or equal to 86400"):
            ServiceAccountCredential(
                service_account_id=uuid4(),
                credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
                identifier="nx_sa_test123456789",
                hashed_secret="$argon2id$placeholder",  # noqa: S106
                created_by=uuid4(),
                grace_period_seconds=86401,
            )

    def test_optional_fields_default_none(self) -> None:
        cred = ServiceAccountCredential(
            service_account_id=uuid4(),
            credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
            identifier="nx_sa_test123456789",
            hashed_secret="$argon2id$placeholder",  # noqa: S106
            created_by=uuid4(),
        )
        assert cred.old_hashed_secret is None
        assert cred.old_secret_valid_until is None
        assert cred.expires_at is None
        assert cred.last_used_at is None
        assert cred.updated_by is None


class TestServiceAccountCredentialAuditConfig:
    """Tests for audit configuration — hashed secrets must be excluded."""

    def test_audit_level_is_meta(self) -> None:
        assert ServiceAccountCredential.__auditable__ == AuditLevel.META

    def test_hashed_secret_excluded_from_audit(self) -> None:
        assert "hashed_secret" not in ServiceAccountCredential.__auditable_fields__
        assert "old_hashed_secret" not in ServiceAccountCredential.__auditable_fields__

    def test_auditable_fields_include_key_metadata(self) -> None:
        for field in ("identifier", "credential_type", "status", "service_account_id"):
            assert field in ServiceAccountCredential.__auditable_fields__
