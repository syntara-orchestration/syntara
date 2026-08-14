"""rename nexus_group_id to mapped_group_id in idp_group_mapping_entries

Revision ID: 4ca3cbf8652a
Revises: b69ef9067e66
Create Date: 2026-08-06 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4ca3cbf8652a"
down_revision: str | Sequence[str] | None = "b69ef9067e66"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # CUSTOM: column rename not detected by autogenerate
    op.alter_column("idp_group_mapping_entries", "nexus_group_id", new_column_name="mapped_group_id")
    # END CUSTOM

    # CUSTOM: drop and recreate index with updated column name
    op.drop_index("ix_idp_group_mapping_entries_nexus_group_id", table_name="idp_group_mapping_entries")
    op.create_index(
        op.f("ix_idp_group_mapping_entries_mapped_group_id"),
        "idp_group_mapping_entries",
        ["mapped_group_id"],
    )
    # END CUSTOM

    # CUSTOM: drop and recreate unique constraint with updated column list
    op.drop_constraint("uq_idp_group_mapping_provider_value_group", "idp_group_mapping_entries", type_="unique")
    op.create_unique_constraint(
        "uq_idp_group_mapping_provider_value_group",
        "idp_group_mapping_entries",
        ["identity_provider_id", "idp_group_value", "mapped_group_id"],
    )
    # END CUSTOM


def downgrade() -> None:
    """Downgrade schema."""
    # CUSTOM: drop constraints/indexes referencing mapped_group_id before renaming column back
    op.drop_constraint("uq_idp_group_mapping_provider_value_group", "idp_group_mapping_entries", type_="unique")
    op.drop_index("ix_idp_group_mapping_entries_mapped_group_id", table_name="idp_group_mapping_entries")
    # END CUSTOM

    # CUSTOM: rename column back first so recreated index/constraint reference the correct name
    op.alter_column("idp_group_mapping_entries", "mapped_group_id", new_column_name="nexus_group_id")
    # END CUSTOM

    # CUSTOM: recreate index and constraint using the restored column name
    op.create_index(
        op.f("ix_idp_group_mapping_entries_nexus_group_id"),
        "idp_group_mapping_entries",
        ["nexus_group_id"],
    )
    op.create_unique_constraint(
        "uq_idp_group_mapping_provider_value_group",
        "idp_group_mapping_entries",
        ["identity_provider_id", "idp_group_value", "nexus_group_id"],
    )
    # END CUSTOM
