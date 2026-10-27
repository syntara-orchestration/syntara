"""Register before startup and persist only verified local lifecycle results."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.core.placement import SubscriptionPlacementLease, WorkerIdentity
from syntara.eventstreams.core.runtime import RuntimeRevision, RuntimeState, SubscriptionRuntimeStatus
from syntara.eventstreams.models.consumer_worker import EventConsumerWorker
from syntara.eventstreams.models.control import EventSubscriptionRuntime
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services import runtime_control_service as module
from syntara.eventstreams.services.runtime_control_service import EventRuntimeControlService
from syntara.workflows.models.workflow import Workflow
from tests.unit.eventstreams.test_deduplication_store import NOW
from tests.unit.eventstreams.test_subscription_snapshot import _source, _subscription


@pytest.fixture
def context(monkeypatch):
    subscription = _subscription()
    source = _source(subscription)
    snapshot = SubscriptionSnapshot.from_models(subscription, source)
    worker = WorkerIdentity(deployment_id=source.deployment_id)
    subscription.assigned_worker_id = worker.worker_id
    subscription.assignment_lease_until = NOW + timedelta(seconds=60)
    member = EventConsumerWorker(
        worker_id=worker.worker_id,
        deployment_id=worker.deployment_id,
        heartbeat_until=subscription.assignment_lease_until,
    )
    lease = SubscriptionPlacementLease(
        subscription_id=subscription.id, owner=worker, confirmed_at=NOW, expires_at=subscription.assignment_lease_until
    )
    session = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    monkeypatch.setattr(module, "lock_source_lifecycle", AsyncMock(return_value=(subscription, source)))
    context = SimpleNamespace(
        subscription=subscription,
        source=source,
        snapshot=snapshot,
        session=session,
        worker=worker,
        lease=lease,
        member=member,
        members=[member],
        row=None,
        content_gate=None,
        workflow=SimpleNamespace(
            is_enabled=True, published_version_id=snapshot.published_version_id, project_id=subscription.project_id
        ),
        service=EventRuntimeControlService(MagicMock(return_value=session), worker),
    )

    def get(model, *_args: object, **_kwargs: object) -> object:
        return context.workflow if model is Workflow else context.row

    def execute(statement) -> MagicMock:
        result = MagicMock()
        result.all.return_value = [(item, NOW) for item in context.members]
        result.first.return_value = context.content_gate
        return result

    session.get.side_effect = get
    session.exec.side_effect = execute
    return context


@pytest.mark.parametrize(
    "changed",
    [
        "paused",
        "retired",
        "unpublished",
        "revision",
        "content_gate",
        "takeover",
        "expired_lease",
        "expired_member",
        "draining",
        "deployment",
        "project",
    ],
)
async def test_stale_workers_cannot_register_or_open_a_client(context, changed):
    if changed in {"paused", "retired"}:
        setattr(context.subscription, changed, True)
    elif changed == "unpublished":
        context.workflow.is_enabled = False
    elif changed == "content_gate":
        context.content_gate = "previous-worker"
    elif changed == "takeover":
        context.subscription.assigned_worker_id = uuid4()
    elif changed == "expired_lease":
        context.subscription.assignment_lease_until = NOW
    elif changed == "expired_member":
        context.member.heartbeat_until = NOW
    elif changed == "draining":
        context.member.draining = True
    elif changed == "deployment":
        context.member.deployment_id = uuid4()
    elif changed == "project":
        context.workflow.project_id = uuid4()
    else:
        context.subscription.configuration_revision += 1
    assert not await context.service.register(context.snapshot, context.lease)
    context.session.add.assert_not_called()


async def test_successful_registration_precedes_any_applied_claim(context):
    before = context.subscription.model_dump()
    assert await context.service.register(context.snapshot, context.lease)
    row = context.session.add.call_args.args[0]
    assert row.configuration_revision == context.snapshot.configuration_revision
    assert row.applied_revision is None
    assert not row.stopped
    assert row.worker_id == str(context.worker.worker_id)
    assert row.runtime_state == "starting"
    assert context.subscription.model_dump() == before


@pytest.mark.parametrize("state", [RuntimeState.DRAINING, RuntimeState.STOPPED])
async def test_only_verified_stop_acknowledges_shutdown_and_keeps_content_gate(context, state):
    row = EventSubscriptionRuntime(
        source_id=context.source.id, worker_id=str(context.worker.worker_id), configuration_revision=1
    )
    context.row = row
    context.subscription.assignment_lease_until = NOW
    context.member.heartbeat_until = NOW
    await context.service.acknowledge(
        context.snapshot,
        SubscriptionRuntimeStatus(
            subscription_id=context.subscription.id,
            state=state,
            desired_revision=RuntimeRevision.from_snapshot(context.snapshot),
            desired_active=False,
            applied_revision=None,
            permanent_content_error=True,
        ),
    )
    assert row.stopped is (state == RuntimeState.STOPPED)
    assert row.permanent_content_error


@pytest.mark.parametrize("changed", ["owner", "lease", "revision", "desired", "project"])
async def test_stale_start_acknowledgement_cannot_reopen_stopped_participation(context, changed):
    context.row = EventSubscriptionRuntime(
        source_id=context.source.id, worker_id=str(context.worker.worker_id), configuration_revision=1, stopped=True
    )
    status = SubscriptionRuntimeStatus(
        subscription_id=context.subscription.id,
        state=RuntimeState.ACTIVE,
        desired_revision=RuntimeRevision.from_snapshot(context.snapshot),
        desired_active=True,
        applied_revision=RuntimeRevision.from_snapshot(context.snapshot),
    )
    if changed == "owner":
        context.subscription.assigned_worker_id = uuid4()
    elif changed == "lease":
        context.subscription.assignment_lease_until += timedelta(seconds=20)
    elif changed == "revision":
        context.subscription.configuration_revision += 1
    elif changed == "project":
        context.workflow.project_id = uuid4()
    else:
        context.subscription.paused = True
    await context.service.acknowledge(context.snapshot, status, lease=context.lease)
    assert context.row.stopped
    assert context.row.applied_revision is None


@pytest.mark.parametrize("state", [RuntimeState.STARTING, RuntimeState.ACTIVE])
async def test_current_owner_reports_runtime_state_separately_from_applied_configuration(context, state):
    context.row = EventSubscriptionRuntime(
        source_id=context.source.id, worker_id=str(context.worker.worker_id), configuration_revision=1
    )
    status = SubscriptionRuntimeStatus(
        subscription_id=context.subscription.id,
        state=state,
        desired_revision=RuntimeRevision.from_snapshot(context.snapshot),
        desired_active=True,
        applied_revision=RuntimeRevision.from_snapshot(context.snapshot),
    )
    before = context.subscription.model_dump()
    await context.service.acknowledge(context.snapshot, status, lease=context.lease)
    assert context.row.applied_revision == 1
    assert context.row.runtime_state == state.value
    assert context.subscription.model_dump() == before


async def test_old_registration_cannot_reset_stopped_evidence_after_takeover(context):
    context.row = EventSubscriptionRuntime(
        source_id=context.source.id, worker_id=str(context.worker.worker_id), configuration_revision=1, stopped=True
    )
    context.subscription.assigned_worker_id = uuid4()
    assert not await context.service.register(context.snapshot, context.lease)
    assert context.row.stopped


async def test_renewed_lease_can_acknowledge_without_new_configuration_or_actor(context):
    context.subscription.assignment_lease_until += timedelta(seconds=20)
    renewed = context.lease.model_copy(update={"expires_at": context.subscription.assignment_lease_until})
    context.row = EventSubscriptionRuntime(
        source_id=context.source.id, worker_id=str(context.worker.worker_id), configuration_revision=1
    )
    status = SubscriptionRuntimeStatus(
        subscription_id=context.subscription.id,
        state=RuntimeState.ACTIVE,
        desired_revision=RuntimeRevision.from_snapshot(context.snapshot),
        desired_active=True,
        applied_revision=RuntimeRevision.from_snapshot(context.snapshot),
    )
    before = context.subscription.model_dump()
    await context.service.acknowledge(context.snapshot, status, lease=renewed)
    assert context.row.applied_revision == 1
    assert context.subscription.model_dump() == before


async def test_old_revision_still_retains_a_known_permanent_content_gate(context):
    context.row = EventSubscriptionRuntime(
        source_id=context.source.id, worker_id=str(context.worker.worker_id), configuration_revision=2
    )
    status = SubscriptionRuntimeStatus(
        subscription_id=context.subscription.id,
        state=RuntimeState.STOPPED,
        desired_revision=RuntimeRevision.from_snapshot(context.snapshot),
        desired_active=False,
        applied_revision=None,
        permanent_content_error=True,
    )
    await context.service.acknowledge(context.snapshot, status)
    assert context.row.permanent_content_error
    assert not context.row.stopped
