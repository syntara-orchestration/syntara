"""add payload column to work_items

Revision ID: a1b2c3d4e5f6
Revises: 9f3e1a2b4c7d
Create Date: 2026-09-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "9f3e1a2b4c7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EP = "execution_plane"


def upgrade() -> None:
    op.add_column(
        "work_items",
        sa.Column("payload", JSONB(), nullable=False, server_default="{}"),
        schema=EP,
    )


def downgrade() -> None:
    op.drop_column("work_items", "payload", schema=EP)
