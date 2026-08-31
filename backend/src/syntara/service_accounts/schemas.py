"""Service account API request/response schemas."""

from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from pydantic import ConfigDict, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema as PydanticCoreSchema
from sqlmodel import Field, SQLModel

from syntara.core.constants import FieldLimits
from syntara.core.models.base.query_params import BaseListParams
from syntara.core.models.pagination import ResourcesResponse
from syntara.core.models.user_reference import UserReference
from syntara.service_accounts.models.service_account import ServiceAccountStatus


class ServiceAccountCreate(SQLModel):
    """Schema for creating a new service account."""

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
    project_id: UUID = Field(description="Project to create the service account in")


class ServiceAccountUpdate(SQLModel):
    """Schema for updating a service account (PATCH)."""

    project_id: UUID | None = Field(
        default=None,
        description="Project ID (immutable after creation; rejected if different from stored value)",
    )
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


class ServiceAccountRead(SQLModel):
    """Schema for service account responses."""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    id: UUID
    name: str
    description: str | None = None
    status: ServiceAccountStatus
    project_id: UUID
    project_name: str | None = None
    is_project_deleted: bool = False
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
