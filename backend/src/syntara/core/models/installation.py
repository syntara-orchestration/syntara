"""Installation model for unique deployment identification.

This module provides the Installation model — a system-internal singleton
that persists a unique UUID identifying this Nexus deployment.  The record
is created once by an Alembic migration and read at runtime by the
telemetry subsystem.

A ``is_singleton`` column with a UNIQUE + CHECK constraint guarantees that
at most one row can ever exist in the table.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Boolean, CheckConstraint, Column, DateTime, Field, SQLModel, UniqueConstraint, text


class Installation(SQLModel, table=True):
    """Singleton record representing a Nexus deployment.

    Created during database migration.  Read-only from application code.

    The ``is_singleton`` column enforces the single-row invariant at the
    database level: its CHECK constraint pins the value to ``True`` and
    its UNIQUE constraint prevents a second row.

    Attributes:
        id: Unique installation identifier (UUID v4).
        created_at: Timestamp of installation record creation.
        is_singleton: Guard column — always True, unique, enforcing one row.
        salt: Cryptographically random salt used as the HMAC key for
            anonymizing user IDs in telemetry events.

    """

    __tablename__ = "installation"
    __table_args__ = (
        UniqueConstraint("is_singleton"),
        CheckConstraint("is_singleton = true", name="ck_installation_singleton"),
    )

    id: uuid.UUID = Field(primary_key=True)
    created_at: datetime = Field(
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        sa_column_kwargs={"server_default": text("now()")},
    )
    is_singleton: bool = Field(
        default=True,
        sa_column=Column(
            Boolean,
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    salt: uuid.UUID = Field(
        sa_column=Column(
            sa.Uuid,
            nullable=False,
        ),
    )
