"""Add an explicit cluster_type column to clusters.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: str | Sequence[str] | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EP = "execution_plane"


def upgrade() -> None:
    """Persist Cluster type instead of inferring it from labels."""
    op.add_column(
        "clusters",
        sa.Column("cluster_type", sa.String(), nullable=False, server_default="openshift"),
        schema=EP,
    )
    op.alter_column("clusters", "cluster_type", server_default=None, schema=EP)


def downgrade() -> None:
    """Remove the explicit Cluster type column."""
    op.drop_column("clusters", "cluster_type", schema=EP)
