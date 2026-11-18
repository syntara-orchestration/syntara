"""Add Execution Plane IntegrationType and CredentialRecipe registries.

Revision ID: b1d2e3f4a5c6
Revises: fc1f70c3fcc6
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b1d2e3f4a5c6"
down_revision: str | Sequence[str] | None = "fc1f70c3fcc6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add storage for managed plugin target manifests."""
    op.create_table(
        "execution_plane_integration_types",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "labels", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("integration_type_id", sa.String(length=255), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_execution_plane_integration_types"),
        sa.UniqueConstraint("integration_type_id", name="uq_execution_plane_integration_type_id"),
    )
    op.create_index(
        "ix_execution_plane_integration_types_id", "execution_plane_integration_types", ["id"], unique=False
    )
    op.create_index(
        "ix_execution_plane_integration_types_created_at",
        "execution_plane_integration_types",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_execution_plane_integration_types_updated_at",
        "execution_plane_integration_types",
        ["updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_execution_plane_integration_types_integration_type_id",
        "execution_plane_integration_types",
        ["integration_type_id"],
        unique=False,
    )

    op.create_table(
        "execution_plane_credential_recipes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "labels", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("credential_recipe_id", sa.String(length=255), nullable=False),
        sa.Column("integration_type_id", sa.String(length=255), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["integration_type_id"],
            ["execution_plane_integration_types.integration_type_id"],
            name="fk_execution_plane_credential_recipes_integration_type",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_execution_plane_credential_recipes"),
        sa.UniqueConstraint("credential_recipe_id", name="uq_execution_plane_credential_recipe_id"),
    )
    op.create_index(
        "ix_execution_plane_credential_recipes_id", "execution_plane_credential_recipes", ["id"], unique=False
    )
    op.create_index(
        "ix_execution_plane_credential_recipes_created_at",
        "execution_plane_credential_recipes",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_execution_plane_credential_recipes_updated_at",
        "execution_plane_credential_recipes",
        ["updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_execution_plane_credential_recipes_credential_recipe_id",
        "execution_plane_credential_recipes",
        ["credential_recipe_id"],
        unique=False,
    )
    op.create_index(
        "ix_execution_plane_credential_recipes_integration_type_id",
        "execution_plane_credential_recipes",
        ["integration_type_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the managed plugin target manifest tables."""
    op.drop_index(
        "ix_execution_plane_credential_recipes_integration_type_id",
        table_name="execution_plane_credential_recipes",
    )
    op.drop_index(
        "ix_execution_plane_credential_recipes_credential_recipe_id",
        table_name="execution_plane_credential_recipes",
    )
    op.drop_index("ix_execution_plane_credential_recipes_updated_at", table_name="execution_plane_credential_recipes")
    op.drop_index("ix_execution_plane_credential_recipes_created_at", table_name="execution_plane_credential_recipes")
    op.drop_index("ix_execution_plane_credential_recipes_id", table_name="execution_plane_credential_recipes")
    op.drop_table("execution_plane_credential_recipes")
    op.drop_index(
        "ix_execution_plane_integration_types_integration_type_id",
        table_name="execution_plane_integration_types",
    )
    op.drop_index("ix_execution_plane_integration_types_updated_at", table_name="execution_plane_integration_types")
    op.drop_index("ix_execution_plane_integration_types_created_at", table_name="execution_plane_integration_types")
    op.drop_index("ix_execution_plane_integration_types_id", table_name="execution_plane_integration_types")
    op.drop_table("execution_plane_integration_types")
