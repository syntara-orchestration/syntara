"""initial execution_plane schema

Revision ID: 9f3e1a2b4c7d
Revises:
Create Date: 2026-09-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "9f3e1a2b4c7d"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EP = "execution_plane"


def upgrade() -> None:
    """Create execution target and work item tables."""
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {EP}")

    op.create_table(
        "execution_targets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("backend_type", sa.String(), nullable=False),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("labels", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_ran_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        schema=EP,
    )
    op.create_index("ix_execution_targets_name", "execution_targets", ["name"], schema=EP)

    op.create_table(
        "work_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("work_correlation_id", sa.UUID(), nullable=False),
        sa.Column("activity_handle", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("execution_target_id", sa.UUID(), nullable=True),
        sa.Column("payload", JSONB(), nullable=False, server_default="{}"),
        sa.Column("result", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signaled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["execution_target_id"],
            [f"{EP}.execution_targets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=EP,
    )
    op.create_index("ix_work_items_work_correlation_id", "work_items", ["work_correlation_id"], schema=EP)
    op.create_index("ix_work_items_status", "work_items", ["status"], schema=EP)

    # Partial index for the hot claiming path: SELECT ... FOR UPDATE SKIP LOCKED
    # WHERE status = 'pending' ORDER BY created_at.
    op.execute(
        f"""
        CREATE INDEX ix_work_items_pending
        ON {EP}.work_items (created_at)
        WHERE status = 'pending'
        """
    )


def downgrade() -> None:
    """Remove execution target and work item tables."""
    op.execute(f"DROP INDEX IF EXISTS {EP}.ix_work_items_pending")
    op.drop_table("work_items", schema=EP)
    op.drop_table("execution_targets", schema=EP)
    # The Alembic environment owns the schema and its version table. Keep both
    # available so Alembic can record the downgrade and later upgrade again.
