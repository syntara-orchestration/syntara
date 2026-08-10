"""ServiceAccount SQLModel definition.

Represents a service account for programmatic API access.  Credentials
are stored separately in the service_account_credentials table.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID, uuid4

from sqlalchemy import Index, String, text
from sqlmodel import CheckConstraint, DateTime, Field

from syntara.core.models.base.base_resource import AuditLevel
from syntara.core.models.base.named import NamedResource
from syntara.core.models.base.user_owned import UserOwnedResource
from syntara.core.models.principal import PrincipalType


class ServiceAccountStatus(StrEnum):
    """Operational status of a service account."""

    ACTIVE = "active"
    DISABLED = "disabled"


class ServiceAccount(NamedResource, UserOwnedResource, table=True):
    """Service account for programmatic API access (hard delete)."""

    FIELD_SCHEMA_EXTRAS: ClassVar[dict[str, dict[str, Any]]] = {
        **NamedResource.FIELD_SCHEMA_EXTRAS,
        **UserOwnedResource.FIELD_SCHEMA_EXTRAS,
    }

    __tablename__ = "service_accounts"
    __principal_type__: ClassVar[PrincipalType] = PrincipalType.SERVICE_ACCOUNT

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        foreign_key="principals.id",
        description="Unique identifier for the resource",
        index=True,
    )

    status: ServiceAccountStatus = Field(
        default=ServiceAccountStatus.ACTIVE,
        sa_type=String(10),  # type: ignore[call-overload]
        description="Operational status of the service account",
        index=True,
    )

    project_id: UUID = Field(
        foreign_key="projects.id",
        description="Project namespace for resource isolation",
        index=True,
    )

    token_version: int = Field(
        default=0,
        sa_column_kwargs={"server_default": text("0")},
        description="Incremented on disable/delete to invalidate issued tokens",
    )

    last_authenticated_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="Timestamp of the most recent successful authentication",
    )

    __table_args__ = (
        Index("ix_service_accounts_created_at_id", "created_at", "id"),
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_service_accounts_status_valid",
        ),
    )

    __filterable_fields__: ClassVar[list[str]] = list(
        dict.fromkeys(
            [
                *NamedResource.__filterable_fields__,
                *UserOwnedResource.__filterable_fields__,
                "status",
                "project_id",
                "last_authenticated_at",
            ]
        )
    )

    __sortable_fields__: ClassVar[list[str]] = list(
        dict.fromkeys(
            [
                *NamedResource.__sortable_fields__,
                *UserOwnedResource.__sortable_fields__,
                "last_authenticated_at",
            ]
        )
    )

    __auditable__: ClassVar[AuditLevel] = AuditLevel.META
    __auditable_fields__: ClassVar[list[str]] = [
        "name",
        "description",
        "status",
        "project_id",
        "token_version",
        "last_authenticated_at",
        "created_by",
        "updated_by",
    ]
