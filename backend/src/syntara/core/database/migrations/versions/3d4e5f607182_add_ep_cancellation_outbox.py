"""Add durable AO-to-EP cancellation delivery state.

Revision ID: 3d4e5f607182
Revises: 2c3d4e5f6071
Create Date: 2026-10-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3d4e5f607182"
down_revision: str | Sequence[str] | None = "2c3d4e5f6071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store and retry cancellation intent independently of the request process."""
    op.add_column(
        "execution_plane_activity_bindings",
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "execution_plane_activity_bindings",
        sa.Column("cancel_delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "execution_plane_activity_bindings",
        sa.Column("cancel_next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "execution_plane_activity_bindings",
        sa.Column("cancel_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "execution_plane_activity_bindings",
        sa.Column("cancel_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "execution_plane_activity_bindings",
        sa.Column("cancel_last_error", sa.String(length=1000), nullable=True),
    )
    op.create_index(
        "ix_ep_activity_bindings_cancel_delivery",
        "execution_plane_activity_bindings",
        ["cancel_delivered_at", "cancel_next_attempt_at", "cancel_lease_expires_at"],
    )


def downgrade() -> None:
    """Remove AO-to-EP cancellation delivery state."""
    op.drop_index("ix_ep_activity_bindings_cancel_delivery", table_name="execution_plane_activity_bindings")
    op.drop_column("execution_plane_activity_bindings", "cancel_last_error")
    op.drop_column("execution_plane_activity_bindings", "cancel_attempts")
    op.drop_column("execution_plane_activity_bindings", "cancel_lease_expires_at")
    op.drop_column("execution_plane_activity_bindings", "cancel_next_attempt_at")
    op.drop_column("execution_plane_activity_bindings", "cancel_delivered_at")
    op.drop_column("execution_plane_activity_bindings", "cancel_requested_at")
