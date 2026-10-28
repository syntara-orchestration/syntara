"""Original integration contract. Kafka has a separate v1 resource."""

from enum import StrEnum
from uuid import UUID

from pydantic import model_validator
from sqlmodel import Field

from syntara.core.models.base.query_params import BaseListParams
from syntara.core.models.pagination import ResourcesResponse
from syntara.integrations.models.integration import (
    IntegrationCreateBase,
    IntegrationReadBase,
    IntegrationScope,
    IntegrationStatus,
    IntegrationTestConnectionBase,
    IntegrationUpdateBase,
    validate_configuration_type,
)
from syntara.integrations.models.integration_configuration import (
    IntegrationConfigurationReadTypes as IntegrationConfigurationInputTypes,
)
from syntara.integrations.models.integration_configuration import (
    IntegrationConfigurationReadTypes as IntegrationConfigurationTypes,
)

_CONFIGURATION_DESCRIPTION = "Integration-specific configuration"


class IntegrationType(StrEnum):
    """Type of external integration."""

    MCP_SERVER = "mcp_server"
    LLM_PROVIDER = "llm_provider"
    ANSIBLE_AUTOMATION_PLATFORM = "ansible_automation_platform"


class IntegrationCreate(IntegrationCreateBase):
    """Schema for creating a new integration."""

    integration_type: IntegrationType = Field(description="Type of external integration")
    configuration: IntegrationConfigurationInputTypes = Field(
        description=_CONFIGURATION_DESCRIPTION,
        discriminator="integration_type",
    )

    @model_validator(mode="after")
    def validate_type_matches_configuration(self) -> "IntegrationCreate":
        """Ensure integration_type and configuration.integration_type agree."""
        self.validate_discovery_selection(self.integration_type.value, self.configuration.integration_type)
        return self


class IntegrationRead(IntegrationReadBase):
    """Schema for integration API responses."""

    integration_type: IntegrationType
    configuration: IntegrationConfigurationTypes = Field(
        description=_CONFIGURATION_DESCRIPTION, discriminator="integration_type"
    )


class IntegrationUpdate(IntegrationUpdateBase):
    """Schema for partially updating an integration (user-facing)."""

    configuration: IntegrationConfigurationInputTypes | None = Field(
        default=None,
        description=_CONFIGURATION_DESCRIPTION,
        discriminator="integration_type",
    )


class IntegrationTestConnection(IntegrationTestConnectionBase):
    """Schema for testing a connection without saving an integration."""

    integration_type: IntegrationType = Field(description="Type of external integration")

    configuration: IntegrationConfigurationInputTypes = Field(
        description=_CONFIGURATION_DESCRIPTION,
        discriminator="integration_type",
    )

    @model_validator(mode="after")
    def validate_type_matches_configuration(self) -> "IntegrationTestConnection":
        """Ensure integration_type and configuration.integration_type agree."""
        validate_configuration_type(self.integration_type.value, self.configuration.integration_type)
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
