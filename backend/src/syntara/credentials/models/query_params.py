"""Query parameter models for credential list endpoints."""

from typing import Literal
from uuid import UUID

from sqlmodel import Field

from syntara.core.models.base import BaseListParams


class CredentialListParams(BaseListParams):
    """Query parameters for listing credentials."""

    credential_type_id: UUID | None = Field(default=None, description="Filter by credential type ID")
    enabled: bool | None = Field(default=None, description="Filter by enabled status")
    for_action: Literal["use"] | None = Field(default=None, description="When 'use', returns only usable credentials.")
