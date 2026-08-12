"""GlobalRevocationTimestamp singleton model.

Stores the system-wide token revocation timestamp. All tokens whose
``iat`` (issued-at) claim precedes this timestamp are rejected.

A ``is_singleton`` column with UNIQUE + CHECK constraints guarantees
that at most one row can ever exist in the table (same pattern as
:class:`~syntara.core.models.installation.Installation`).
"""

from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Boolean, CheckConstraint, Column, DateTime, Field, SQLModel, UniqueConstraint, text


class GlobalRevocationTimestamp(SQLModel, table=True):
    """Singleton record holding the global token revocation timestamp.

    Updated by the admin CLI (``syntara.admin revoke-all-sessions``).
    Read on every authenticated request to reject pre-revocation tokens.

    The ``is_singleton`` column enforces the single-row invariant at the
    database level: its CHECK constraint pins the value to ``True`` and
    its UNIQUE constraint prevents a second row.

    Attributes:
        id: Fixed primary key (always 1).
        revoked_before: Tokens issued before this UTC timestamp are invalid.
        updated_at: When the revocation timestamp was last changed.
        is_singleton: Guard column — always True, unique, enforcing one row.

    """

    __tablename__ = "global_revocation_timestamp"
    __table_args__ = (
        UniqueConstraint("is_singleton"),
        CheckConstraint("is_singleton = true", name="ck_global_revocation_singleton"),
    )

    id: int = Field(default=1, primary_key=True)
    revoked_before: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="Tokens issued before this UTC timestamp are invalid",
    )
    updated_at: datetime = Field(
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        sa_column_kwargs={"server_default": text("now()")},
        description="When the revocation timestamp was last changed",
    )
    updated_by: str | None = Field(
        default=None,
        description="Username of the actor who last set the revocation timestamp",
    )
    is_singleton: bool = Field(
        default=True,
        sa_column=Column(
            Boolean,
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
