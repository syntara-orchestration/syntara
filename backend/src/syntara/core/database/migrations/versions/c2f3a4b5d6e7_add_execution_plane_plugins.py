"""Add the database-backed Execution Plane plugin registry.

Revision ID: c2f3a4b5d6e7
Revises: e2f6a8c1d4b7
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c2f3a4b5d6e7"
down_revision: str | Sequence[str] | None = "e2f6a8c1d4b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add storage for managed Action manifests and images."""
    op.create_table(
        "execution_plane_plugins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "labels", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("step_identity", sa.String(length=255), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("image_reference", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_execution_plane_plugins"),
        sa.UniqueConstraint("name", name="uq_execution_plane_plugins_name"),
        sa.UniqueConstraint("step_identity", name="uq_execution_plane_plugins_step_identity"),
    )
    op.create_index("ix_execution_plane_plugins_id", "execution_plane_plugins", ["id"], unique=False)
    op.create_index("ix_execution_plane_plugins_created_at", "execution_plane_plugins", ["created_at"], unique=False)
    op.create_index("ix_execution_plane_plugins_updated_at", "execution_plane_plugins", ["updated_at"], unique=False)


def downgrade() -> None:
    """Drop the plugin registry table; PostgreSQL enum values remain append-only."""
    op.drop_index("ix_execution_plane_plugins_updated_at", table_name="execution_plane_plugins")
    op.drop_index("ix_execution_plane_plugins_created_at", table_name="execution_plane_plugins")
    op.drop_index("ix_execution_plane_plugins_id", table_name="execution_plane_plugins")
    op.drop_table("execution_plane_plugins")
