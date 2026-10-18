"""Add the event Subscribe trigger node type.

Revision ID: f8c2e5a13b70
Revises: e7a1c4b92f08

PostgreSQL enum additions are not detected by Alembic autogenerate.
This revision is stacked after the Kafka Integration migration in PR #898.

Before rolling application code back, stop event ingestion and ensure no
definitions or retained activity executions using this node type will be read
by incompatible workers or APIs. Keep compatible readers while such data is
retained. Downgrade preserves the enum label and all workflow/execution data;
it does not make older application code capable of reading the new node type.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f8c2e5a13b70"
down_revision: str | Sequence[str] | None = "e7a1c4b92f08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the supported trigger value without rewriting existing activities."""
    # CUSTOM: Alembic autogenerate does not detect PostgreSQL enum additions.
    op.execute("ALTER TYPE nodetype ADD VALUE IF NOT EXISTS 'event_subscribe_trigger'")
    # END CUSTOM


def downgrade() -> None:
    """Preserve the enum label and data; observe the rollback conditions above."""
