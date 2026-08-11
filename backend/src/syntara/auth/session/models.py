"""SQLModel for refresh session storage in PostgreSQL."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import JSON, Column, DateTime, Field, SQLModel

_ACTIVE_SESSION_FILTER = text("revoked_at IS NULL")


class RefreshSession(SQLModel, table=True):
    """Refresh token session stored in PostgreSQL.

    Sessions are soft-revoked (revoked_at is set) and physically deleted
    by the periodic cleanup worker.
    """

    __tablename__ = "refresh_sessions"

    jti: str = Field(
        sa_type=String(64),  # type: ignore[call-overload]
        primary_key=True,
    )
    user_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    issued_at: datetime = Field(sa_type=DateTime(timezone=True))  # type: ignore[call-overload]
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))  # type: ignore[call-overload]
    revoked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]

    device: str | None = Field(default=None, sa_type=String(512))  # type: ignore[call-overload]
    ip_address: str | None = Field(default=None, sa_type=String(45))  # type: ignore[call-overload]
    amr: list[str] | None = Field(default=None, sa_column=Column(JSON))
    idp: str | None = Field(default=None, sa_type=String(255))  # type: ignore[call-overload]
    idp_id: str | None = Field(default=None, sa_type=String(36))  # type: ignore[call-overload]
    identity_id: str | None = Field(default=None, sa_type=String(36))  # type: ignore[call-overload]
    issuer: str | None = Field(default=None, sa_type=String(2048))  # type: ignore[call-overload]
    subject: str | None = Field(default=None, sa_type=String(1024))  # type: ignore[call-overload]
    id_token_hint: str | None = Field(default=None, sa_type=String(4096))  # type: ignore[call-overload]
    rp_logout_enabled: bool = Field(default=False)

    __table_args__ = (
        Index(
            "ix_refresh_sessions_user_id",
            "user_id",
            postgresql_where=_ACTIVE_SESSION_FILTER,
        ),
        Index(
            "ix_refresh_sessions_idp_id",
            "idp_id",
            postgresql_where=_ACTIVE_SESSION_FILTER,
        ),
        Index(
            "ix_refresh_sessions_identity_id",
            "identity_id",
            postgresql_where=_ACTIVE_SESSION_FILTER,
        ),
        Index("ix_refresh_sessions_expires_at", "expires_at"),
    )
