"""Response schemas for admin revocation endpoints."""

from datetime import datetime

from sqlmodel import SQLModel


class GlobalRevocationTimestampRead(SQLModel):
    """Response schema for reading the global revocation timestamp."""

    revoked_before: datetime | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None


class RevocationResponse(SQLModel):
    """Response schema for revocation operations."""

    message: str
    sessions_revoked: int | None = None
