"""Targeted maintenance acknowledgement preserves delivery and recovery evidence."""

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, text
from sqlmodel import select

from syntara.eventstreams.adapters.kafka_initial_position import KafkaPartitionInitialPosition
from syntara.eventstreams.models.consumer_worker import EventConsumerWorker
from syntara.eventstreams.models.control import EventSubscriptionRuntime
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow import Workflow
from tests.integration.eventstreams import test_execution_scheduling
from tests.integration.eventstreams.conftest import hold_partition_recovery

pytestmark = pytest.mark.integration
scheduling_context = test_execution_scheduling.scheduling_context


async def acknowledge(context, **changes: object):
    """Bind the example's psql variables; execute the actual maintenance statement."""
    statement = (
        Path(__file__).resolve().parents[4] / "backend/samples/kafka/acknowledge-stopped-worker.example.sql"
    ).read_text()
    parameters = {
        "deployment_id": context.delivery.snapshot.deployment_id,
        "source_id": context.delivery.snapshot.source_id,
        "worker_id": context.worker_id,
        "worker_fenced": True,
        **changes,
    }
    for name in parameters:
        statement = statement.replace(f":'{name}'", f":{name}")
    async with context.delivery.session_factory() as session, session.begin():
        result = await session.execute(text(statement), parameters)
        row = result.one_or_none()
    return row  # noqa: RET504 - report success only after the transaction commits


async def evidence(context) -> dict[str, dict[str, Any]]:
    """Compare complete rows before and after the maintenance transaction."""
    snapshot = context.delivery.snapshot
    resources = {
        "runtime": (EventSubscriptionRuntime, (snapshot.source_id, str(context.worker_id))),
        "other_runtime": (EventSubscriptionRuntime, (snapshot.source_id, str(context.other_worker_id))),
        "member": (EventConsumerWorker, context.worker_id),
        "subscription": (EventSubscription, snapshot.subscription_id),
        "source": (EventSubscriptionSource, snapshot.source_id),
        "workflow": (Workflow, snapshot.workflow_id),
        "delivery": (EventDelivery, context.prepared.claim.identity.digest),
        "execution": (Execution, context.prepared.execution_id),
        "position": (KafkaPartitionInitialPosition, (snapshot.source_id, 0)),
    }
    saved = {}
    async with context.delivery.session_factory() as session:
        for name, (model, key) in resources.items():
            row = await session.get(model, key)
            assert row is not None
            saved[name] = row.model_dump()
    return saved


@pytest_asyncio.fixture
async def stopped_runtime(scheduling_context):
    context = scheduling_context
    delivery = context.delivery
    snapshot = delivery.snapshot
    worker_id, other_worker_id = uuid4(), uuid4()
    async with delivery.session_factory() as session, session.begin():
        now = (await session.exec(select(func.clock_timestamp()))).one()
        subscription = await session.get(EventSubscription, snapshot.subscription_id)
        workflow = await session.get(Workflow, snapshot.workflow_id)
        assert subscription is not None
        assert workflow is not None
        subscription.desired_enabled = False
        workflow.is_enabled = False
        workflow.published_version_id = None
        subscription.assigned_worker_id = worker_id
        subscription.assignment_lease_until = now - timedelta(seconds=1)
        session.add(
            EventConsumerWorker(
                worker_id=worker_id,
                deployment_id=snapshot.deployment_id,
                heartbeat_until=now - timedelta(seconds=1),
            )
        )
        for participant in (worker_id, other_worker_id):
            session.add(
                EventSubscriptionRuntime(
                    source_id=snapshot.source_id,
                    worker_id=str(participant),
                    configuration_revision=snapshot.configuration_revision,
                    applied_revision=snapshot.configuration_revision,
                    applied_published_version_id=snapshot.published_version_id,
                    runtime_state="active",
                    stopped=False,
                    permanent_content_error=True,
                )
            )
    await hold_partition_recovery(delivery)
    return SimpleNamespace(
        delivery=delivery,
        prepared=context.prepared,
        worker_id=worker_id,
        other_worker_id=other_worker_id,
    )


@pytest.mark.parametrize("content_error", [False, True])
async def test_confirmed_stop_changes_only_the_target_participation(stopped_runtime, *, content_error: bool) -> None:
    context = stopped_runtime
    snapshot = context.delivery.snapshot
    async with context.delivery.session_factory() as session, session.begin():
        runtime = await session.get(EventSubscriptionRuntime, (snapshot.source_id, str(context.worker_id)))
        assert runtime is not None
        runtime.permanent_content_error = content_error
    before = await evidence(context)

    result = await acknowledge(context)

    assert result is not None
    assert result.source_id == snapshot.source_id
    assert result.worker_id == str(context.worker_id)
    assert result.stopped
    assert result.permanent_content_error is content_error
    expected = {
        **before,
        "runtime": {
            **before["runtime"],
            "stopped": True,
            "runtime_state": "stopped",
            "applied_revision": None,
            "applied_published_version_id": None,
        },
    }
    assert await evidence(context) == expected
    assert await acknowledge(context) is None
    assert await evidence(context) == expected


@pytest.mark.parametrize("condition", ["unconfirmed", "heartbeat", "lease", "active", "deployment", "source", "worker"])
async def test_missing_fence_or_unmet_preconditions_cannot_acknowledge(stopped_runtime, condition) -> None:
    context = stopped_runtime
    snapshot = context.delivery.snapshot
    changes: dict[str, object] = {}
    async with context.delivery.session_factory() as session, session.begin():
        now = (await session.exec(select(func.clock_timestamp()))).one()
        if condition == "heartbeat":
            member = await session.get(EventConsumerWorker, context.worker_id)
            assert member is not None
            member.heartbeat_until = now + timedelta(minutes=5)
        elif condition == "lease":
            subscription = await session.get(EventSubscription, snapshot.subscription_id)
            assert subscription is not None
            subscription.assignment_lease_until = now + timedelta(minutes=5)
        elif condition == "active":
            subscription = await session.get(EventSubscription, snapshot.subscription_id)
            workflow = await session.get(Workflow, snapshot.workflow_id)
            assert subscription is not None
            assert workflow is not None
            subscription.desired_enabled = True
            workflow.is_enabled = True
            workflow.published_version_id = snapshot.published_version_id
        elif condition == "unconfirmed":
            changes["worker_fenced"] = False
        else:
            changes[f"{condition}_id"] = uuid4()
    before = await evidence(context)

    assert await acknowledge(context, **changes) is None
    assert await evidence(context) == before
