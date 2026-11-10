"""Non-consuming Kafka Subscribe connection-test response."""

from datetime import datetime
from typing import Literal

from sqlmodel import Field, SQLModel


class EventSubscriptionTestResponse(SQLModel):
    """Success proves connectivity and topic metadata only, never runtime ACLs."""

    success: bool
    checked_at: datetime
    connection: Literal["verified", "failed", "unverified"] = "unverified"
    topic_metadata: Literal["verified", "failed", "unverified"] = "unverified"
    topic_read: Literal["unverified"] = "unverified"
    group_access: Literal["unverified"] = "unverified"
    error_code: str | None = Field(default=None, description="Sanitized failure code; no broker error text")
