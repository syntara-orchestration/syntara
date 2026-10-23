"""merge kafka subscriptions and activity control data

Revision ID: cdd536bc1946
Revises: 4469722de5b7, e7f4a1b2c3d4
Create Date: 2026-10-23 14:56:41.528223

Join the Kafka subscription and activity control-data branches so startup can
upgrade to a single head. Each parent retains its own schema operations.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "cdd536bc1946"
down_revision: str | Sequence[str] | None = ("4469722de5b7", "e7f4a1b2c3d4")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge histories without additional schema changes."""


def downgrade() -> None:
    """Split histories without reversing either parent migration."""
