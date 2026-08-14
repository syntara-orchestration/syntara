"""Query parameter models for integration endpoints."""

from uuid import UUID

from sqlmodel import Field

from syntara.core.models.base import BaseListParams


class IntegrationListParams(BaseListParams):
    """Query parameters for integration list endpoint."""

    project_id: UUID | None = Field(
        default=None,
        description="Filter to integrations that are global or assigned to this project. "
        "Restricted to projects the user has RBAC access to; querying inaccessible projects "
        "returns only global integrations.",
    )
