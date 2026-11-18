"""Add Python and Bash script node values to the node type enum.

Revision ID: fc1f70c3fcc6
Revises: c2f3a4b5d6e7
Create Date: 2026-11-18 11:56:59.649560

PostgreSQL enum labels are append-only here because existing activity rows may
already contain either value when this migration is rolled back.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fc1f70c3fcc6"
down_revision: str | Sequence[str] | None = "c2f3a4b5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Allow activity execution rows to use the split script node types."""
    op.execute("ALTER TYPE public.nodetype ADD VALUE IF NOT EXISTS 'script_python'")
    op.execute("ALTER TYPE public.nodetype ADD VALUE IF NOT EXISTS 'script_bash'")


def downgrade() -> None:
    """Keep enum labels because PostgreSQL cannot safely remove used values."""
