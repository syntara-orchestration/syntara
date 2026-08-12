"""UserIdentity API request/response schemas."""

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from pydantic import ConfigDict
from sqlmodel import SQLModel

from syntara.core.models.pagination import ResourcesResponse


class UserIdentityRead(SQLModel):
    """Schema for user identity response."""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    id: UUID
    user_id: UUID
    identity_provider_id: UUID
    issuer: str
    subject: str
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None
    provider_name: str = ""


class UserIdentityListResponse(ResourcesResponse[UserIdentityRead]):
    """Paginated list of user identities."""


class UserIdentityAttach(SQLModel):
    """Schema for attaching an identity to a user."""

    identity_id: UUID
