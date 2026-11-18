"""Add Kafka Publish to persisted activity execution node types.

Revision ID: 07f34fed0845
Revises: 1de0863de9dc
PostgreSQL enum additions are not detected by Alembic autogenerate. The model
already supports Kafka Publish, but upgraded databases need this label before
activity execution records can be persisted.

Downgrade retains the label and existing execution data. Keep compatible readers
while Kafka Publish definitions or activity executions are retained; preserving
the label does not make older application code understand the node type.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "07f34fed0845"
down_revision: str | Sequence[str] | None = "1de0863de9dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Allow Kafka Publish execution tracking without rewriting existing rows."""
    # CUSTOM: Alembic autogenerate does not detect PostgreSQL enum additions.
    op.execute("ALTER TYPE nodetype ADD VALUE IF NOT EXISTS 'kafka_publish'")
    # END CUSTOM


def downgrade() -> None:
    """Preserve the enum label and execution data; observe rollback conditions above."""
