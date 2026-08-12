"""IdentityProvider SQLModel definition for database storage.

This module contains the IdentityProvider SQLModel class that extends the Resource base class
with identity provider specific fields as defined in the OpenAPI specification.
"""

from typing import Any, ClassVar
from uuid import UUID

from pydantic import ConfigDict
from sqlalchemy import Index, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from syntara.core.constants import FieldLimits
from syntara.core.models.base.named import NamedResource
from syntara.core.models.base.user_owned import UserOwnedResource
from syntara.core.models.pagination import ResourcesResponse
from syntara.core.utils.sqlmodel import DiscriminatedJSONB
from syntara.identity_providers.models.identity_provider_configuration import (
    IdentityProviderConfiguration,
    IdentityProviderConfigurationPatch,
    IdentityProviderConfigurationResponseTypes,
    IdentityProviderConfigurationTypes,
)


class IdentityProviderBase(NamedResource, UserOwnedResource):
    """IdentityProvider base model.

    Represents an external identity provider for authentication.
    Extends NamedResource and UserOwnedResource (without SoftDeletableResource
    since identity providers use hard delete).
    """

    FIELD_SCHEMA_EXTRAS: ClassVar[dict[str, dict[str, Any]]] = {
        **NamedResource.FIELD_SCHEMA_EXTRAS,
        **UserOwnedResource.FIELD_SCHEMA_EXTRAS,
    }

    name: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Human-readable provider name",
        index=True,
    )

    enabled: bool = Field(default=True, description="Enable/disable the identity provider", index=True)


class IdentityProvider(IdentityProviderBase, table=True):
    """IdentityProvider database model."""

    __tablename__ = "identity_providers"

    __filterable_fields__: ClassVar[list[str]] = [
        *NamedResource.__filterable_fields__,
        "enabled",
        "provider_type",
        "configuration.provider_type",
    ]

    __sortable_fields__: ClassVar[list[str]] = [
        *NamedResource.__sortable_fields__,
        "enabled",
    ]

    configuration: IdentityProviderConfigurationTypes = Field(
        sa_type=DiscriminatedJSONB(IdentityProviderConfiguration),  # type: ignore[call-overload]
        description="Provider-specific configuration",
    )

    secret_id: UUID | None = Field(
        default=None,
        foreign_key="secrets.id",
        description="FK to secret routing record containing encrypted client_secret",
        index=True,
    )

    __table_args__ = (
        UniqueConstraint("name", name="ix_identity_providers_name_unique"),
        Index("ix_identity_providers_created_at_id", "created_at", "id"),
    )


# ============================================================================
# API Request/Response Schemas
# ============================================================================


class IdentityProviderResponse(IdentityProviderBase):
    """Schema for IdentityProvider response with configuration details (excludes secrets)."""

    configuration: IdentityProviderConfigurationResponseTypes = Field(
        ..., description="Identity provider configuration"
    )


class IdentityProviderCreate(SQLModel):
    """Schema for creating a new identity provider."""

    name: str = Field(
        min_length=1, max_length=FieldLimits.NAME_MAX_LENGTH, description="Human-readable name for the provider"
    )

    description: str | None = Field(
        default=None, max_length=FieldLimits.DESCRIPTION_MAX_LENGTH, description="Detailed description of the provider"
    )

    configuration: IdentityProviderConfiguration = Field(
        description="Provider configuration", discriminator="provider_type"
    )


class IdentityProviderPatch(SQLModel):
    """Schema for partially updating an identity provider."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        description="Human-readable name for the provider",
    )

    description: str | None = Field(
        default=None,
        max_length=FieldLimits.DESCRIPTION_MAX_LENGTH,
        description="Detailed description of the provider",
    )

    configuration: IdentityProviderConfigurationPatch | None = Field(
        default=None,
        description="Provider-specific configuration (client_secret optional — preserves existing if omitted)",
        discriminator="provider_type",
    )

    enabled: bool | None = Field(default=None, description="Enable/disable the provider")

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
    )  # type: ignore[assignment]


# ============================================================================
# List Response
# ============================================================================


class IdentityProviderListResponse(ResourcesResponse[IdentityProviderResponse]):
    """Paginated list response for identity providers."""
