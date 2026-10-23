"""merge kafka integration and tested delivery histories

Revision ID: 6fb670b16b82
Revises: 52662dc0e022, cdd536bc1946
Create Date: 2026-10-23 18:17:34.861842

Join the parent's Kafka integration merge with the tested delivery branch.
Keep both existing revisions so databases already at either head can upgrade
without changing schema operations or rewriting applied migration history.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "6fb670b16b82"
down_revision: str | Sequence[str] | None = ("52662dc0e022", "cdd536bc1946")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge histories without additional schema changes."""


def downgrade() -> None:
    """Split histories without reversing either parent migration."""
