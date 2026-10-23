"""Ledger schema constraints and safe, bounded coordination value contracts."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from syntara.eventstreams.core.deduplication import DeliveryState, TerminalDelivery
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.recovery_hold import EventDeliveryRecoveryHold
from tests.unit.eventstreams.test_delivery_identity import identity


def test_ledger_has_no_payload_or_secret_columns() -> None:
    """The delivery ledger stores references and integrity digests only."""
    columns = set(EventDelivery.__table__.columns.keys())  # type: ignore[attr-defined]
    assert not {"payload", "input_data", "envelope", "secret", "password", "topic", "partition", "offset"} & columns
    assert {"record_identity", "frozen_binding", "execution_identity", "first_start_attempt_at"} <= columns


def test_execution_deletion_cannot_cascade_delivery_evidence() -> None:
    """Terminal identity survives historical Execution reference detachment."""
    columns = EventDelivery.__table__.columns  # type: ignore[attr-defined]
    fk = next(iter(columns.execution_id.foreign_keys))
    assert fk.ondelete == "SET NULL"
    assert not columns.execution_identity.nullable
    assert not columns.workflow_id.foreign_keys
    assert not columns.subscription_id.foreign_keys
    checks = {constraint.name for constraint in EventDelivery.__table__.constraints}  # type: ignore[attr-defined]
    assert "ck_event_deliveries_unresolved_execution" in checks
    assert "ck_event_deliveries_scheduled_evidence" in checks


def test_bounded_due_and_terminal_indexes() -> None:
    """The schema supports separate unresolved and terminal scans."""
    indexes = {index.name: index for index in EventDelivery.__table__.indexes}  # type: ignore[attr-defined]
    assert {
        "ix_event_deliveries_due",
        "ix_event_deliveries_unowned_due",
        "ix_event_deliveries_terminal_cleanup",
    } <= indexes.keys()
    kafka = indexes["ix_event_deliveries_kafka_position"]
    assert str(kafka.dialect_options["postgresql"]["where"]) == "transport = 'kafka'"
    assert "::bigint" in str(kafka.expressions[-1])


def test_recovery_reservation_has_no_automatic_expiry() -> None:
    """Worker and claim lease expiration cannot remove an evidence reservation."""
    columns = set(EventDeliveryRecoveryHold.__table__.columns.keys())  # type: ignore[attr-defined]
    assert "released_at" in columns
    assert not {"expires_at", "lease_until", "payload", "secret"} & columns


@pytest.mark.parametrize("state", [DeliveryState.IN_PROGRESS, DeliveryState.SCHEDULED])
def test_incomplete_terminal_evidence_is_rejected(state: DeliveryState) -> None:
    """An unresolved row or unconfirmed acceptance cannot become a resolution value."""
    with pytest.raises(ValidationError):
        TerminalDelivery(identity=identity(), state=state, resolved_at=datetime.now(UTC))


def test_scheduled_terminal_requires_the_deterministic_execution() -> None:
    """A run with a different execution identity is never accepted as duplicate evidence."""
    with pytest.raises(ValidationError):
        TerminalDelivery(
            identity=identity(),
            state=DeliveryState.SCHEDULED,
            resolved_at=datetime.now(UTC),
            execution_id=UUID(int=99),
            temporal_run_id="run",
            execution_confirmed_at=datetime.now(UTC),
        )
