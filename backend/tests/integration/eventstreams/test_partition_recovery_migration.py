"""Recovery-table removal preserves partition tokens and rejects unresolved legacy state."""

import importlib
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select

from syntara.eventstreams.adapters.kafka_initial_position import KafkaPartitionInitialPosition
from tests.integration.eventstreams.conftest import DeliveryContext, hold_partition_recovery

pytestmark = pytest.mark.integration
MIGRATION = "syntara.core.database.migrations.versions.c4a8f17d2e93_use_partition_recovery_fences"


async def test_recovery_table_removal_preserves_parallel_partition_tokens(
    delivery_context: DeliveryContext, eventstream_migration_engine: AsyncEngine
) -> None:
    context = delivery_context
    tokens = {await hold_partition_recovery(context, partition) for partition in (0, 1)}
    migration = importlib.import_module(MIGRATION)

    def round_trip(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            retained = connection.execute(sa.text("SELECT token FROM event_delivery_recovery_holds")).scalars().all()
            assert set(retained) == tokens
            migration.upgrade()
        inspector = sa.inspect(connection)
        assert not inspector.has_table("event_subscription_recoveries")
        assert not inspector.has_table("event_delivery_recovery_holds")
        assert inspector.has_table("event_subscription_runtimes")
        assert inspector.has_table("event_delivery_capacity")
        assert all(
            key["constrained_columns"] != ["recovery_token"]
            for key in inspector.get_foreign_keys("kafka_partition_initial_positions")
        )

    async with eventstream_migration_engine.begin() as connection:
        await connection.run_sync(round_trip)
    async with context.session_factory() as session:
        positions = (
            await session.exec(
                select(KafkaPartitionInitialPosition).where(
                    KafkaPartitionInitialPosition.source_id == context.snapshot.source_id
                )
            )
        ).all()
        assert {row.recovery_token for row in positions} == tokens
        assert all(row.recovery_revision == 1 and row.pending_boundary == 0 for row in positions)


@pytest.mark.parametrize("protected", ["manual_request", "standalone_hold", "manual_partition"])
async def test_recovery_table_removal_refuses_unresolved_legacy_state(
    delivery_context: DeliveryContext, eventstream_migration_engine: AsyncEngine, protected: str
) -> None:
    context = delivery_context
    if protected == "manual_partition":
        await hold_partition_recovery(context)
    migration = importlib.import_module(MIGRATION)

    def remove_protected_tables(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            if protected == "manual_request":
                connection.execute(
                    sa.text(
                        "INSERT INTO event_subscription_recoveries "
                        "(source_id, partition, configuration_revision, expected_recovery_revision, policy, "
                        "reason, acknowledge_duplicate_risk, resolve_unscheduled, requested_by) "
                        "VALUES (:source, 0, :revision, 0, 'retained_beginning', 'operator_recovery', "
                        "false, false, :principal)"
                    ),
                    {
                        "source": context.snapshot.source_id,
                        "revision": context.snapshot.configuration_revision,
                        "principal": context.principal_id,
                    },
                )
            elif protected == "standalone_hold":
                connection.execute(
                    sa.text("INSERT INTO event_delivery_recovery_holds (token, source_id) VALUES (:token, :source)"),
                    {"token": uuid4(), "source": context.snapshot.source_id},
                )
            else:
                connection.execute(
                    sa.text(
                        "UPDATE kafka_partition_initial_positions SET pending_policy = 'current_end' "
                        "WHERE source_id = :source"
                    ),
                    {"source": context.snapshot.source_id},
                )
            migration.upgrade()

    with pytest.raises(RuntimeError, match="Resolve legacy manual recovery"):
        async with eventstream_migration_engine.begin() as connection:
            await connection.run_sync(remove_protected_tables)
