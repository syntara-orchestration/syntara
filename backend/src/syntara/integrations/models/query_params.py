"""Query parameter models for integration endpoints."""

from uuid import UUID

from sqlmodel import Field

from syntara.core.models.base import BaseListParams
from syntara.integrations.models.integration import (
    IntegrationScope,
    IntegrationStatus,
    IntegrationType,
)


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
