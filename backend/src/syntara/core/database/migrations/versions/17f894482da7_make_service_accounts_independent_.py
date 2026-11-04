"""keep optional creation context on independent service accounts

Revision ID: 17f894482da7
Revises: e7f4a1b2c3d4
Create Date: 2026-10-20 13:48:41.994408

Service account project links are creation context, not an authorization boundary.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "17f894482da7"
down_revision: str | Sequence[str] | None = "e7f4a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make project context optional and clear it when a project is deleted."""
    op.drop_constraint(op.f("service_accounts_project_id_fkey"), "service_accounts", type_="foreignkey")
    op.alter_column("service_accounts", "project_id", existing_type=sa.UUID(), nullable=True)
    op.create_foreign_key(
        op.f("service_accounts_project_id_fkey"),
        "service_accounts",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Restore required project context only when no accounts are projectless."""
    if op.get_bind().execute(sa.text("SELECT 1 FROM service_accounts WHERE project_id IS NULL LIMIT 1")).first():
        msg = "Cannot downgrade while projectless service accounts exist."
        raise RuntimeError(msg)
    op.drop_constraint(op.f("service_accounts_project_id_fkey"), "service_accounts", type_="foreignkey")
    op.alter_column("service_accounts", "project_id", existing_type=sa.UUID(), nullable=False)
    op.create_foreign_key(
        op.f("service_accounts_project_id_fkey"), "service_accounts", "projects", ["project_id"], ["id"]
    )
