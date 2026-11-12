"""Use partition recovery fences instead of separate request and hold tables.

Revision ID: c4a8f17d2e93
Revises: 1de0863de9dc

Stop ingestion/recovery workers before upgrading or downgrading. Active automatic
recovery tokens remain on their partition rows. Resolve legacy manual requests
and standalone holds with the previous compatible version before upgrading.
The migration refuses to discard those unresolved protections.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4a8f17d2e93"
down_revision: str | Sequence[str] | None = "1de0863de9dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Preserve active partition fences before removing redundant tables."""
    # CUSTOM: Table removal must not erase an unresolved reservation or decision.
    op.execute(
        "LOCK TABLE event_subscription_sources, kafka_partition_initial_positions, "
        "event_subscription_recoveries, event_delivery_recovery_holds IN ACCESS EXCLUSIVE MODE"
    )
    connection = op.get_bind()
    protected = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM event_subscription_recoveries WHERE NOT completed) "
            "OR EXISTS (SELECT 1 FROM event_delivery_recovery_holds h "
            "WHERE h.released_at IS NULL AND NOT EXISTS ("
            "SELECT 1 FROM kafka_partition_initial_positions p "
            "WHERE p.recovery_token = h.token AND p.source_id = h.source_id)) "
            "OR EXISTS (SELECT 1 FROM kafka_partition_initial_positions p "
            "WHERE p.recovery_token IS NOT NULL AND (NOT EXISTS ("
            "SELECT 1 FROM event_delivery_recovery_holds h "
            "WHERE h.token = p.recovery_token AND h.source_id = p.source_id AND h.released_at IS NULL) "
            "OR p.pending_policy IS DISTINCT FROM 'retained_beginning' "
            "OR p.pending_duplicate_risk_acknowledged "
            "OR p.pending_reason NOT IN ('missing_commit', 'out_of_range', 'below_authorized_boundary')))"
        )
    ).scalar()
    if protected:
        msg = "Resolve legacy manual recovery decisions and unmatched holds before removing recovery tables"
        raise RuntimeError(msg)
    foreign_keys = sa.inspect(connection).get_foreign_keys("kafka_partition_initial_positions")
    for foreign_key in foreign_keys:
        if foreign_key["constrained_columns"] == ["recovery_token"]:
            name = foreign_key["name"]
            if name is None:
                msg = "Expected a named partition recovery-token foreign key"
                raise RuntimeError(msg)
            op.drop_constraint(name, "kafka_partition_initial_positions", type_="foreignkey")
            break
    else:
        msg = "Expected the legacy partition recovery-token foreign key"
        raise RuntimeError(msg)
    op.drop_table("event_subscription_recoveries")
    op.drop_index("ix_event_delivery_recovery_holds_active_source", table_name="event_delivery_recovery_holds")
    op.drop_table("event_delivery_recovery_holds")
    # END CUSTOM


def downgrade() -> None:
    """Recreate legacy storage and restore holds for every active partition token."""
    # CUSTOM: Backfill active tokens before restoring the old foreign key.
    op.execute("LOCK TABLE event_subscription_sources, kafka_partition_initial_positions IN ACCESS EXCLUSIVE MODE")
    op.create_table(
        "event_delivery_recovery_holds",
        sa.Column("token", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False
        ),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["event_subscription_sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("token"),
    )
    op.create_index(
        "ix_event_delivery_recovery_holds_active_source",
        "event_delivery_recovery_holds",
        ["source_id"],
        postgresql_where=sa.text("released_at IS NULL"),
    )
    op.execute(
        "INSERT INTO event_delivery_recovery_holds (token, source_id) "
        "SELECT DISTINCT recovery_token, source_id FROM kafka_partition_initial_positions "
        "WHERE recovery_token IS NOT NULL"
    )
    op.create_foreign_key(
        "kafka_partition_initial_positions_recovery_token_fkey",
        "kafka_partition_initial_positions",
        "event_delivery_recovery_holds",
        ["recovery_token"],
        ["token"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "event_subscription_recoveries",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("partition", sa.Integer(), nullable=False),
        sa.Column("configuration_revision", sa.BigInteger(), nullable=False),
        sa.Column("expected_recovery_revision", sa.BigInteger(), nullable=False),
        sa.Column("policy", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=False),
        sa.Column("acknowledge_duplicate_risk", sa.Boolean(), nullable=False),
        sa.Column("resolve_unscheduled", sa.Boolean(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("completed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.CheckConstraint("partition >= 0", name="ck_event_recovery_partition"),
        sa.CheckConstraint(
            "configuration_revision > 0 AND expected_recovery_revision >= 0", name="ck_event_recovery_revision"
        ),
        sa.CheckConstraint("policy IN ('retained_beginning', 'current_end')", name="ck_event_recovery_policy"),
        sa.ForeignKeyConstraint(["requested_by"], ["principals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_id"], ["event_subscription_sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("source_id", "partition"),
    )
    # END CUSTOM
