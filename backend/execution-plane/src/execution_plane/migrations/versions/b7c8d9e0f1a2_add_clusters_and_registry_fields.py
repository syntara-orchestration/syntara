"""Add clusters and Cluster-owned ExecutionTarget fields.

Revision ID: b7c8d9e0f1a2
Revises: 9f3e1a2b4c7d
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "b7c8d9e0f1a2"
down_revision: str | Sequence[str] | None = "9f3e1a2b4c7d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EP = "execution_plane"
EMPTY_TARGETS_MESSAGE = "execution_plane.execution_targets must be empty for this migration"
DUPLICATE_TARGET_NAMES_MESSAGE = (
    "execution_plane.execution_targets contains duplicate names; resolve them before downgrading this migration"
)


def _require_empty_execution_targets() -> None:
    """Require the green-field target table before adding mandatory fields."""
    if op.get_bind().execute(sa.text("SELECT 1 FROM execution_plane.execution_targets LIMIT 1")).first() is not None:
        raise RuntimeError(EMPTY_TARGETS_MESSAGE)


def _require_unique_target_names_for_downgrade() -> None:
    """Prevent downgrade from restoring a global name constraint over duplicates."""
    duplicate = (
        op.get_bind()
        .execute(
            sa.text("SELECT name FROM execution_plane.execution_targets GROUP BY name HAVING COUNT(*) > 1 LIMIT 1")
        )
        .first()
    )
    if duplicate is not None:
        raise RuntimeError(DUPLICATE_TARGET_NAMES_MESSAGE)


def upgrade() -> None:
    """Create clusters and add Cluster ownership to execution targets."""
    _require_empty_execution_targets()
    op.create_table(
        "clusters",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("status_message", sa.String(), nullable=True),
        sa.Column("labels", JSONB(), nullable=False, server_default="{}"),
        sa.Column("api_key", sa.String(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.UUID(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="clusters_name_key"),
        sa.UniqueConstraint("endpoint", name="clusters_endpoint_key"),
        schema=EP,
    )
    op.add_column(
        "execution_targets",
        sa.Column("cluster_id", sa.UUID(), nullable=False),
        schema=EP,
    )
    op.add_column(
        "execution_targets",
        sa.Column("is_default", sa.Boolean(), nullable=False),
        schema=EP,
    )
    op.add_column("execution_targets", sa.Column("api_key", sa.String(), nullable=False), schema=EP)
    op.add_column("execution_targets", sa.Column("status_message", sa.String(), nullable=True), schema=EP)
    op.add_column("execution_targets", sa.Column("created_by", sa.UUID(), nullable=False), schema=EP)
    op.add_column("execution_targets", sa.Column("updated_by", sa.UUID(), nullable=False), schema=EP)
    op.add_column(
        "execution_targets",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema=EP,
    )
    op.drop_constraint("execution_targets_name_key", "execution_targets", schema=EP, type_="unique")
    op.create_unique_constraint(
        "execution_targets_cluster_name_key",
        "execution_targets",
        ["cluster_id", "name"],
        schema=EP,
    )
    op.create_index(
        "uq_execution_targets_default_cluster",
        "execution_targets",
        ["cluster_id"],
        unique=True,
        schema=EP,
        postgresql_where=sa.text("is_default = true"),
    )
    op.create_foreign_key(
        "execution_targets_cluster_id_fkey",
        "execution_targets",
        "clusters",
        ["cluster_id"],
        ["id"],
        source_schema=EP,
        referent_schema=EP,
    )


def downgrade() -> None:
    """Remove Cluster ownership and the clusters table."""
    _require_unique_target_names_for_downgrade()
    op.drop_index("uq_execution_targets_default_cluster", table_name="execution_targets", schema=EP)
    op.drop_constraint("execution_targets_cluster_name_key", "execution_targets", schema=EP, type_="unique")
    op.create_unique_constraint("execution_targets_name_key", "execution_targets", ["name"], schema=EP)
    op.drop_constraint(
        "execution_targets_cluster_id_fkey",
        "execution_targets",
        schema=EP,
        type_="foreignkey",
    )
    for column_name in (
        "updated_at",
        "updated_by",
        "created_by",
        "status_message",
        "api_key",
        "is_default",
        "cluster_id",
    ):
        op.drop_column("execution_targets", column_name, schema=EP)
    op.drop_table("clusters", schema=EP)
