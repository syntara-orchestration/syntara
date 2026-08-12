"""BaseResource SQLModel definition.

This module contains the foundational BaseResource SQLModel class that provides
system-managed metadata fields (id, timestamps, labels) for all API resources.
"""

from abc import ABC
from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar
from uuid import UUID, uuid4

from pydantic import ConfigDict, GetJsonSchemaHandler, field_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema as PydanticCoreSchema
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import DateTime, Field, SQLModel

from syntara.core.constants import ValidationMessages
from syntara.core.exceptions import SafeValueError


class AuditLevel(str, Enum):
    """Audit trail granularity for SQLModel resources.

    Controls what data is captured in the automatic CRUD audit trail:

    - FULL: Capture all mapped columns (default for most models)
    - META: Capture only metadata fields (id, timestamps, labels) + model-specific fields
            defined in __auditable_fields__. Use for models with sensitive data like Credential.
    - NONE: Skip auditing entirely (use for tables that should not be audited)

    """

    FULL = "full"
    META = "meta"
    NONE = "none"


def _utc_now() -> datetime:
    """Generate UTC timestamp for field defaults."""
    return datetime.now(UTC)


class BaseResource(SQLModel, ABC):
    """Abstract base SQLModel for all API resources with system-managed metadata.

    This abstract class provides the basic structure that all API and database resources should inherit from,
    including UUID identification, automatic timestamps, and key-value labels for
    flexible metadata storage.

    This class cannot be instantiated directly and does not create database tables.
    Concrete subclasses must inherit from this class and SQLModel and set table=True.

    ```
    class MyBaseResource(BaseResource, table=True):
        pass
    ```

    Attributes:
        id: Unique UUID identifier (primary key, auto-generated)
        created_at: Timestamp when resource was created (auto-set)
        updated_at: Timestamp when resource was last updated (auto-updated)
        labels: Optional dictionary of string key-value pairs for metadata

    """

    # Primary key with UUID
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        description="Unique identifier for the resource",
        title="Resource ID",
        index=True,
    )

    # Automatic timestamps
    # NOTE: These fields store timezone-aware datetime objects (always UTC).
    # Server defaults ensure consistency even for direct DB inserts.
    created_at: datetime = Field(
        default_factory=_utc_now,
        description="Timestamp when resource was created",
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        sa_column_kwargs={"server_default": text("now()")},
        index=True,
    )

    updated_at: datetime = Field(
        default_factory=_utc_now,
        description="Timestamp when resource was last updated",
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        sa_column_kwargs={"server_default": text("now()")},
        index=True,
    )

    # Labels as JSONB column for key-value pairs
    # Server default ensures consistency even for direct DB inserts.
    labels: dict[str, str] = Field(
        default_factory=dict,
        sa_type=JSONB,
        sa_column_kwargs={"server_default": text("'{}'::jsonb")},
        description="Key-value pairs for resource labeling and filtering",
    )

    @field_validator("labels", mode="before")
    @classmethod
    def validate_labels(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        """Validate that labels dictionary contains only string values."""
        if v is None:
            return v

        if not isinstance(v, dict):
            raise SafeValueError(ValidationMessages.LABELS_MUST_BE_DICT)

        for key, value in v.items():
            if not isinstance(key, str):
                msg = ValidationMessages.LABELS_KEY_MUST_BE_STRING.format(key=key, type_name=type(key).__name__)  # type: ignore[unreachable]
                raise SafeValueError(msg)
            if not isinstance(value, str):
                msg = ValidationMessages.LABELS_VALUE_MUST_BE_STRING.format(key=key, type_name=type(value).__name__)  # type: ignore[unreachable]
                raise SafeValueError(msg)

        return v

    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,
        validate_by_name=True,
        validate_assignment=True,
        extra="forbid",  # Reject unknown fields
    )  # type: ignore[assignment]

    # Base filterable fields - common to all resources
    __filterable_fields__: ClassVar[list[str]] = [
        "id",
        "created_at",
        "updated_at",
    ]

    # Base sortable fields - common to all resources
    __sortable_fields__: ClassVar[list[str]] = [
        "created_at",
        "updated_at",
    ]

    # Audit trail configuration
    # Set to AuditLevel.NONE to disable auditing, AuditLevel.META to audit only metadata
    __auditable__: ClassVar[AuditLevel] = AuditLevel.FULL

    # Meta-only audit fields (used when __auditable__ = AuditLevel.META)
    # Include BaseResource standard fields (id, timestamps, labels) plus model-specific safe fields.
    # Example for Credential: ["id", "created_at", "updated_at", "labels", "name", "credential_type_id", "enabled"]
    __auditable_fields__: ClassVar[list[str]] = []

    FIELD_SCHEMA_EXTRAS: ClassVar[dict[str, dict[str, Any]]] = {
        "id": {"readOnly": True, "example": "550e8400-e29b-41d4-a716-446655440000"},
        "created_at": {"readOnly": True, "example": "2025-10-09T12:00:00Z"},
        "updated_at": {"readOnly": True, "example": "2025-10-09T12:30:00Z"},
        "labels": {"default": {}, "example": {"environment": "production", "region": "us-east-1", "team": "platform"}},
    }

    # Needed to populate OpenAPI metadata
    # Inlining properties in Field properties directly breaks SQLModel
    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: PydanticCoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        """Inject field-level OpenAPI metadata (readOnly, examples) into the JSON schema."""
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        props = json_schema.get("properties", {})
        for field, extras in cls.FIELD_SCHEMA_EXTRAS.items():
            if field in props:
                props[field].update(extras)
        return json_schema
