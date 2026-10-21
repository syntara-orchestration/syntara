"""Recovery worker lifecycle against PostgreSQL with isolated Temporal."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import func
from sqlmodel import select

from syntara.core.services.secret_service import create_secret_service
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.eventstreams.core.deduplication import DeliveryState
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.eventstreams.services.recovery_worker import EventDeliveryRecoveryWorker
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow import Workflow
from tests.integration.eventstreams.conftest import AvailableCapacity, DeliveryContext
from tests.integration.eventstreams.test_execution_preparation import envelope
from tests.integration.eventstreams.test_execution_scheduling import IsolatedTemporal

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def recovery_worker(
    delivery_context: DeliveryContext,
) -> tuple[EventDeliveryRecoveryWorker, DeliveryContext, IsolatedTemporal, PreparedExecution]:
    """Prepare one delivery and create a worker pointing at the same DB and Temporal adapter."""
    context = delivery_context
    async with context.session_factory() as session, session.begin():
        credential = await session.get(Credential, context.snapshot.runtime_credential_id)
        assert credential is not None
        credential.secret_id = await create_secret_service(session).create_secret(
            {"username": "test", "password": "test"}
        )
        credential_type = await session.get(CredentialType, credential.credential_type_id)
        assert credential_type is not None
        credential_type.injectors = {"extra_vars": {"kafka_username": "{{username}}", "kafka_password": "{{password}}"}}
    prepared = await EventExecutionPreparationService(
        context.session_factory, capacity_check=AvailableCapacity()
    ).prepare_delivery(context.snapshot, context.identity(), await envelope(context), "first")
    assert isinstance(prepared, PreparedExecution)
    temporal = IsolatedTemporal(context)
    worker = EventDeliveryRecoveryWorker(
        context.session_factory, temporal, batch_limit=10, worker_id="integration-test"
    )
    return worker, context, temporal, prepared


async def test_tick_recovers_expired_prepared_delivery(recovery_worker) -> None:
    """AC: Due selection includes recoverable deliveries with bounded batches and claim tokens."""
    worker, context, temporal, prepared = recovery_worker
    await context.expire(prepared.claim)
    count = await worker.tick()
    assert count == 1
    assert len(temporal.starts) == 1
    async with context.session_factory() as session:
        row = await session.get(EventDelivery, prepared.claim.identity.digest)
        assert row.state == DeliveryState.SCHEDULED


async def test_tick_skips_unprepared_work(recovery_worker) -> None:
    """Recovery only claims prepared deliveries (frozen_binding IS NOT NULL)."""
    worker, context, temporal, prepared = recovery_worker
    await context.claim(99)
    await context.expire(prepared.claim)
    count = await worker.tick()
    assert count == 1
    assert temporal.starts[0].execution_id == prepared.execution_id


@pytest.mark.parametrize("lifecycle", ["paused", "unpublished", "retired"])
async def test_tick_recovers_inactive_source(recovery_worker, lifecycle) -> None:
    """AC: Due selection includes recoverable deliveries for inactive/retired sources."""
    worker, context, temporal, prepared = recovery_worker
    async with context.session_factory() as session, session.begin():
        subscription = await session.get(EventSubscription, context.snapshot.subscription_id)
        if lifecycle == "paused":
            subscription.paused = True
        elif lifecycle == "unpublished":
            workflow = await session.get(Workflow, context.snapshot.workflow_id)
            workflow.published_version_id = None
            workflow.is_enabled = subscription.desired_enabled = False
        else:
            subscription.retired = True
            subscription.desired_enabled = False
            source = await session.get(EventSubscriptionSource, context.snapshot.source_id)
            source.retired_at = (await session.exec(select(func.clock_timestamp()))).one()
    await context.expire(prepared.claim)
    count = await worker.tick()
    assert count == 1
    assert isinstance(temporal.starts[0], PreparedExecution)
    async with context.session_factory() as session:
        row = await session.get(EventDelivery, prepared.claim.identity.digest)
        assert row.state == DeliveryState.SCHEDULED


async def test_tick_reuses_frozen_context_and_stable_identity(recovery_worker) -> None:
    """AC: Recovery reuses frozen Execution context and stable Temporal identity without Kafka."""
    worker, context, temporal, prepared = recovery_worker
    await context.expire(prepared.claim)
    await worker.tick()
    started = temporal.starts[0]
    assert started.execution_id == prepared.execution_id
    assert started.temporal_workflow_id == prepared.temporal_workflow_id
    assert started.workflow_arguments() == prepared.workflow_arguments()
    async with context.session_factory() as session:
        assert (await session.exec(select(func.count()).select_from(Execution))).one() == 1


async def test_concurrent_workers_do_not_duplicate(recovery_worker) -> None:
    """AC: Concurrent scans with superseded tokens cannot produce unauthorized finalization."""
    worker, context, temporal, prepared = recovery_worker
    await context.expire(prepared.claim)

    worker2 = EventDeliveryRecoveryWorker(
        context.session_factory, temporal, batch_limit=10, worker_id="concurrent-test"
    )
    count1 = await worker.tick()
    count2 = await worker2.tick()
    assert count1 + count2 == 1
    assert len(temporal.starts) == 1


async def test_drain_prevents_new_claims(recovery_worker) -> None:
    """AC: Stop prevents new claims and drains within a bound without erasing evidence."""
    worker, context, _temporal, prepared = recovery_worker
    await context.expire(prepared.claim)
    await worker.drain()
    assert await worker.tick() == 0
    async with context.session_factory() as session:
        row = await session.get(EventDelivery, prepared.claim.identity.digest)
        assert row.state == DeliveryState.IN_PROGRESS
        assert row.frozen_binding is not None


async def test_failure_isolation_across_deliveries(recovery_worker) -> None:
    """AC: Blocked resource retains unresolved work while unrelated recoveries may progress."""
    worker, context, temporal, prepared = recovery_worker
    await context.expire(prepared.claim)

    good_claim = await context.claim(42, prepare=True)
    await context.expire(good_claim)

    temporal.fail_starts = True
    count = await worker.tick()
    assert count == 2
    temporal.fail_starts = False

    async with context.session_factory() as session:
        for digest in [prepared.claim.identity.digest, good_claim.identity.digest]:
            row = await session.get(EventDelivery, digest)
            assert row.state == DeliveryState.IN_PROGRESS
            assert row.scheduling_failure_count > 0
