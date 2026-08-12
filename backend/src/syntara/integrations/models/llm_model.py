"""LLM Model storage for LLM provider integrations.

Stores models discovered from LLM providers. Models that disappear
from a provider are kept (not deleted) to preserve referential
integrity. The ``enabled`` flag is admin-controlled only; discovery
never toggles it.
"""

from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from pydantic import ConfigDict, model_validator
from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, DateTime, Field, SQLModel

from syntara.core.constants import FieldLimits
from syntara.core.models.base import BaseListParams, BaseResource
from syntara.core.models.pagination import ResourcesResponse


class ModelCapabilityProfile(SQLModel):
    """Typed view of an LLM model's capability profile."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")  # type: ignore[assignment]

    # Metadata
    name: str | None = None
    status: str | None = None
    release_date: str | None = None
    last_updated: str | None = None
    open_weights: bool | None = None

    # Input constraints
    max_input_tokens: int | None = None
    text_inputs: bool | None = None
    image_inputs: bool | None = None
    image_url_inputs: bool | None = None
    pdf_inputs: bool | None = None
    audio_inputs: bool | None = None
    video_inputs: bool | None = None
    image_tool_message: bool | None = None
    pdf_tool_message: bool | None = None

    # Output constraints
    max_output_tokens: int | None = None
    reasoning_output: bool | None = None
    text_outputs: bool | None = None
    image_outputs: bool | None = None
    audio_outputs: bool | None = None
    video_outputs: bool | None = None

    # Tool calling
    tool_calling: bool | None = None
    tool_choice: bool | None = None
    tool_call_streaming: bool | None = None

    # Other
    structured_output: bool | None = None
    attachment: bool | None = None
    temperature: bool | None = None


class LLMModel(BaseResource, table=True):
    """An LLM model discovered from a provider integration."""

    __tablename__ = "llm_models"

    __filterable_fields__: ClassVar[list[str]] = [
        *BaseResource.__filterable_fields__,
        "enabled",
        "is_default",
        "integration_id",
        "model_id",
    ]

    __sortable_fields__: ClassVar[list[str]] = [
        *BaseResource.__sortable_fields__,
        "model_id",
        "name",
        "enabled",
    ]

    integration_id: UUID = Field(
        foreign_key="integrations.id",
        index=True,
        ondelete="CASCADE",
        description="Integration this model was discovered from",
    )

    model_id: str = Field(
        max_length=FieldLimits.NAME_MAX_LENGTH,
        description="Provider model identifier (e.g. gpt-4o, claude-opus-4-6)",
    )

    name: str = Field(
        max_length=FieldLimits.NAME_MAX_LENGTH,
        description="Human-readable display name",
    )

    description: str | None = Field(
        default=None,
        max_length=FieldLimits.DESCRIPTION_MAX_LENGTH,
        description="Model description from the provider",
    )

    enabled: bool = Field(default=True, index=True, description="Whether this model is enabled for use")

    is_default: bool = Field(default=False, description="Whether this is the default model for the integration")

    last_refreshed_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="Last time this model was synced from the provider",
    )

    profile: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
        description="Model capability profile",
    )

    __table_args__ = (
        UniqueConstraint("integration_id", "model_id", name="uq_llm_models_integration_model"),
        Index("ix_llm_models_integration_id_created_at_id", "integration_id", "created_at", "id"),
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    @property
    def capability_profile(self) -> ModelCapabilityProfile | None:
        """Parse the raw profile JSONB into a typed ``ModelCapabilityProfile``."""
        if self.profile is None or len(self.profile) == 0:
            return None
        return ModelCapabilityProfile.model_validate(self.profile)


# ============================================================================
# API Request/Response Schemas
# ============================================================================


class LLMModelRead(SQLModel):
    """Schema for LLM model API responses."""

    id: UUID
    integration_id: UUID
    model_id: str
    name: str
    description: str | None = None
    enabled: bool = True
    is_default: bool = False
    last_refreshed_at: datetime | None = None
    profile: ModelCapabilityProfile | None = Field(
        default=None,
        description="Model capability profile",
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LLMModelUpdate(SQLModel):
    """Schema for updating an LLM model (enable/disable, set as default)."""

    enabled: bool | None = None
    is_default: bool | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "LLMModelUpdate":
        """Reject empty update payloads."""
        if self.enabled is None and self.is_default is None:
            msg = "At least one field must be provided"
            raise ValueError(msg)
        return self


class LLMModelBulkUpdate(SQLModel):
    """Schema for bulk-updating LLM models."""

    model_ids: list[UUID] = Field(
        description="Model IDs to update",
    )
    enabled: bool = Field(description="New enabled state")


class LLMModelBulkUpdateResponse(SQLModel):
    """Response for bulk LLM model update."""

    updated_count: int = Field(description="Number of models updated")
    skipped_count: int = Field(description="Number of model IDs not found in integration")
    updated_at: datetime = Field(description="Timestamp of the update")


class LLMModelListParams(BaseListParams):
    """Query parameters for LLM model list endpoint."""

    sort: str | None = Field(
        default=None,
        description="Sort parameter (e.g., 'name', '-created_at')",
        schema_extra={"pattern": r"^-?[a-z][a-z0-9_]*$"},
    )


class LLMModelListResponse(ResourcesResponse[LLMModelRead]):
    """Paginated response for LLM models."""
