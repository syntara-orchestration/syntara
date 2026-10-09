"""Add AO-owned integration synchronization state and outbox.

Revision ID: 2c3d4e5f6071
Revises: 1b2c3d4e5f60
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2c3d4e5f6071"
down_revision: str | Sequence[str] | None = "8fe7495a14dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist synchronization status and transactional desired-state delivery."""
    op.add_column("integrations", sa.Column("execution_plane_status", sa.String(length=32), nullable=True))
    op.add_column(
        "integrations",
        sa.Column("execution_plane_revision", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("integrations", sa.Column("execution_plane_error", sa.Text(), nullable=True))
    op.create_table(
        "execution_plane_integration_sync",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("integration_id", sa.UUID(), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("endpoint", sa.String(length=2048), nullable=False),
        sa.Column("namespace", sa.String(length=63), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("integration_id", "source_revision", name="uq_ep_integration_sync_revision"),
    )
    op.create_index(
        "ix_ep_integration_sync_delivery",
        "execution_plane_integration_sync",
        ["processed_at", "next_attempt_at", "lease_expires_at"],
    )


def downgrade() -> None:
    """Remove the integration sync outbox and status fields."""
    op.drop_index("ix_ep_integration_sync_delivery", table_name="execution_plane_integration_sync")
    op.drop_table("execution_plane_integration_sync")
    op.drop_column("integrations", "execution_plane_error")
    op.drop_column("integrations", "execution_plane_revision")
    op.drop_column("integrations", "execution_plane_status")
