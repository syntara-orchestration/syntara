"""Local authority budgets; isolated tests do not establish database contention guarantees."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from syntara.core.config.base import EventStreamSettings
from syntara.core.constants import EventPlacementDefaults
from syntara.eventstreams.core.placement import (
    PlacementAuthority,
    SubscriptionPlacementLease,
    WorkerIdentity,
    WorkerMembership,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def placement_lease(worker: WorkerIdentity, subscription_id: UUID, *, seconds: int = 60) -> SubscriptionPlacementLease:
    return SubscriptionPlacementLease(
        subscription_id=subscription_id,
        owner=worker,
        confirmed_at=NOW,
        expires_at=NOW + timedelta(seconds=seconds),
    )


def test_worker_and_lease_values_are_distinct_immutable_contexts() -> None:
    deployment = uuid4()
    first, second = WorkerIdentity(deployment_id=deployment), WorkerIdentity(deployment_id=deployment)
    assert first.worker_id != second.worker_id
    lease = placement_lease(first, uuid4())
    membership = WorkerMembership(worker=first, heartbeat_until=lease.expires_at, draining=False)
    for value, field, replacement in [
        (first, "worker_id", second.worker_id),
        (membership, "draining", True),
        (lease, "expires_at", NOW),
    ]:
        with pytest.raises(ValidationError, match="frozen"):
            setattr(value, field, replacement)
    with pytest.raises(ValidationError, match="expiry"):
        placement_lease(first, uuid4(), seconds=0)


def test_request_and_commit_latency_only_shorten_database_time_authority() -> None:
    worker, key = WorkerIdentity(deployment_id=uuid4()), uuid4()
    clock = [50.0]
    guard = PlacementAuthority(worker, key, clock=lambda: clock[0])
    assert guard.confirm(placement_lease(worker, key), request_started=10.0)
    clock[0] = 70.0  # Exact conservative deadline: 10 + 60.
    assert not guard.is_current()
    assert not guard.confirm(placement_lease(worker, key), request_started=10.0)


def test_lost_guard_cannot_reopen_until_previous_local_consumer_has_stopped() -> None:
    worker, key = WorkerIdentity(deployment_id=uuid4()), uuid4()
    guard = PlacementAuthority(worker, key, clock=lambda: 0.0)
    lease = placement_lease(worker, key)
    assert guard.confirm(lease, request_started=0.0)
    first, other = object(), object()
    assert guard.reserve_local(first)
    assert not guard.reserve_local(other)
    guard.invalidate()
    assert not guard.confirm(lease, request_started=0.0)
    guard.local_stopped(other)
    assert guard.local_in_use
    guard.local_stopped(first)
    assert guard.confirm(lease, request_started=0.0)
    assert guard.reserve_local(other)


@pytest.mark.parametrize("change", ["worker", "deployment", "subscription"])
def test_confirm_rejects_other_owner_or_namespace(change) -> None:
    worker, key = WorkerIdentity(deployment_id=uuid4()), uuid4()
    guard = PlacementAuthority(worker, key)
    wrong = worker.model_copy(update={"worker_id" if change == "worker" else "deployment_id": uuid4()})
    lease = placement_lease(worker if change == "subscription" else wrong, uuid4() if change == "subscription" else key)
    with pytest.raises(ValueError, match="match"):
        guard.confirm(lease, request_started=0.0)
    assert not guard.is_current()


async def test_renewal_wakes_watchdog_without_reporting_loss() -> None:
    worker, key = WorkerIdentity(deployment_id=uuid4()), uuid4()
    guard = PlacementAuthority(worker, key, clock=lambda: 0.0)
    guard.confirm(placement_lease(worker, key), request_started=0.0)
    watching = asyncio.create_task(guard.wait_lost())
    await asyncio.sleep(0)
    guard.confirm(placement_lease(worker, key, seconds=120), request_started=0.0)
    await asyncio.sleep(0)
    assert not watching.done()
    guard.invalidate()
    await asyncio.wait_for(watching, timeout=1)


@pytest.mark.parametrize(
    "values",
    [
        {"event_worker_heartbeat_interval_seconds": 0},
        {"event_worker_liveness_seconds": 20},
        {"event_subscription_lease_seconds": 20},
        {"event_worker_heartbeat_interval_seconds": 60},
    ],
)
def test_placement_intervals_require_positive_renewal_margin(values) -> None:
    with pytest.raises(ValidationError):
        EventStreamSettings(**values)


def test_unvalidated_placement_defaults_are_separate_from_delivery_leases() -> None:
    settings = EventStreamSettings()
    assert settings.event_worker_heartbeat_interval_seconds == EventPlacementDefaults.HEARTBEAT_INTERVAL_SECONDS == 20
    assert settings.event_worker_liveness_seconds == EventPlacementDefaults.WORKER_LIVENESS_SECONDS == 60
    assert settings.event_subscription_lease_seconds == EventPlacementDefaults.SUBSCRIPTION_LEASE_SECONDS == 60
