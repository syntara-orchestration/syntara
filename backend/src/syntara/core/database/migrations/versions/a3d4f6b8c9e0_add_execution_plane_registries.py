"""Add OpenShift integrations and Execution Plane plugin registries.

Revision ID: a3d4f6b8c9e0
Revises: e7f4a1b2c3d4
Create Date: 2026-11-18

Custom SQL adds PostgreSQL enum labels, which Alembic cannot autogenerate.
Script node labels remain on downgrade because activity rows may use them.
The integration enum is restored only when no OpenShift integrations remain.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3d4f6b8c9e0"
down_revision: str | Sequence[str] | None = "e7f4a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add integration and script types, constraints, and plugin registries."""
    # CUSTOM: Commit new enum labels before using them in the partial index.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE public.integration_type ADD VALUE IF NOT EXISTS 'openshift'")
        op.execute("ALTER TYPE public.nodetype ADD VALUE IF NOT EXISTS 'script_python'")
        op.execute("ALTER TYPE public.nodetype ADD VALUE IF NOT EXISTS 'script_bash'")
    # END CUSTOM

    op.create_index(
        "uq_integrations_single_openshift",
        "integrations",
        ["integration_type"],
        unique=True,
        postgresql_where=sa.text("integration_type = 'openshift'"),
    )
    op.create_table(
        "execution_plane_plugins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "labels", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("node_type", postgresql.ENUM(name="nodetype", create_type=False), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("step_identity", sa.String(length=255), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("image_reference", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_execution_plane_plugins"),
        sa.UniqueConstraint("node_type", name="uq_execution_plane_plugins_node_type"),
        sa.UniqueConstraint("name", name="uq_execution_plane_plugins_name"),
        sa.UniqueConstraint("step_identity", name="uq_execution_plane_plugins_step_identity"),
    )
    op.create_index("ix_execution_plane_plugins_id", "execution_plane_plugins", ["id"], unique=False)
    op.create_index("ix_execution_plane_plugins_created_at", "execution_plane_plugins", ["created_at"], unique=False)
    op.create_index("ix_execution_plane_plugins_updated_at", "execution_plane_plugins", ["updated_at"], unique=False)

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
    """Remove plugin registries and restore the integration discriminator."""
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
    op.drop_index("ix_execution_plane_plugins_updated_at", table_name="execution_plane_plugins")
    op.drop_index("ix_execution_plane_plugins_created_at", table_name="execution_plane_plugins")
    op.drop_index("ix_execution_plane_plugins_id", table_name="execution_plane_plugins")
    op.drop_table("execution_plane_plugins")
    op.drop_index("uq_integrations_single_openshift", table_name="integrations")

    # CUSTOM: PostgreSQL requires rebuilding an enum to remove a label.
    connection = op.get_bind()
    has_openshift_integration = connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM public.integrations WHERE integration_type = 'openshift')")
    ).scalar_one()
    if has_openshift_integration:
        msg = "Cannot downgrade while OpenShift integrations exist; remove them explicitly first"
        raise RuntimeError(msg)

    # PostgreSQL cannot drop an enum label in place. Rebuild the type without
    # deleting integrations of the other three types.
    op.execute(
        "CREATE TYPE public.integration_type_previous AS ENUM "
        "('mcp_server', 'llm_provider', 'ansible_automation_platform')"
    )
    op.execute(
        "ALTER TABLE public.integrations ALTER COLUMN integration_type "
        "TYPE public.integration_type_previous USING integration_type::text::public.integration_type_previous"
    )
    op.execute("DROP TYPE public.integration_type")
    op.execute("ALTER TYPE public.integration_type_previous RENAME TO integration_type")
    # END CUSTOM
