"""CredentialType SQLModel definition for database storage.

Defines the schema (what fields a Credential has) and consumption model
(how values are transformed into configuration for downstream consumers).
Managed types are preseeded and cannot be deleted by users.
"""

from typing import Any, ClassVar

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from syntara.core.constants import FieldLimits
from syntara.core.models.base import BaseResource
from syntara.core.models.pagination import ResourcesResponse


class CredentialType(BaseResource, table=True):
    """CredentialType database model.

    Extends BaseResource with credential-type-specific fields.
    Manages its own name field with a unique constraint.
    CredentialType does not support soft delete (managed types cannot be deleted).
    """

    __tablename__ = "credential_types"

    name: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Human-readable credential type name",
        unique=True,
        index=True,
    )

    description: str | None = Field(
        default=None,
        sa_type=Text(),  # type: ignore[call-overload]
        max_length=FieldLimits.DESCRIPTION_MAX_LENGTH,
        description="Optional description of the credential type",
    )

    inputs: dict[str, Any] = Field(
        default_factory=dict,
        sa_type=JSONB,
        description="Field schema defining credential inputs",
    )

    injectors: dict[str, Any] = Field(
        default_factory=dict,
        sa_type=JSONB,
        description="Consumption mapping templates for downstream consumers",
    )

    managed: bool = Field(
        default=False,
        description="True for preseeded system types that cannot be deleted",
    )

    __filterable_fields__: ClassVar[list[str]] = [
        *BaseResource.__filterable_fields__,
        "name",
        "managed",
    ]


class CredentialTypeRead(BaseResource):
    """Read schema for credential type API responses."""

    name: str
    description: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    injectors: dict[str, Any] = Field(default_factory=dict)
    managed: bool = False
    credential_count: int = Field(default=0, description="Number of credentials using this type")


class CredentialTypeListResponse(ResourcesResponse[CredentialTypeRead]):
    """Paginated list response for credential types."""
