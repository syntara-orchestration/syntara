"""Add OpenShift to the integration discriminator PostgreSQL enum.

Revision ID: 8fe7495a14dc
Revises: d5b8c2f04e71
Create Date: 2026-09-23 13:11:39.630834

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8fe7495a14dc"
down_revision: str | Sequence[str] | None = "d5b8c2f04e71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # CUSTOM: Alembic does not detect additions to an existing PostgreSQL enum.
    # IF NOT EXISTS permits recovery after an interrupted, autocommitted enum DDL.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE public.integration_type ADD VALUE IF NOT EXISTS 'openshift'")
    # END CUSTOM


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL cannot drop a single enum value without replacing the type.
    # Refuse a silent downgrade that would leave a schema incompatible with code.
    msg = "Downgrading OpenShift integration enum requires an explicit data migration"
    raise NotImplementedError(msg)
