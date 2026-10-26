"""Compile the provider migration to PostgreSQL SQL without a live database."""

from importlib import import_module
from io import StringIO
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_mock_engine
from sqlalchemy.schema import CreateIndex

from syntara.eventstreams.models.consumer_worker import EventConsumerWorker
from syntara.eventstreams.models.subscription import EventSubscription

_MIGRATION = "syntara.core.database.migrations.versions.83a9c641be72_add_event_consumer_placement"
_POSTGRESQL = create_mock_engine("postgresql://", lambda *_args, **_kwargs: None).dialect


@pytest.mark.parametrize("direction", ["upgrade", "downgrade"])
def test_placement_migration_preserves_durable_evidence(direction: str) -> None:
    migration = import_module(_MIGRATION)
    buffer = StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buffer})
    with Operations.context(context):
        getattr(migration, direction)()
    sql = buffer.getvalue()

    # Neither direction edits configuration JSON or touches recovery evidence.
    assert "event_subscription_sources" not in sql
    assert "event_deliveries" not in sql
    assert "kafka_partition_initial_positions" not in sql
    assert "DROP TABLE event_subscriptions;" not in sql
    assert "DELETE FROM" not in sql
    assert "UPDATE " not in sql
    if direction == "upgrade":
        assert "CREATE TABLE event_consumer_workers" in sql
        assert "ADD COLUMN assigned_worker_id UUID" in sql
        assert "ADD COLUMN assignment_lease_until TIMESTAMP WITH TIME ZONE" in sql
        assert "CHECK ((assigned_worker_id IS NULL) = (assignment_lease_until IS NULL))" in sql
        for table in (EventConsumerWorker.__table__, EventSubscription.__table__):  # type: ignore[attr-defined]
            for index in table.indexes:
                if index.name in {
                    "ix_event_consumer_workers_live_membership",
                    "ix_event_subscriptions_assignment_owner",
                    "ix_event_subscriptions_active_lease_expiry",
                }:
                    assert str(CreateIndex(index).compile(dialect=_POSTGRESQL)) in sql
    else:
        assert "DROP TABLE event_consumer_workers;" in sql
        assert sql.index("DROP CONSTRAINT ck_event_subscriptions_assignment_pair") < sql.index(
            "DROP COLUMN assignment_lease_until"
        )


def test_placement_revision_follows_subscription_head() -> None:
    migration = import_module(_MIGRATION)
    assert migration.__file__ is not None
    scripts = ScriptDirectory(str(Path(migration.__file__).parent.parent))
    assert scripts.get_heads() == [migration.revision]
    assert migration.down_revision == "759a689cc69c"
