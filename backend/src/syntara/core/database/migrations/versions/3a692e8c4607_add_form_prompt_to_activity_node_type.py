"""add form_prompt to activity node type

Revision ID: 3a692e8c4607
Revises: 2a78b3c49c72
Create Date: 2026-09-24 13:49:46.095434

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a692e8c4607"
down_revision: str | Sequence[str] | None = "2a78b3c49c72"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE nodetype ADD VALUE IF NOT EXISTS 'form_prompt'")


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL does not support removing an individual enum label.
