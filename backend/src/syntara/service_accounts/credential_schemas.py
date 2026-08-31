"""Service account credential API request/response schemas."""

from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from pydantic import AwareDatetime, ConfigDict, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema as PydanticCoreSchema
from sqlmodel import Field, SQLModel

from syntara.core.models.base.query_params import BaseListParams
from syntara.core.models.pagination import ResourcesResponse
from syntara.core.models.user_reference import UserReference
from syntara.service_accounts.constants import MAX_CREDENTIALS_PER_SA
from syntara.service_accounts.models.service_account_credential import (
    ServiceAccountCredentialStatus,
    ServiceAccountCredentialType,
)


class ServiceAccountCredentialCreate(SQLModel):
    """Schema for creating a new service account credential."""

    credential_type: ServiceAccountCredentialType = Field(
        description="Type of credential to create",
    )
    grace_period_seconds: int = Field(
        default=3600,
        ge=0,
        le=86400,
        description="Duration (seconds) old secret remains valid after rotation",
    )
    expires_at: AwareDatetime | None = Field(
        default=None,
        description=(
            "Optional expiry timestamp (must include timezone). If omitted, auto-set from the configured "
            "maximum credential lifetime. Rejected if it exceeds the configured limit."
        ),
    )


class ServiceAccountCredentialRead(SQLModel):
    """Schema for credential responses (excludes secrets)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    id: UUID
    service_account_id: UUID
    credential_type: ServiceAccountCredentialType
    identifier: str
    status: ServiceAccountCredentialStatus
    grace_period_seconds: int
    expires_at: datetime | None = None
    old_secret_valid_until: datetime | None = None
    last_used_at: datetime | None = None
    created_by: UserReference | UUID | str | None = Field(default=None, description="User who created the credential")
    updated_by: UserReference | UUID | str | None = Field(
        default=None, description="User who last modified the credential"
    )
    created_at: datetime
    updated_at: datetime

    FIELD_SCHEMA_EXTRAS: ClassVar[dict[str, dict[str, Any]]] = {
        "created_by": UserReference.OPENAPI_NULLABLE_FIELD,
        "updated_by": UserReference.OPENAPI_NULLABLE_FIELD,
    }

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: PydanticCoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        """Inject field-level OpenAPI metadata into the JSON schema."""
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        props = json_schema.get("properties", {})
        for field, extras in cls.FIELD_SCHEMA_EXTRAS.items():
            if field in props:
                props[field].update(extras)
        return json_schema


class ServiceAccountCredentialCreateResponse(ServiceAccountCredentialRead):
    """Schema for the create response — includes one-time plaintext secret(s)."""

    client_secret: str | None = Field(
        default=None,
        description="Plaintext client secret (shown only once)",
    )


class ServiceAccountCredentialRotateRequest(SQLModel):
    """Schema for rotating a credential's secret."""

    grace_period_seconds: int | None = Field(
        default=None,
        ge=0,
        le=86400,
        description="Override grace period for this rotation (uses credential default if omitted)",
    )


class ServiceAccountCredentialRotateResponse(ServiceAccountCredentialCreateResponse):
    """Schema for the rotate response — same shape as create response."""


class ServiceAccountCredentialListParams(BaseListParams):
    """Query parameters for listing service account credentials."""

    credential_type: ServiceAccountCredentialType | None = Field(default=None, description="Filter by credential type")
    status: ServiceAccountCredentialStatus | None = Field(default=None, description="Filter by status")


class ServiceAccountCredentialListResponse(ResourcesResponse[ServiceAccountCredentialRead]):
    """Paginated list response for service account credentials."""

    max_credentials: int = Field(
        default=MAX_CREDENTIALS_PER_SA,
        description="Maximum number of credentials allowed per service account",
    )
    total_credentials: int = Field(
        default=0,
        description="Total number of credentials for this service account (ignoring filters)",
    )
    max_lifetime_days: int = Field(
        default=180,
        description="Maximum credential lifetime in days (0 for unlimited)",
    )
