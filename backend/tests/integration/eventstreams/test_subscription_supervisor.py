"""Persisted supervision/recovery boundaries with isolated runners and Temporal."""

from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from syntara.core.models.user import User
from syntara.core.services.secret_service import create_secret_service
from syntara.credentials.models.credential import Credential
from syntara.eventstreams.core.deduplication import DeliveryState
from syntara.eventstreams.core.handler import ResolvedDelivery
from syntara.eventstreams.core.processing import HeldRecord
from syntara.eventstreams.core.results import EventFailureCode
from syntara.eventstreams.core.runtime import RuntimeRevision, RuntimeState
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.eventstreams.services.record_processing_service import EventRecordProcessingService
from syntara.eventstreams.services.subscription_service import EventSubscriptionService, lock_source_lifecycle
from syntara.eventstreams.services.subscription_supervisor import SubscriptionSupervisor
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from tests.helpers.eventstream_runtime import IsolatedSubscriptionRunner
from tests.integration.eventstreams import test_execution_scheduling
from tests.integration.eventstreams.test_execution_scheduling import SchedulingContext

pytestmark = pytest.mark.integration
scheduling_context = test_execution_scheduling.scheduling_context


async def persisted_snapshot(context: SchedulingContext) -> SubscriptionSnapshot:
    async with context.delivery.session_factory() as session:
        subscription = await session.get(EventSubscription, context.delivery.snapshot.subscription_id)
        source = await session.get(EventSubscriptionSource, context.delivery.snapshot.source_id)
        assert subscription is not None
        assert source is not None
        return SubscriptionSnapshot.from_models(subscription, source)


async def change_lifecycle(context: SchedulingContext, change: str) -> SubscriptionSnapshot:
    async with context.delivery.session_factory() as session, session.begin():
        lifecycle = await lock_source_lifecycle(session, context.delivery.snapshot.source_id)
        assert lifecycle is not None
        subscription, source = lifecycle
        workflow = await session.get(Workflow, subscription.workflow_id)
        assert workflow is not None
        subscription.configuration_revision += 1
        if change == "paused":
            subscription.paused = True
        elif change == "unpublished":
            workflow.is_enabled = subscription.desired_enabled = False
            workflow.published_version_id = None
        elif change == "retired":
            subscription.retired = True
            subscription.desired_enabled = False
            source.retired_at = datetime.now(UTC)
        else:
            assert change == "resumed"
            subscription.paused = False
            subscription.desired_enabled = workflow.is_enabled = True
            workflow.published_version_id = subscription.published_version_id
    return await persisted_snapshot(context)


@pytest_asyncio.fixture
async def runtime(scheduling_context):
    trace, runners = [], []

    def construct(snapshot) -> IsolatedSubscriptionRunner:
        runner = IsolatedSubscriptionRunner(snapshot, trace)
        runners.append(runner)
        return runner

    factory = AsyncMock(side_effect=construct)
    supervisor = SubscriptionSupervisor(scheduling_context.delivery.snapshot.subscription_id, factory)
    try:
        yield SimpleNamespace(
            context=scheduling_context, supervisor=supervisor, factory=factory, runners=runners, trace=trace
        )
    finally:
        await supervisor.stop()


@pytest.mark.parametrize("lifecycle", ["paused", "unpublished", "retired"])
async def test_inactive_consumer_teardown_keeps_prepared_recovery_discoverable(runtime, lifecycle):
    context, supervisor = runtime.context, runtime.supervisor
    original = await persisted_snapshot(context)
    await supervisor.apply(original)
    await supervisor.apply(await persisted_snapshot(context))
    runtime.factory.assert_awaited_once()
    inactive = await change_lifecycle(context, lifecycle)
    status = await supervisor.apply(inactive)
    assert status.state == RuntimeState.STOPPED
    assert status.applied_revision is None
    assert not runtime.runners[0].accepting
    assert runtime.runners[0].stopped
    assert inactive.source_id == original.source_id
    assert inactive.configuration == original.configuration
    async with context.delivery.session_factory() as session:
        row = await session.get(EventDelivery, context.prepared.claim.identity.digest)
        execution = await session.get(Execution, context.prepared.execution_id)
        assert row is not None
        assert execution is not None
        assert row.state == DeliveryState.IN_PROGRESS
        assert row.claim_token == context.prepared.claim.token
        assert row.frozen_binding == context.prepared.claim.binding
        assert execution.workflow_version_id == original.published_version_id
        assert execution.input_data == context.prepared.input_data
    await context.delivery.expire(context.prepared.claim)
    recovered = await context.recovery.recover_due("after-consumer-stop", limit=1)
    assert len(recovered) == 1
    assert isinstance(recovered[0][1], ResolvedDelivery)
    assert supervisor.status.state == RuntimeState.STOPPED
    runtime.factory.assert_awaited_once()  # No Kafka client is constructed to repair frozen work.
    assert len(context.temporal.starts) == 1
    assert context.temporal.starts[0].workflow_arguments() == context.prepared.workflow_arguments()
    async with context.delivery.session_factory() as session:
        row = await session.get(EventDelivery, context.prepared.claim.identity.digest)
        execution = await session.get(Execution, context.prepared.execution_id)
        assert row.state == DeliveryState.SCHEDULED
        assert row.frozen_binding == context.prepared.claim.binding
        assert execution.input_data == context.prepared.input_data
        assert execution.execution_metadata["event_delivery"]["scheduling_state"] == "confirmed"


@pytest.mark.parametrize("lifecycle", ["paused", "unpublished"])
async def test_persisted_resume_reuses_the_source_generation_and_group(runtime, lifecycle):
    context, supervisor = runtime.context, runtime.supervisor
    original = await persisted_snapshot(context)
    await supervisor.apply(original)
    await supervisor.apply(await change_lifecycle(context, lifecycle))
    resumed = await change_lifecycle(context, "resumed")
    status = await supervisor.apply(resumed)
    assert status.state == RuntimeState.ACTIVE
    assert resumed.source_id == original.source_id
    assert resumed.source_generation == original.source_generation
    assert resumed.configuration == original.configuration
    assert runtime.runners[0].stopped
    assert runtime.runners[1].snapshot == resumed
    assert runtime.factory.await_count == 2


async def test_publication_replacement_keeps_prepared_version_credential_and_input(runtime):
    context, supervisor = runtime.context, runtime.supervisor
    original = await persisted_snapshot(context)
    await supervisor.apply(original)
    async with context.delivery.session_factory() as session, session.begin():
        lifecycle = await lock_source_lifecycle(session, original.source_id)
        assert lifecycle is not None
        workflow = await session.get(Workflow, original.workflow_id)
        version = await session.get(WorkflowVersion, original.published_version_id)
        credential = await session.get(Credential, original.runtime_credential_id)
        actor = await session.get(User, original.enabled_by)
        assert workflow is not None
        assert version is not None
        assert credential is not None
        assert actor is not None
        replacement_credential = Credential(
            name="supervisor-replacement",
            credential_type_id=credential.credential_type_id,
            project_id=credential.project_id,
            created_by=actor.id,
            enabled=True,
            secret_id=await create_secret_service(session).create_secret(
                {"username": "replacement", "password": "test"}
            ),
        )
        session.add(replacement_credential)
        await session.flush()
        definition = deepcopy(version.workflow_definition)
        definition["triggers"][0]["parameters"]["credential_id"] = str(replacement_credential.id)
        replacement_version = WorkflowVersion(
            workflow_id=workflow.id,
            version=2,
            schema_version=version.schema_version,
            workflow_definition=definition,
            created_by=actor.id,
        )
        session.add(replacement_version)
        await session.flush()
        changes = await EventSubscriptionService(session, actor).sync_from_published_definition(
            workflow, replacement_version, enabled=True
        )
        workflow.published_version_id = replacement_version.id
        workflow.current_version = 2
        replacement = changes.updated[0]
    await supervisor.apply(replacement)
    assert runtime.trace.index(("stop", RuntimeRevision.from_snapshot(original))) < runtime.trace.index(
        ("start", RuntimeRevision.from_snapshot(replacement))
    )
    assert replacement.runtime_credential_id != original.runtime_credential_id
    assert replacement.source_id == original.source_id
    assert replacement.configuration == original.configuration
    await context.delivery.expire(context.prepared.claim)
    result = await context.recovery.recover_due("after-republication", limit=1)
    assert isinstance(result[0][1], ResolvedDelivery)
    recovered = context.temporal.starts[0]
    assert recovered.claim.binding == context.prepared.claim.binding
    assert recovered.workflow_version_id == original.published_version_id
    assert recovered.input_data == context.prepared.input_data
    assert recovered.workflow_arguments() == context.prepared.workflow_arguments()


async def test_pause_resume_preserves_durable_permanent_content_evidence(runtime):
    context, supervisor = runtime.context, runtime.supervisor
    claim = await context.delivery.claim(offset=10)
    async with context.delivery.session_factory() as session, session.begin():
        assert (
            await context.delivery.store(session).defer(
                claim, error_code=EventFailureCode.invalid_json.value, next_attempt_at=datetime.max.replace(tzinfo=UTC)
            )
            is None
        )
    async with context.delivery.session_factory() as session:
        row = await session.get(EventDelivery, claim.identity.digest)
        retained = row.model_dump()
    await supervisor.apply(await persisted_snapshot(context))
    await supervisor.apply(await change_lifecycle(context, "paused"))
    resumed = await change_lifecycle(context, "resumed")
    await supervisor.apply(resumed)
    processing = EventRecordProcessingService(
        context.delivery.session_factory,
        EventExecutionPreparationService(context.delivery.session_factory),
        context.admission,
    )
    held = await processing.process(resumed, claim.identity, None, "resumed")
    assert isinstance(held, HeldRecord)
    assert held.permanent_content_error
    assert held.retry_at is None
    assert held.reason == "activity_log_unavailable"
    async with context.delivery.session_factory() as session:
        row = await session.get(EventDelivery, claim.identity.digest)
        assert row.model_dump() == retained
        assert row.state == DeliveryState.IN_PROGRESS
        assert row.frozen_binding is None
    assert context.temporal.starts == []
