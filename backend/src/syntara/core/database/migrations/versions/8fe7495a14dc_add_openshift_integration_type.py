"""Add OpenShift to the integration discriminator PostgreSQL enum.

Revision ID: 8fe7495a14dc
Revises: d5b8c2f04e71
Create Date: 2026-09-23 13:11:39.630834

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

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
    """Restore the prior enum, provided no OpenShift integrations would be lost."""
    connection = op.get_bind()
    has_openshift_integration = connection.execute(
        text("SELECT EXISTS (SELECT 1 FROM public.integrations WHERE integration_type = 'openshift')")
    ).scalar_one()
    if has_openshift_integration:
        msg = "Cannot downgrade while OpenShift integrations exist; remove them explicitly first"
        raise RuntimeError(msg)

    # PostgreSQL cannot drop an enum label in place. Rebuild the type without
    # deleting integrations of the other three types.
    op.execute(
        "CREATE TYPE public.integration_type_previous AS ENUM "
        "('mcp_server', 'llm_provider', 'ansible_automation_platform')"
    )
    op.execute(
        "ALTER TABLE public.integrations ALTER COLUMN integration_type "
        "TYPE public.integration_type_previous USING integration_type::text::public.integration_type_previous"
    )
    op.execute("DROP TYPE public.integration_type")
    op.execute("ALTER TYPE public.integration_type_previous RENAME TO integration_type")
