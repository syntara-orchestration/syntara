"""UserIdentity SQLModel for federated identity linking.

This module provides the UserIdentity model that tracks OIDC (issuer, sub) pairs
linked to platform users, enabling proper federated identity management.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel

SUBJECT_MAX_LENGTH = 1024


class UserIdentity(SQLModel, table=True):
    """Federated identity record linking an OIDC (issuer, sub) pair to a user.

    This table is exclusively for federated identities. Local users authenticate
    via password_hash on the User model and have no rows here.
    """

    __tablename__ = "user_identities"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)

    user_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )

    identity_provider_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("identity_providers.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )

    issuer: str = Field(
        max_length=2048,
        sa_type=String(2048),  # type: ignore[call-overload]
        description="OIDC issuer URL",
    )

    subject: str = Field(
        max_length=SUBJECT_MAX_LENGTH,
        sa_type=String(SUBJECT_MAX_LENGTH),  # type: ignore[call-overload]
        description="OIDC sub claim",
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="Timestamp when identity was linked",
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="Timestamp when identity was last updated",
    )

    last_used_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="Timestamp of last successful authentication via this identity",
    )

    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_user_identities_issuer_subject"),)
