"""Placement schema and metadata behavior without a PostgreSQL service."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import CheckConstraint, Column, DateTime, MetaData, Table, Uuid, create_engine, create_mock_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, make_transient_to_detached
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.schema import CreateIndex, CreateTable

from syntara.core.database.migrations.models import ALL_MODELS
from syntara.core.models.base.base_resource import touch_audit_metadata_before_flush
from syntara.eventstreams.models.consumer_worker import EventConsumerWorker
from syntara.eventstreams.models.subscription import EventSubscription

_POSTGRESQL = create_mock_engine("postgresql://", lambda *_args, **_kwargs: None).dialect


def _subscription() -> EventSubscription:
    return EventSubscription(
        workflow_id=uuid4(),
        project_id=uuid4(),
        trigger_node_id="incoming",
        published_version_id=uuid4(),
        active_source_generation=1,
        configuration_revision=7,
        enabled_by=uuid4(),
        created_by=uuid4(),
        updated_by=uuid4(),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.mark.parametrize(("has_owner", "has_lease"), [(False, False), (True, True), (True, False), (False, True)])
def test_assignment_pair_constraint(*, has_owner: bool, has_lease: bool) -> None:
    """Exercise the model's SQL check truth table on a minimal SQLite table."""
    check = next(
        constraint
        for constraint in EventSubscription.__table__.constraints  # type: ignore[attr-defined]
        if constraint.name == "ck_event_subscriptions_assignment_pair"
    )
    table = Table(
        "assignment_pair",
        MetaData(),
        Column("assigned_worker_id", Uuid, nullable=True),
        Column("assignment_lease_until", DateTime(timezone=True), nullable=True),
        CheckConstraint(str(check.sqltext)),
    )
    engine = create_engine("sqlite://")
    try:
        table.metadata.create_all(engine)
        with engine.begin() as connection:
            values = {
                "assigned_worker_id": uuid4() if has_owner else None,
                "assignment_lease_until": datetime.now(UTC) if has_lease else None,
            }
            if has_owner == has_lease:
                connection.execute(table.insert().values(**values))
            else:
                with pytest.raises(IntegrityError):
                    connection.execute(table.insert().values(**values))
    finally:
        engine.dispose()


def test_placement_claim_renew_transfer_and_release_preserve_user_metadata() -> None:
    subscription = _subscription()
    assert subscription.assigned_worker_id is None
    assert subscription.assignment_lease_until is None
    original = subscription.model_dump(exclude={"assigned_worker_id", "assignment_lease_until"})
    make_transient_to_detached(subscription)
    with Session() as session:
        session.add(subscription)
        deadline = datetime.now(UTC)
        first_owner = uuid4()
        for owner, lease in [
            (first_owner, deadline),
            (first_owner, deadline + timedelta(seconds=30)),
            (uuid4(), deadline + timedelta(seconds=60)),
            (None, None),
        ]:
            subscription.assigned_worker_id = owner
            subscription.assignment_lease_until = lease
            touch_audit_metadata_before_flush(session, None, None)
            assert subscription.model_dump(exclude={"assigned_worker_id", "assignment_lease_until"}) == original
            # Model the next transition starting from a persisted lease, so the
            # release check cannot pass simply by returning to initial defaults.
            set_committed_value(subscription, "assigned_worker_id", owner)
            set_committed_value(subscription, "assignment_lease_until", lease)

        subscription.paused = True
        touch_audit_metadata_before_flush(session, None, None)
        assert subscription.updated_at > original["updated_at"]


def test_worker_membership_is_operational_and_registered() -> None:
    table = EventConsumerWorker.__table__  # type: ignore[attr-defined]
    assert EventConsumerWorker in ALL_MODELS
    assert set(table.c.keys()) == {"worker_id", "deployment_id", "heartbeat_until", "draining", "started_at"}
    assert list(table.primary_key.columns.keys()) == ["worker_id"]
    assert not table.foreign_keys
    assert all(not column.nullable for column in table.c)
    assert str(table.c.started_at.server_default.arg) == "now()"
    assert str(table.c.draining.server_default.arg) == "false"
    first = EventConsumerWorker(deployment_id=uuid4(), heartbeat_until=datetime.now(UTC))
    second = EventConsumerWorker(deployment_id=first.deployment_id, heartbeat_until=datetime.now(UTC))
    assert first.worker_id != second.worker_id
    assert first.draining is False


def test_postgresql_placement_types_indexes_and_no_membership_cascade() -> None:
    subscription_table = EventSubscription.__table__  # type: ignore[attr-defined]
    worker_table = EventConsumerWorker.__table__  # type: ignore[attr-defined]
    assert not subscription_table.c.assigned_worker_id.foreign_keys
    assert subscription_table.c.assigned_worker_id.nullable
    assert subscription_table.c.assignment_lease_until.nullable
    assert subscription_table.c.assignment_lease_until.type.timezone
    assert subscription_table.c.updated_at.onupdate is None
    assert worker_table.c.heartbeat_until.type.timezone
    assert worker_table.c.started_at.type.timezone
    indexes = {index.name: index for index in subscription_table.indexes | worker_table.indexes}
    assert list(indexes["ix_event_subscriptions_assignment_owner"].columns.keys()) == ["assigned_worker_id"]
    expiry = indexes["ix_event_subscriptions_active_lease_expiry"]
    assert list(expiry.columns.keys()) == ["assignment_lease_until", "id"]
    assert "WHERE desired_enabled = true AND paused = false AND retired = false" in str(
        CreateIndex(expiry).compile(dialect=_POSTGRESQL)
    )
    assert list(indexes["ix_event_consumer_workers_live_membership"].columns.keys()) == [
        "deployment_id",
        "draining",
        "heartbeat_until",
    ]
    assert "TIMESTAMP WITH TIME ZONE" in str(CreateTable(worker_table).compile(dialect=_POSTGRESQL))
