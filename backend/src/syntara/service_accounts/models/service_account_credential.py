"""ServiceAccountCredential SQLModel definition.

Stores credentials for service accounts, supporting multiple credentials
per account and secret rotation with a grace-period window.
"""

from datetime import datetime
from enum import StrEnum
from typing import ClassVar
from uuid import UUID, uuid4

from sqlalchemy import Index, String, Text
from sqlmodel import CheckConstraint, DateTime, Field

from syntara.core.models.base.base_resource import AuditLevel
from syntara.core.models.base.user_owned import UserOwnedResource


class ServiceAccountCredentialType(StrEnum):
    """Type of credential issued for a service account."""

    CLIENT_CREDENTIALS = "client_credentials"


class ServiceAccountCredentialStatus(StrEnum):
    """Operational status of a service account credential."""

    ACTIVE = "active"
    DISABLED = "disabled"


class ServiceAccountCredential(UserOwnedResource, table=True):
    """A credential belonging to a service account."""

    __tablename__ = "service_account_credentials"

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        description="Unique identifier for the credential",
        index=True,
    )

    service_account_id: UUID = Field(
        foreign_key="service_accounts.id",
        description="Service account this credential belongs to",
        index=True,
    )

    credential_type: ServiceAccountCredentialType = Field(
        sa_type=String(20),  # type: ignore[call-overload]
        description="Type of credential issued for a service account",
    )

    identifier: str = Field(
        sa_type=String(64),  # type: ignore[call-overload]
        description="Public identifier for the credential (e.g., client_id)",
        index=True,
    )

    hashed_secret: str = Field(
        sa_type=Text,
        description="Argon2id hash of the secret",
    )

    old_hashed_secret: str | None = Field(
        default=None,
        sa_type=Text,
        description="Previous secret hash, valid during rotation grace period",
    )

    old_secret_valid_until: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="Expiry timestamp for the old secret during rotation",
    )

    grace_period_seconds: int = Field(
        default=3600,
        ge=0,
        le=86400,
        description="Duration (seconds) that the old secret remains valid after rotation",
    )

    status: ServiceAccountCredentialStatus = Field(
        default=ServiceAccountCredentialStatus.ACTIVE,
        sa_type=String(10),  # type: ignore[call-overload]
        description="Operational status of the credential",
        index=True,
    )

    expires_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="Optional expiry timestamp for the credential",
    )

    last_used_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="Timestamp of the most recent use of this credential",
    )

    __table_args__ = (
        Index("ix_sa_credentials_identifier_unique", "identifier", unique=True),
        Index("ix_sa_credentials_sa_id_type", "service_account_id", "credential_type"),
        Index("ix_sa_credentials_created_at_id", "created_at", "id"),
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_sa_credentials_status_valid",
        ),
        CheckConstraint(
            "grace_period_seconds BETWEEN 0 AND 86400",
            name="ck_sa_credentials_grace_period_range",
        ),
        CheckConstraint(
            "credential_type IN ('client_credentials')",
            name="ck_sa_credentials_type_valid",
        ),
    )

    __filterable_fields__: ClassVar[list[str]] = list(
        dict.fromkeys(
            [
                *UserOwnedResource.__filterable_fields__,
                "service_account_id",
                "credential_type",
                "identifier",
                "status",
                "expires_at",
                "last_used_at",
            ]
        )
    )

    __sortable_fields__: ClassVar[list[str]] = list(
        dict.fromkeys(
            [
                *UserOwnedResource.__sortable_fields__,
                "last_used_at",
                "expires_at",
            ]
        )
    )

    __auditable__: ClassVar[AuditLevel] = AuditLevel.META
    __auditable_fields__: ClassVar[list[str]] = [
        "service_account_id",
        "credential_type",
        "identifier",
        "status",
        "grace_period_seconds",
        "expires_at",
        "last_used_at",
        "created_by",
        "updated_by",
    ]
