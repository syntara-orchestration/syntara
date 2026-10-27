"""Original integration contract. Kafka has a separate v1 resource."""

from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID

from pydantic import ConfigDict, model_validator
from sqlmodel import Field, SQLModel

from syntara.core.constants import FieldLimits
from syntara.core.models.base.named import NamedResource
from syntara.core.models.base.query_params import BaseListParams
from syntara.core.models.base.user_owned import UserOwnedResource
from syntara.core.models.pagination import ResourcesResponse
from syntara.core.models.user_reference import UserReference, UserReferenceFieldsMixin
from syntara.integrations.models.integration import (
    InitialModelSelection,
    InitialToolSelection,
    IntegrationRefreshStatus,
    IntegrationScope,
    IntegrationStatus,
)
from syntara.integrations.models.integration_configuration import (
    IntegrationConfigurationReadTypes as IntegrationConfigurationInputTypes,
)
from syntara.integrations.models.integration_configuration import (
    IntegrationConfigurationReadTypes as IntegrationConfigurationTypes,
)

_ENABLED_DESCRIPTION = "Whether the integration is active"
_CONFIGURATION_DESCRIPTION = "Integration-specific configuration"


class IntegrationType(StrEnum):
    """Type of external integration."""

    MCP_SERVER = "mcp_server"
    LLM_PROVIDER = "llm_provider"
    ANSIBLE_AUTOMATION_PLATFORM = "ansible_automation_platform"


class IntegrationCreate(SQLModel):
    """Schema for creating a new integration."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]

    name: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        description="Human-readable name for the integration",
    )

    description: str | None = Field(
        default=None,
        max_length=FieldLimits.DESCRIPTION_MAX_LENGTH,
        description="Detailed description of the integration",
    )

    integration_type: IntegrationType = Field(description="Type of external integration")

    configuration: IntegrationConfigurationInputTypes = Field(
        description=_CONFIGURATION_DESCRIPTION,
        discriminator="integration_type",
    )

    management_credential_id: UUID | None = Field(
        default=None,
        description="Optional credential for admin operations",
    )

    enabled: bool = Field(default=True, description=_ENABLED_DESCRIPTION)

    scope: IntegrationScope = Field(
        default=IntegrationScope.GLOBAL,
        description="Visibility scope: global or project",
    )

    labels: dict[str, str] = Field(default_factory=dict, description="Key-value labels")

    discovered_tools: list[InitialToolSelection] | None = Field(
        default=None,
        max_length=200,
        description="Tools discovered during setup with enabled/disabled selections",
    )

    discovered_models: list[InitialModelSelection] | None = Field(
        default=None,
        description="Models discovered during setup with enabled/disabled selections",
    )

    @model_validator(mode="after")
    def validate_type_matches_configuration(self) -> "IntegrationCreate":
        """Ensure integration_type and configuration.integration_type agree."""
        if self.configuration.integration_type != self.integration_type.value:
            msg = (
                f"integration_type '{self.integration_type.value}' does not match "
                f"configuration.integration_type '{self.configuration.integration_type}'"
            )
            raise ValueError(msg)
        if self.discovered_tools:
            if self.integration_type != IntegrationType.MCP_SERVER:
                msg = "discovered_tools is only supported for mcp_server integrations"
                raise ValueError(msg)
            names = [t.name for t in self.discovered_tools]
            if len(names) != len(set(names)):
                msg = "discovered_tools contains duplicate tool names"
                raise ValueError(msg)
        if self.discovered_models:
            if self.integration_type != IntegrationType.LLM_PROVIDER:
                msg = "discovered_models is only supported for llm_provider integrations"
                raise ValueError(msg)
            model_ids = [m.model_id for m in self.discovered_models]
            if len(model_ids) != len(set(model_ids)):
                msg = "discovered_models contains duplicate model IDs"
                raise ValueError(msg)
            default_count = sum(1 for m in self.discovered_models if m.is_default)
            if default_count > 1:
                msg = "discovered_models contains multiple default models; at most one is allowed"
                raise ValueError(msg)
        return self


class IntegrationRead(UserReferenceFieldsMixin, NamedResource, UserOwnedResource):
    """Schema for integration API responses."""

    created_by: UserReference | UUID | str | None = Field(default=None, description="User who created the integration")  # type: ignore[assignment]
    updated_by: UserReference | UUID | str | None = Field(
        default=None, description="User who last modified the integration"
    )  # type: ignore[assignment]

    FIELD_SCHEMA_EXTRAS: ClassVar[dict[str, Any]] = {
        **NamedResource.FIELD_SCHEMA_EXTRAS,
        **UserOwnedResource.FIELD_SCHEMA_EXTRAS,
    }

    integration_type: IntegrationType
    enabled: bool = True
    validation_status: IntegrationStatus = IntegrationStatus.UNKNOWN
    scope: IntegrationScope = IntegrationScope.GLOBAL
    configuration: IntegrationConfigurationTypes = Field(
        description=_CONFIGURATION_DESCRIPTION, discriminator="integration_type"
    )
    management_credential_id: UUID | None = None
    last_validated_at: datetime | None = None
    validation_error: str | None = None
    refresh_status: IntegrationRefreshStatus | None = None
    last_refreshed_at: datetime | None = None
    last_successful_refresh_at: datetime | None = None
    refresh_error: str | None = None
    project_ids: list[UUID] = Field(
        default_factory=list,
        description="IDs of projects this integration is assigned to (empty for global scope)",
    )
    total_tool_count: int = Field(default=0, description="Total number of tools linked to this integration")
    enabled_tool_count: int = Field(default=0, description="Number of enabled tools linked to this integration")
    total_model_count: int = Field(default=0, description="Total number of models linked to this integration")
    enabled_model_count: int = Field(default=0, description="Number of enabled models linked to this integration")


class IntegrationUpdate(SQLModel):
    """Schema for partially updating an integration (user-facing)."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        description="Human-readable name for the integration",
    )

    description: str | None = Field(
        default=None,
        max_length=FieldLimits.DESCRIPTION_MAX_LENGTH,
        description="Detailed description of the integration",
    )

    configuration: IntegrationConfigurationInputTypes | None = Field(
        default=None,
        description=_CONFIGURATION_DESCRIPTION,
        discriminator="integration_type",
    )

    management_credential_id: UUID | None = Field(default=None, description="Optional credential for admin operations")

    enabled: bool | None = Field(default=None, description=_ENABLED_DESCRIPTION)

    scope: IntegrationScope | None = Field(default=None, description="Visibility scope: global or project")

    labels: dict[str, str] | None = Field(default=None, description="Key-value labels")

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]


class IntegrationTestConnection(SQLModel):
    """Schema for testing a connection without saving an integration."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]

    integration_type: IntegrationType = Field(description="Type of external integration")

    configuration: IntegrationConfigurationInputTypes = Field(
        description=_CONFIGURATION_DESCRIPTION,
        discriminator="integration_type",
    )

    credential_id: UUID | None = Field(default=None, description="Credential to use for the connection test")

    @model_validator(mode="after")
    def validate_type_matches_configuration(self) -> "IntegrationTestConnection":
        """Ensure integration_type and configuration.integration_type agree."""
        if self.configuration.integration_type != self.integration_type.value:
            msg = (
                f"integration_type '{self.integration_type.value}' does not match "
                f"configuration.integration_type '{self.configuration.integration_type}'"
            )
            raise ValueError(msg)
        return self


class IntegrationListResponse(ResourcesResponse[IntegrationRead]):
    """Paginated list response for integrations."""


class IntegrationListParams(BaseListParams):
    """Query parameters for integration list endpoint."""

    integration_type: IntegrationType | None = Field(default=None, description="Filter by integration type")
    validation_status: IntegrationStatus | None = Field(default=None, description="Filter by validation status")
    enabled: bool | None = Field(default=None, description="Filter by enabled status")
    scope: IntegrationScope | None = Field(default=None, description="Filter by visibility scope")
    management_credential_id: UUID | None = Field(default=None, description="Filter by management credential ID")
    project_id: UUID | None = Field(
        default=None,
        description="Filter to integrations that are global or assigned to this project. "
        "Restricted to projects the user has RBAC access to; querying inaccessible projects "
        "returns only global integrations.",
    )
