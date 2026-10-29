"""add Kafka partition initialization kind without relabeling history

Revision ID: 91f4c2e8a6bd
Revises: 2b07573473d7

Existing boundaries remain untouched and initialization_kind remains NULL for
historical rows. Current metadata cannot prove the original topic partition set.
The provider blocks ambiguous initialization until explicit recovery or source
replacement; this migration never reconstructs initial_partition_ids.

Stop/drain ingestion and recovery before upgrade. Sources that predate this
migration without a captured set advance their existing evidence revision, even
when no position/delivery rows survive. This is an uncertainty fence, not proof
of original membership. Newly created sources retain revision zero and can
capture their first snapshot. Downgrade never decrements an evidence fence.

CUSTOM compatibility handling keeps the new field nullable and adds constraints
without a data backfill. Stop ingestion/recovery before downgrade. Downgrade
refuses to erase recorded kind evidence; permanently retire its source and
resolve all evidence dependencies before removing any such rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision: str = "91f4c2e8a6bd"
down_revision: str | Sequence[str] | None = "2b07573473d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Preserve historical choices; only the provider classifies new boundaries."""
    # CUSTOM: NULL is intentional compatibility evidence, not a first-activation default.
    op.execute("LOCK TABLE event_subscription_sources, kafka_partition_initial_positions IN ACCESS EXCLUSIVE MODE")
    op.add_column(
        "kafka_partition_initial_positions",
        sa.Column("initialization_kind", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=True),
    )
    op.create_check_constraint(
        "ck_kafka_initial_kind",
        "kafka_partition_initial_positions",
        "initialization_kind IS NULL OR initialization_kind IN ('first_activation', 'added_partition')",
    )
    op.create_check_constraint(
        "ck_kafka_initial_kind_evidence",
        "kafka_partition_initial_positions",
        "initialization_kind IS NULL OR NOT initial_metadata_missing",
    )
    op.execute(
        "UPDATE event_subscription_sources SET delivery_evidence_revision = delivery_evidence_revision + 1 "
        "WHERE transport = 'kafka' AND configuration->>'initial_partition_ids' IS NULL"
    )
    # END CUSTOM


def downgrade() -> None:
    """Do not erase classified boundaries to make an older provider accept them."""
    # CUSTOM: Serialize with source/position writers before checking retained evidence.
    op.execute("LOCK TABLE event_subscription_sources, kafka_partition_initial_positions IN ACCESS EXCLUSIVE MODE")
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM kafka_partition_initial_positions WHERE initialization_kind IS NOT NULL)"
            )
        )
        .scalar_one()
    ):
        msg = "Unsafe downgrade: retained Kafka initialization kind evidence remains"
        raise RuntimeError(msg)
    op.drop_constraint("ck_kafka_initial_kind_evidence", "kafka_partition_initial_positions", type_="check")
    op.drop_constraint("ck_kafka_initial_kind", "kafka_partition_initial_positions", type_="check")
    op.drop_column("kafka_partition_initial_positions", "initialization_kind")
    # END CUSTOM
