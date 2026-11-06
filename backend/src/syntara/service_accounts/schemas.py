"""Service account API request/response schemas."""

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel

from syntara.core.constants import FieldLimits
from syntara.core.models.base.query_params import BaseListParams
from syntara.core.models.pagination import ResourcesResponse
from syntara.core.models.user_reference import UserReference, UserReferenceFieldsMixin
from syntara.service_accounts.models.service_account import ServiceAccountStatus


class ServiceAccountCreate(SQLModel):
    """Schema for creating a new service account."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]

    name: str = Field(
        ...,
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        description="Human-readable name for the service account",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional description of the service account's purpose",
    )
    project_id: UUID | None = Field(
        default=None,
        description="Optional creation context; this does not limit the service account's access",
    )


class ServiceAccountUpdate(SQLModel):
    """Schema for updating a service account (PATCH)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        description="Update the service account name",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Update the description",
    )


class ServiceAccountRead(UserReferenceFieldsMixin, SQLModel):
    """Schema for service account responses."""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    id: UUID
    name: str
    description: str | None = None
    project_id: UUID | None = Field(
        default=None,
        description="Project where the service account was created; informational only",
    )
    status: ServiceAccountStatus
    last_authenticated_at: datetime | None = None
    created_by: UserReference | UUID | str | None = Field(
        default=None, description="User who created the service account"
    )
    updated_by: UserReference | UUID | str | None = Field(
        default=None, description="User who last modified the service account"
    )
    created_at: datetime
    updated_at: datetime
    labels: dict[str, str] = Field(default_factory=dict)


class ServiceAccountListParams(BaseListParams):
    """Query parameters for listing service accounts."""

    status: ServiceAccountStatus | None = Field(default=None, description="Filter by status")
    name: str | None = Field(default=None, description="Filter by name")


class ServiceAccountListResponse(ResourcesResponse[ServiceAccountRead]):
    """Paginated list response for service accounts."""

    max_lifetime_days: int = Field(
        default=180,
        description="Maximum credential lifetime in days (0 for unlimited)",
    )


class ServiceAccountDirectoryEntry(SQLModel):
    """Basic identity for selectors; directory membership does not authorize management."""

    id: UUID
    name: str
    status: ServiceAccountStatus


class ServiceAccountDirectoryListResponse(ResourcesResponse[ServiceAccountDirectoryEntry]):
    """Paginated basic service-account directory."""
