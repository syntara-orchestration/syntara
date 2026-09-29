"""drop_form_prompt_timezone

Revision ID: f3a6b219c8d0
Revises: 2a78b3c49c72
Create Date: 2026-09-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a6b219c8d0"
down_revision: str | Sequence[str] | None = "2a78b3c49c72"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove the obsolete form-level timezone column."""
    op.drop_column("form_prompts", "timezone")


def downgrade() -> None:
    """Restore the nullable form-level timezone column."""
    op.add_column("form_prompts", sa.Column("timezone", sa.String(length=64), nullable=True))
