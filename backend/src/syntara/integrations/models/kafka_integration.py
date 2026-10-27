"""Kafka-specific v1 request and response schemas."""

from typing import ClassVar, Literal
from uuid import UUID

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel

from syntara.core.constants import FieldLimits
from syntara.core.models.base.query_params import BaseListParams
from syntara.core.models.pagination import ResourcesResponse
from syntara.integrations.models.integration import IntegrationReadBase, IntegrationScope, IntegrationStatus
from syntara.integrations.models.integration_configuration import KafkaConfiguration


class KafkaIntegrationCreate(SQLModel):
    """Create a Kafka connection without extending the original integration union."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]
    name: str = Field(min_length=1, max_length=FieldLimits.NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=FieldLimits.DESCRIPTION_MAX_LENGTH)
    integration_type: Literal["kafka"] = "kafka"
    configuration: KafkaConfiguration
    management_credential_id: UUID | None = None
    enabled: bool = True
    scope: IntegrationScope = IntegrationScope.GLOBAL
    labels: dict[str, str] = Field(default_factory=dict)


class KafkaIntegrationUpdate(SQLModel):
    """Patch Kafka settings, preserving omitted fields."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]
    name: str | None = Field(default=None, min_length=1, max_length=FieldLimits.NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=FieldLimits.DESCRIPTION_MAX_LENGTH)
    configuration: KafkaConfiguration | None = None
    management_credential_id: UUID | None = None
    enabled: bool | None = None
    scope: IntegrationScope | None = None
    labels: dict[str, str] | None = None


class KafkaIntegrationRead(IntegrationReadBase):
    """Kafka connection with its broker settings in configuration."""

    integration_type: Literal["kafka"]
    configuration: KafkaConfiguration


class KafkaIntegrationListResponse(ResourcesResponse[KafkaIntegrationRead]):
    """Paginated Kafka-only results."""


class KafkaIntegrationTestConnection(SQLModel):
    """Test a Kafka connection without persisting it."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]
    integration_type: Literal["kafka"] = "kafka"
    configuration: KafkaConfiguration
    credential_id: UUID | None = None


class KafkaIntegrationListParams(BaseListParams):
    """Query parameters for integration list endpoint."""

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
