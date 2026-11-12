"""Guard legacy table removal and preserve normal Execution/position evidence."""

import importlib
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from syntara.eventstreams.adapters.kafka_initial_position import KafkaPartitionInitialPosition
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.models.consumer_worker import EventConsumerWorker
from syntara.workflows.models.execution import Execution, ExecutionStatus
from tests.integration.eventstreams import test_execution_scheduling
from tests.integration.eventstreams.test_execution_scheduling import SchedulingContext

pytestmark = pytest.mark.integration
preparation_context = test_execution_scheduling.preparation_context
scheduling_context = test_execution_scheduling.scheduling_context
MIGRATION = "syntara.core.database.migrations.versions.07ace57975ac_remove_legacy_event_delivery_tables"


def legacy_delivery(connection: Connection, prepared: PreparedExecution, state: str) -> None:
    """Insert an old row through reflection, without reintroducing the removed model."""
    table = sa.Table("event_deliveries", sa.MetaData(), autoload_with=connection)
    identity = prepared.identity
    scheduled = state == "scheduled"
    now = datetime.now(UTC)
    connection.execute(
        table.insert().values(
            identity_digest=identity.digest,
            identity_version=1,
            deployment_id=identity.deployment_id,
            integration_identity=identity.integration_identity,
            source_id=identity.source_id,
            source_generation=identity.source_generation,
            transport="kafka",
            workflow_id=identity.workflow_id,
            subscription_id=identity.subscription_id,
            record_identity=identity.record.model_dump(mode="json"),
            state=state,
            execution_identity=identity.execution_id,
            temporal_workflow_id=identity.temporal_workflow_id,
            frozen_binding=prepared.binding.model_dump(mode="json") if scheduled else sa.null(),
            temporal_run_id="accepted-run" if scheduled else None,
            execution_confirmed_at=now if scheduled else None,
            resolved_at=None if state == "in_progress" else now,
            attempt_count=0,
        )
    )


def retained_execution(connection: Connection, prepared: PreparedExecution, *, confirmed: bool) -> None:
    """Create normal Execution metadata matching the previous scheduling format."""
    execution = prepared.execution()
    execution.status = ExecutionStatus.COMPLETED
    execution.execution_metadata = {
        **prepared.workflow_metadata,
        "event_delivery": {
            "identity_digest": prepared.identity.digest,
            "scheduling_state": "confirmed" if confirmed else "prepared",
            "input_fingerprint": prepared.binding.input_fingerprint,
            "temporal_workflow_id": prepared.temporal_workflow_id,
            "temporal_run_id": "accepted-run",
            "confirmed_at": datetime.now(UTC).isoformat(),
        },
    }
    connection.execute(sa.insert(Execution), execution.model_dump())


@pytest.mark.parametrize(
    "protected",
    [
        "in_progress",
        "rejected",
        "cancelled",
        "filtered",
        "scheduled",
        "runtime",
        "worker",
        "position",
        "source_history",
        "retirement_authorized_by",
        "retirement_reason",
        "retirement_completed_at",
        "unconfirmed",
    ],
)
async def test_removal_refuses_unresolved_legacy_state(
    scheduling_context: SchedulingContext, eventstream_migration_engine: AsyncEngine, protected: str
) -> None:
    prepared = scheduling_context.prepared
    migration = importlib.import_module(MIGRATION)

    def guarded_upgrade(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            seed_protected_state(connection, prepared, protected)
            migration.upgrade()

    # The exception rolls back the legacy schema and leaves the current head intact.
    with pytest.raises(RuntimeError):
        async with eventstream_migration_engine.begin() as connection:
            await connection.run_sync(guarded_upgrade)


def seed_protected_state(connection: Connection, prepared: PreparedExecution, protected: str) -> None:
    """Arrange one real PostgreSQL guard condition at a time."""
    if protected in {"in_progress", "rejected", "cancelled", "filtered", "scheduled"}:
        legacy_delivery(connection, prepared, protected)
    elif protected == "runtime":
        connection.execute(
            sa.text(
                "INSERT INTO event_subscription_runtimes "
                "(source_id, worker_id, configuration_revision) VALUES (:source, 'legacy', 1)"
            ),
            {"source": prepared.identity.source_id},
        )
    elif protected == "worker":
        worker = EventConsumerWorker(
            deployment_id=prepared.identity.deployment_id,
            started_at=datetime.now(UTC),
            heartbeat_until=datetime.now(UTC) + timedelta(minutes=1),
        )
        connection.execute(sa.insert(EventConsumerWorker), worker.model_dump())
    elif protected == "position":
        position = KafkaPartitionInitialPosition(
            source_id=prepared.identity.source_id,
            partition=0,
            initial_next_offset=0,
            recovery_token=prepared.execution_id,
            recovery_revision=1,
            pending_boundary=0,
            pending_policy="retained_beginning",
            pending_reason="missing_commit",
            gap_detected_at=datetime.now(UTC),
            gap_reason="missing_commit",
        )
        connection.execute(sa.insert(KafkaPartitionInitialPosition), position.model_dump())
    elif protected == "source_history":
        connection.execute(
            sa.text("UPDATE event_subscription_sources SET delivery_evidence_revision = 1 WHERE id = :source"),
            {"source": prepared.identity.source_id},
        )
    elif protected in {"retirement_authorized_by", "retirement_reason", "retirement_completed_at"}:
        table = sa.Table("event_subscription_sources", sa.MetaData(), autoload_with=connection)
        values: dict[str, object] = {
            "retirement_authorized_by": prepared.binding.execution_principal_id,
            "retirement_reason": "legacy_retirement",
            "retirement_completed_at": datetime.now(UTC),
        }
        connection.execute(
            table.update().where(table.c.id == prepared.identity.source_id).values({protected: values[protected]})
        )
    else:
        assert protected == "unconfirmed"
        retained_execution(connection, prepared, confirmed=False)


async def test_removal_preserves_confirmed_execution_and_saved_position(
    scheduling_context: SchedulingContext, eventstream_migration_engine: AsyncEngine
) -> None:
    prepared = scheduling_context.prepared
    migration = importlib.import_module(MIGRATION)
    position = KafkaPartitionInitialPosition(source_id=prepared.identity.source_id, partition=0, initial_next_offset=41)

    def upgrade(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            legacy_delivery(connection, prepared, "scheduled")
            retained_execution(connection, prepared, confirmed=True)
            connection.execute(sa.insert(KafkaPartitionInitialPosition), position.model_dump())
            before = connection.execute(
                sa.text("SELECT * FROM executions WHERE id = :id"), {"id": prepared.execution_id}
            ).one()
            migration.upgrade()
        inspector = sa.inspect(connection)
        assert not inspector.has_table("event_deliveries")
        assert not inspector.has_table("event_delivery_capacity")
        assert not inspector.has_table("event_subscription_runtimes")
        after = connection.execute(
            sa.text("SELECT * FROM executions WHERE id = :id"), {"id": prepared.execution_id}
        ).one()
        assert after == before
        assert (
            connection.scalar(
                sa.text("SELECT initial_next_offset FROM kafka_partition_initial_positions WHERE source_id = :source"),
                {"source": prepared.identity.source_id},
            )
            == 41
        )

    async with eventstream_migration_engine.begin() as connection:
        await connection.run_sync(upgrade)


async def test_upgrade_holds_all_evidence_locks_before_running_the_guard(
    eventstream_migration_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration = importlib.import_module(MIGRATION)
    original_guard = migration.require_resolved_eventstream_ledger
    required = {
        "event_consumer_workers",
        "event_subscription_runtimes",
        "event_deliveries",
        "event_delivery_capacity",
        "event_subscription_sources",
        "kafka_partition_initial_positions",
        "executions",
    }

    def guarded(connection: Connection) -> None:
        locked = set(
            connection.execute(
                sa.text(
                    "SELECT locked_relation.relname FROM pg_locks AS held_lock "
                    "JOIN pg_class AS locked_relation ON locked_relation.oid = held_lock.relation "
                    "WHERE held_lock.pid = pg_backend_pid() AND held_lock.granted "
                    "AND held_lock.mode = 'AccessExclusiveLock'"
                )
            ).scalars()
        )
        assert required <= locked
        original_guard(connection)

    def downgrade(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()

    def upgrade(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    def restore(connection: Connection) -> None:
        if sa.inspect(connection).has_table("event_deliveries"):
            upgrade(connection)

    # Commit setup separately: locks from downgrade/CREATE TABLE must not make
    # this test pass when upgrade forgets to acquire its own locks.
    async with eventstream_migration_engine.begin() as connection:
        await connection.run_sync(downgrade)
    try:
        with monkeypatch.context() as patcher:
            patcher.setattr(migration, "require_resolved_eventstream_ledger", guarded)
            async with eventstream_migration_engine.begin() as connection:
                await connection.run_sync(upgrade)
    finally:
        async with eventstream_migration_engine.begin() as connection:
            await connection.run_sync(restore)


@pytest.mark.parametrize("protected", ["execution", "worker"])
async def test_downgrade_refuses_retained_event_execution_or_live_worker(
    scheduling_context: SchedulingContext, eventstream_migration_engine: AsyncEngine, protected: str
) -> None:
    migration = importlib.import_module(MIGRATION)

    def downgrade(connection: Connection) -> None:
        if protected == "execution":
            retained_execution(connection, scheduling_context.prepared, confirmed=True)
        else:
            seed_protected_state(connection, scheduling_context.prepared, "worker")
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()

    with pytest.raises(RuntimeError, match="retained event Executions"):
        async with eventstream_migration_engine.begin() as connection:
            await connection.run_sync(downgrade)
