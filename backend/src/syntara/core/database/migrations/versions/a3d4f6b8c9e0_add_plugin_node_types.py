"""Add AO node types to Execution Plane plugins.

Revision ID: a3d4f6b8c9e0
Revises: b1d2e3f4a5c6
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a3d4f6b8c9e0"
down_revision: str | Sequence[str] | None = "b1d2e3f4a5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Map each seeded plugin to the AO node type that dispatches to it."""
    node_type = postgresql.ENUM(name="nodetype", create_type=False)
    # Alembic applies all revisions in one transaction. PostgreSQL requires the
    # new labels added by the preceding revision to be committed before use.
    op.execute("COMMIT")
    op.add_column(
        "execution_plane_plugins",
        sa.Column("node_type", node_type, nullable=True),
    )
    op.execute(
        """
        UPDATE execution_plane_plugins
        SET node_type = CASE name
            WHEN 'script-python' THEN 'script_python'::nodetype
            WHEN 'script-bash' THEN 'script_bash'::nodetype
        END
        WHERE name IN ('script-python', 'script-bash')
        """
    )
    op.alter_column("execution_plane_plugins", "node_type", existing_type=node_type, nullable=False)
    op.create_unique_constraint("uq_execution_plane_plugins_node_type", "execution_plane_plugins", ["node_type"])


def downgrade() -> None:
    """Remove the AO node type mapping from plugin records."""
    op.drop_constraint("uq_execution_plane_plugins_node_type", "execution_plane_plugins", type_="unique")
    op.drop_column("execution_plane_plugins", "node_type")
