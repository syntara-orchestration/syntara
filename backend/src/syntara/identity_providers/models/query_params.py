"""Query parameter models for identity provider endpoints."""

from sqlmodel import Field

from syntara.core.models.base import BaseListParams


class IdentityProviderListParams(BaseListParams):
    """Query parameters for identity provider list endpoint."""

    limit: int = Field(default=20, gt=0, le=100, description="Maximum number of results per page")
