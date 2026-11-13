"""Normal Execution persistence and recovery without a delivery ledger."""

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlmodel import select

from syntara.core.config.base import Settings
from syntara.core.models import User
from syntara.eventstreams.core.deduplication import (
    DeliveryIdentity,
    TemporalAcceptance,
    TerminalDelivery,
    input_fingerprint,
)
from syntara.eventstreams.core.envelope import RawEvent, WorkflowEventEnvelope
from syntara.eventstreams.core.handler import BlockedDelivery, EventLaunchError, ResolvedDelivery, SchedulingFailureCode
from syntara.eventstreams.core.preparation import AcceptedWorkflow, PreparedExecution
from syntara.eventstreams.core.processing import HeldRecord, SkippedRecord
from syntara.eventstreams.exceptions import EventSubscriptionControlConflictError
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.admission_service import EventAdmissionService
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.eventstreams.services.execution_store import EventExecutionStore
from syntara.eventstreams.services.record_processing_service import EventRecordProcessingService
from syntara.eventstreams.services.subscription_service import EventSubscriptionService, lock_source_lifecycle
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from tests.integration.eventstreams import test_execution_preparation
from tests.integration.eventstreams.conftest import DeliveryContext
from tests.integration.eventstreams.test_execution_preparation import envelope

pytestmark = pytest.mark.integration
preparation_context = test_execution_preparation.preparation_context


class IsolatedTemporal:
    """Keep one stable accepted run; real signing verification is tested in the adapter suite."""

    def __init__(self, context: DeliveryContext) -> None:
        """Receive the database factory used to observe the pre-start boundary."""
        self.context = context
        self.starts: list[PreparedExecution] = []
        self.accepted: AcceptedWorkflow | None = None
        self.lose_response = False
        self.fail_starts = False

    async def lookup(self, identity: DeliveryIdentity, *, run_id: str | None = None) -> AcceptedWorkflow:
        if self.accepted is None or self.accepted.identity != identity:
            raise EventLaunchError(SchedulingFailureCode.TEMPORAL_NOT_FOUND)
        assert run_id is None or run_id == self.accepted.temporal_run_id
        return self.accepted

    async def start(self, prepared: PreparedExecution) -> TemporalAcceptance:
        self.starts.append(prepared)
        async with self.context.session_factory() as session:
            assert await session.get(Execution, prepared.execution_id) is None
        if self.fail_starts:
            raise EventLaunchError(SchedulingFailureCode.TEMPORAL_UNAVAILABLE)
        if self.accepted is None:
            self.accepted = AcceptedWorkflow.model_validate(
                {
                    "identity": prepared.identity,
                    "temporal_run_id": "accepted-run",
                    "arguments": tuple(deepcopy(prepared.workflow_arguments())),
                },
                strict=True,
            )
        if self.accepted.preparation().workflow_arguments() != prepared.workflow_arguments():
            raise EventLaunchError(SchedulingFailureCode.EVIDENCE_MISMATCH)
        if self.lose_response:
            raise EventLaunchError(SchedulingFailureCode.TEMPORAL_UNAVAILABLE)
        return self.accepted.acceptance


@dataclass
class SchedulingContext:
    """Published resources and the actual scheduling/persistence services."""

    delivery: DeliveryContext
    prepared: PreparedExecution
    temporal: IsolatedTemporal
    admission: EventAdmissionService


@pytest_asyncio.fixture
async def scheduling_context(preparation_context: DeliveryContext) -> SchedulingContext:
    context = preparation_context
    prepared = await EventExecutionPreparationService(context.session_factory).prepare_delivery(
        context.snapshot, context.identity(), await envelope(context)
    )
    assert isinstance(prepared, PreparedExecution)
    temporal = IsolatedTemporal(context)
    return SchedulingContext(context, prepared, temporal, EventAdmissionService(context.session_factory, temporal))


@pytest.mark.parametrize("lose_response", [False, True])
async def test_execution_is_saved_only_after_confirmed_acceptance(scheduling_context, *, lose_response) -> None:
    context = scheduling_context
    context.temporal.lose_response = lose_response
    assert isinstance(await context.admission.schedule(context.prepared), ResolvedDelivery)
    async with context.delivery.session_factory() as session:
        execution = await session.get(Execution, context.prepared.execution_id)
        assert execution is not None
        assert execution.input_data == context.prepared.input_data
        assert execution.created_by == context.prepared.binding.execution_principal_id
    assert isinstance(await context.admission.recover_accepted(context.prepared.identity), ResolvedDelivery)
    assert len(context.temporal.starts) == 1


async def test_failed_start_creates_no_execution(scheduling_context) -> None:
    context = scheduling_context
    context.temporal.fail_starts = True
    result = await context.admission.schedule(context.prepared)
    assert not isinstance(result, ResolvedDelivery)
    async with context.delivery.session_factory() as session:
        assert await session.get(Execution, context.prepared.execution_id) is None


async def test_competing_start_recovers_the_first_accepted_arguments(scheduling_context) -> None:
    context = scheduling_context
    await context.temporal.start(context.prepared)
    replacement_input = {**context.prepared.input_data, "payload": {"count": 3}}
    replacement = context.prepared.model_copy(
        update={
            "input_data": replacement_input,
            "binding": context.prepared.binding.model_copy(
                update={
                    "input_fingerprint": input_fingerprint(replacement_input, context.prepared.workflow_metadata),
                }
            ),
        }
    )
    result = await context.admission.schedule(replacement)
    assert isinstance(result, ResolvedDelivery)
    async with context.delivery.session_factory() as session:
        execution = await session.get(Execution, context.prepared.execution_id)
        assert execution is not None
        assert execution.input_data == context.prepared.input_data
        assert execution.execution_metadata["event_delivery"]["input_fingerprint"] == (
            context.prepared.binding.input_fingerprint
        )


async def test_accepted_write_failure_retries_same_arguments_without_another_start(
    scheduling_context, monkeypatch
) -> None:
    context = scheduling_context
    original = EventExecutionStore.persist
    attempts = []

    async def fail_once(
        store: EventExecutionStore, prepared: PreparedExecution, accepted: TemporalAcceptance
    ) -> TerminalDelivery:
        attempts.append(prepared.workflow_arguments())
        result = await original(store, prepared, accepted)
        if len(attempts) == 1:
            statement = "lost persistence response"
            raise OperationalError(statement, {}, RuntimeError("PRIVATE"))
        return result

    monkeypatch.setattr(EventExecutionStore, "persist", fail_once)
    assert isinstance(await context.admission.schedule(context.prepared), ResolvedDelivery)
    assert len(attempts) == 2
    assert attempts[0] == attempts[1]
    assert len(context.temporal.starts) == 1


async def test_delete_guard_preserves_an_accepted_run_without_an_execution(scheduling_context) -> None:
    context = scheduling_context
    snapshot = context.delivery.snapshot
    await context.temporal.start(context.prepared)
    async with context.delivery.session_factory() as session, session.begin():
        lifecycle = await lock_source_lifecycle(session, snapshot.source_id)
        assert lifecycle is not None
        subscription, source = lifecycle
        source.initialized_at = context.prepared.binding.prepared_at
        subscription.desired_enabled = False
        workflow = await session.get(Workflow, snapshot.workflow_id)
        assert workflow is not None
        workflow.is_enabled = False
        workflow.published_version_id = None
    with pytest.raises(EventSubscriptionControlConflictError, match="handoff_safety_unproven"):
        async with context.delivery.session_factory() as session, session.begin():
            workflow = await session.get(Workflow, snapshot.workflow_id)
            assert workflow is not None
            user = await session.get(User, workflow.created_by)
            assert user is not None
            assert await session.get(Execution, context.prepared.execution_id) is None
            await EventSubscriptionService(session, user).assert_workflow_not_bound(workflow.id, workflow.name)
    # Stopping intake must still permit recording the original accepted run.
    repaired = await context.admission.recover_accepted(context.prepared.identity)
    assert isinstance(repaired, ResolvedDelivery)
    async with context.delivery.session_factory() as session:
        assert await session.get(WorkflowVersion, context.prepared.workflow_version_id) is not None
        assert await session.get(Execution, context.prepared.execution_id) is not None


@pytest.mark.parametrize("status", list(ExecutionStatus))
async def test_repeated_persistence_preserves_execution_status(scheduling_context, status) -> None:
    context = scheduling_context
    acceptance = await context.temporal.start(context.prepared)
    assert isinstance(await context.admission._confirm(context.prepared, acceptance), ResolvedDelivery)
    async with context.delivery.session_factory() as session, session.begin():
        execution = await session.get(Execution, context.prepared.execution_id)
        assert execution is not None
        execution.status = status
    assert isinstance(await context.admission._confirm(context.prepared, acceptance), ResolvedDelivery)
    async with context.delivery.session_factory() as session:
        execution = await session.get(Execution, context.prepared.execution_id)
        assert execution is not None
        assert execution.status == status


async def test_matching_redelivery_recovers_original_version_input_and_principal_after_duplicate_start(
    scheduling_context: SchedulingContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = scheduling_context
    await context.temporal.start(context.prepared)
    async with context.delivery.session_factory() as session, session.begin():
        workflow = await session.get(Workflow, context.prepared.identity.workflow_id)
        subscription = await session.get(EventSubscription, context.prepared.identity.subscription_id)
        source = await session.get(EventSubscriptionSource, context.prepared.identity.source_id)
        old = await session.get(WorkflowVersion, context.prepared.workflow_version_id)
        assert workflow is not None
        assert subscription is not None
        assert source is not None
        assert old is not None
        replacement = WorkflowVersion(
            workflow_id=workflow.id,
            version=old.version + 1,
            schema_version=old.schema_version,
            created_by=workflow.created_by,
            workflow_definition=old.workflow_definition,
        )
        session.add(replacement)
        await session.flush()
        workflow.published_version_id = subscription.published_version_id = replacement.id
        subscription.configuration_revision += 1
        subscription.input_schema = {"type": "object"}
        subscription.filter = {"expression": "true"}
        snapshot = SubscriptionSnapshot.from_models(subscription, source)
    preparation = EventExecutionPreparationService(context.delivery.session_factory)
    prepare = AsyncMock(wraps=preparation.prepare_delivery)
    monkeypatch.setattr(preparation, "prepare_delivery", prepare)
    original_lookup = context.temporal.lookup

    async def lookup(identity: DeliveryIdentity, *, run_id: str | None = None) -> AcceptedWorkflow:
        assert len(context.temporal.starts) == 2  # No lookup before the competing direct start.
        return await original_lookup(identity, run_id=run_id)

    monkeypatch.setattr(context.temporal, "lookup", lookup)
    admission = EventAdmissionService(context.delivery.session_factory, context.temporal)
    processing = EventRecordProcessingService(context.delivery.session_factory, preparation, admission)
    raw = RawEvent(
        value=b'{"count":3}',
        source_metadata=WorkflowEventEnvelope.model_validate(context.prepared.input_data).source_metadata,
    )
    with patch.object(Settings, "service_identity", new_callable=PropertyMock, return_value="replacement.ao.svc"):
        result = await processing.process(snapshot, context.prepared.identity, raw)
    assert isinstance(result, ResolvedDelivery)
    prepare.assert_awaited_once()
    assert len(context.temporal.starts) == 2
    async with context.delivery.session_factory() as session:
        execution = await session.get(Execution, context.prepared.execution_id)
        assert execution is not None
        assert execution.workflow_version_id == context.prepared.workflow_version_id
        assert execution.input_data == context.prepared.input_data
        assert execution.created_by == context.prepared.binding.execution_principal_id


@pytest.mark.parametrize("expression", ["false", "input.payload.value.count"])
async def test_changed_filter_after_crash_can_leave_accepted_execution_unrepaired(
    scheduling_context, monkeypatch, expression
) -> None:
    context = scheduling_context
    await context.temporal.start(context.prepared)
    async with context.delivery.session_factory() as session, session.begin():
        subscription = await session.get(EventSubscription, context.prepared.identity.subscription_id)
        source = await session.get(EventSubscriptionSource, context.prepared.identity.source_id)
        assert subscription is not None
        assert source is not None
        subscription.filter = {"expression": expression}
        subscription.configuration_revision += 1
        snapshot = SubscriptionSnapshot.from_models(subscription, source)
    forbidden = Mock(side_effect=AssertionError("Local filter outcomes must not access execution services"))
    processing = EventRecordProcessingService(forbidden, forbidden, forbidden)
    raw = RawEvent(
        value=b'{"count":2}',
        source_metadata=WorkflowEventEnvelope.model_validate(context.prepared.input_data).source_metadata,
    )
    lookup = AsyncMock(side_effect=AssertionError("Local filter outcomes must not access Temporal"))
    monkeypatch.setattr(context.temporal, "lookup", lookup)
    result = await processing.process(snapshot, context.prepared.identity, raw)
    assert isinstance(result, SkippedRecord)
    assert result.outcome == ("no_match" if expression == "false" else "evaluation_error")
    forbidden.assert_not_called()
    lookup.assert_not_awaited()
    assert len(context.temporal.starts) == 1
    async with context.delivery.session_factory() as session:
        assert await session.get(Execution, context.prepared.execution_id) is None


async def test_accepted_repair_retries_after_database_outage_without_starting_again(
    scheduling_context, monkeypatch
) -> None:
    context = scheduling_context
    await context.temporal.start(context.prepared)
    original = EventExecutionStore.persist
    statement = "database unavailable"
    monkeypatch.setattr(
        EventExecutionStore, "persist", AsyncMock(side_effect=OperationalError(statement, {}, RuntimeError("PRIVATE")))
    )
    assert isinstance(await context.admission.recover_accepted(context.prepared.identity), BlockedDelivery)
    monkeypatch.setattr(EventExecutionStore, "persist", original)
    assert isinstance(await context.admission.recover_accepted(context.prepared.identity), ResolvedDelivery)
    assert len(context.temporal.starts) == 1


@pytest.mark.parametrize(
    "code",
    [
        SchedulingFailureCode.TEMPORAL_UNAVAILABLE,
        SchedulingFailureCode.HISTORY_UNAVAILABLE,
        SchedulingFailureCode.EVIDENCE_MISMATCH,
    ],
)
async def test_uncertain_history_never_starts_or_discards_the_record(scheduling_context, monkeypatch, code) -> None:
    context = scheduling_context
    monkeypatch.setattr(context.temporal, "lookup", AsyncMock(side_effect=EventLaunchError(code)))
    processing = EventRecordProcessingService(
        context.delivery.session_factory,
        EventExecutionPreparationService(context.delivery.session_factory),
        context.admission,
    )
    result = await processing.process(context.delivery.snapshot, context.prepared.identity, None)
    assert isinstance(result, HeldRecord)
    assert not result.permanent_content_error
    assert context.temporal.starts == []


async def test_concurrent_confirmation_keeps_one_execution(scheduling_context) -> None:
    context = scheduling_context
    acceptance = await context.temporal.start(context.prepared)
    results = await asyncio.gather(*(context.admission._confirm(context.prepared, acceptance) for _ in range(2)))
    assert all(isinstance(result, ResolvedDelivery) for result in results)
    async with context.delivery.session_factory() as session:
        executions = (await session.exec(select(Execution).where(Execution.id == context.prepared.execution_id))).all()
        assert len(executions) == 1


async def test_conflicting_execution_evidence_does_not_allow_another_start(scheduling_context) -> None:
    context = scheduling_context
    assert isinstance(await context.admission.schedule(context.prepared), ResolvedDelivery)
    async with context.delivery.session_factory() as session, session.begin():
        execution = await session.get(Execution, context.prepared.execution_id)
        assert execution is not None
        execution.input_data = {**execution.input_data, "payload": {"count": 999}}
    result = await context.admission.recover_accepted(context.prepared.identity)
    assert isinstance(result, BlockedDelivery)
    assert result.error_code == SchedulingFailureCode.EVIDENCE_MISMATCH
    assert len(context.temporal.starts) == 1
