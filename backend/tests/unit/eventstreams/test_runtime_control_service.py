"""Register before startup and persist only verified local lifecycle results."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.core.runtime import RuntimeRevision, RuntimeState, SubscriptionRuntimeStatus
from syntara.eventstreams.models.control import EventSubscriptionRuntime
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services import runtime_control_service as module
from syntara.eventstreams.services.runtime_control_service import EventRuntimeControlService
from tests.unit.eventstreams.test_subscription_snapshot import _source, _subscription


@pytest.fixture
def context(monkeypatch):
    subscription = _subscription()
    source = _source(subscription)
    snapshot = SubscriptionSnapshot.from_models(subscription, source)
    session = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    session.exec.return_value = MagicMock()
    session.exec.return_value.first.return_value = None
    monkeypatch.setattr(module, "lock_source_lifecycle", AsyncMock(return_value=(subscription, source)))
    return SimpleNamespace(
        subscription=subscription,
        source=source,
        snapshot=snapshot,
        session=session,
        service=EventRuntimeControlService(MagicMock(return_value=session), "worker"),
    )


@pytest.mark.parametrize("changed", ["paused", "retired", "unpublished", "revision", "content_gate"])
async def test_stale_workers_cannot_register_or_open_a_client(context, changed):
    workflow = SimpleNamespace(is_enabled=True, published_version_id=context.subscription.published_version_id)
    if changed in {"paused", "retired"}:
        setattr(context.subscription, changed, True)
    elif changed == "unpublished":
        workflow.is_enabled = False
    elif changed == "content_gate":
        context.session.exec.return_value.first.return_value = "previous-worker"
    else:
        context.subscription.configuration_revision += 1
    context.session.get.return_value = workflow
    assert not await context.service.register(context.snapshot)
    context.session.add.assert_not_called()


async def test_successful_registration_precedes_any_applied_claim(context):
    context.session.get.side_effect = [
        SimpleNamespace(is_enabled=True, published_version_id=context.snapshot.published_version_id),
        None,
    ]
    assert await context.service.register(context.snapshot)
    row = context.session.add.call_args.args[0]
    assert row.configuration_revision == context.snapshot.configuration_revision
    assert row.applied_revision is None
    assert not row.stopped


@pytest.mark.parametrize("state", [RuntimeState.DRAINING, RuntimeState.STOPPED])
async def test_only_verified_stop_acknowledges_shutdown_and_keeps_content_gate(context, state):
    row = EventSubscriptionRuntime(source_id=context.source.id, worker_id="worker", configuration_revision=1)
    context.session.get.return_value = row
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
