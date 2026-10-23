"""PostgreSQL scheduling/recovery boundaries with an isolated Temporal adapter."""

from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import event, func, update
from sqlalchemy.exc import OperationalError
from sqlmodel import col, select

from syntara.core.services.secret_service import create_secret_service
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.eventstreams.core.deduplication import ClaimLost, DeliveryClaim, DeliveryState, TemporalAcceptance
from syntara.eventstreams.core.handler import (
    BlockedDelivery,
    EventLaunchError,
    ResolvedDelivery,
    RetryDelivery,
    SchedulingFailureCode,
)
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.services.admission_service import EventAdmissionService
from syntara.eventstreams.services.deduplication_store import EventDeliveryStore
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.eventstreams.services.recovery_service import EventExecutionRecoveryService
from syntara.integrations.models.integration import Integration
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from tests.integration.eventstreams.conftest import AvailableCapacity, DeliveryContext
from tests.integration.eventstreams.test_execution_preparation import envelope

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.engine import Connection
    from sqlalchemy.orm import Session
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.eventstreams.core.deduplication import TerminalDelivery

pytestmark = pytest.mark.integration


class IsolatedTemporal:
    """One stable run plus finite failures; never a substitute for live Temporal verification."""

    def __init__(self, context: DeliveryContext) -> None:
        """Retain one acceptance and a bounded set of test failure controls."""
        self.context = context
        self.starts: list[PreparedExecution] = []
        self.accepted: TemporalAcceptance | None = None
        self.fail_starts = False
        self.lose_response = False
        self.before_first_start: Callable[[], Awaitable[None]] | None = None

    async def history_retention_seconds(self) -> int:
        return 259200

    async def describe(self, prepared: PreparedExecution) -> TemporalAcceptance:
        if self.accepted is None:
            raise EventLaunchError(SchedulingFailureCode.TEMPORAL_NOT_FOUND)
        assert self.accepted.execution_id == prepared.execution_id
        assert prepared.claim.binding is not None
        assert self.accepted.input_fingerprint == prepared.claim.binding.input_fingerprint
        return self.accepted

    async def start(self, prepared: PreparedExecution) -> TemporalAcceptance:
        assert prepared.claim.binding is not None
        self.starts.append(prepared)
        # A separate session can see committed attempt evidence before this RPC.
        async with self.context.session_factory() as session:
            row = await session.get(EventDelivery, prepared.claim.identity.digest)
            execution = await session.get(Execution, prepared.execution_id)
            assert row is not None
            assert execution is not None
            assert execution.execution_metadata is not None
            assert row.attempt_count == prepared.claim.attempt_count > 0
            assert row.first_start_attempt_at is not None
            assert row.start_retry_deadline is not None
            assert execution.input_data == prepared.input_data
            assert execution.execution_metadata["event_delivery"]["attempt_count"] == row.attempt_count
            assert UUID(execution.execution_metadata["event_delivery"]["start_attempt_id"])
        if len(self.starts) == 1 and self.before_first_start is not None:
            await self.before_first_start()
        if self.fail_starts:
            raise EventLaunchError(SchedulingFailureCode.TEMPORAL_UNAVAILABLE)
        if self.accepted is None:
            self.accepted = TemporalAcceptance(
                execution_id=prepared.execution_id,
                temporal_workflow_id=prepared.temporal_workflow_id,
                temporal_run_id="one-accepted-run",
                input_fingerprint=prepared.claim.binding.input_fingerprint,
            )
        if self.lose_response:
            raise EventLaunchError(SchedulingFailureCode.TEMPORAL_UNAVAILABLE)
        return self.accepted


@dataclass
class SchedulingContext:
    """Committed prerequisite resources and finite scheduling/recovery services."""

    delivery: DeliveryContext
    prepared: PreparedExecution
    temporal: IsolatedTemporal
    admission: EventAdmissionService
    recovery: EventExecutionRecoveryService


@pytest_asyncio.fixture
async def scheduling_context(delivery_context: DeliveryContext) -> SchedulingContext:
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
    admission = EventAdmissionService(context.session_factory, temporal)
    return SchedulingContext(
        context, prepared, temporal, admission, EventExecutionRecoveryService(context.session_factory, admission)
    )


async def test_attempt_commits_before_rpc_and_resolution_is_atomic(scheduling_context) -> None:
    context = scheduling_context
    result = await context.admission.schedule(context.prepared)
    assert isinstance(result, ResolvedDelivery)
    async with context.delivery.session_factory() as session:
        row = await session.get(EventDelivery, context.prepared.claim.identity.digest)
        execution = await session.get(Execution, context.prepared.execution_id)
        assert row.state == DeliveryState.SCHEDULED
        assert row.temporal_run_id == result.terminal.temporal_run_id
        assert row.execution_confirmed_at == result.terminal.execution_confirmed_at
        assert execution.execution_metadata["event_delivery"]["scheduling_state"] == "confirmed"
        assert execution.created_by == context.delivery.principal_id
        assert (await session.exec(select(func.count()).select_from(Execution))).one() == 1


async def test_lost_start_response_verifies_same_identity(scheduling_context) -> None:
    context = scheduling_context
    context.temporal.lose_response = True
    assert isinstance(await context.admission.schedule(context.prepared), ResolvedDelivery)
    assert len(context.temporal.starts) == 1


async def test_lost_attempt_commit_response_reconciles_own_evidence(scheduling_context) -> None:
    context = scheduling_context
    failed = False
    failure = OperationalError("commit response", {}, RuntimeError("PRIVATE"))

    def factory() -> AsyncSession:
        session: AsyncSession = context.delivery.session_factory()

        def before_commit(sync_session: Session) -> None:
            if not failed:
                execution = sync_session.get(Execution, context.prepared.execution_id)
                sync_session.info["attempt_recorded"] = bool(
                    execution is not None
                    and (execution.execution_metadata or {}).get("event_delivery", {}).get("start_attempt_id")
                )

        def after_commit(sync_session: Session) -> None:
            nonlocal failed
            if not failed and sync_session.info.get("attempt_recorded"):
                failed = True
                raise failure

        event.listen(session.sync_session, "before_commit", before_commit)
        event.listen(session.sync_session, "after_commit", after_commit)
        return session

    admission = EventAdmissionService(factory, context.temporal)
    result = await admission.schedule(context.prepared)
    assert failed
    assert isinstance(result, ResolvedDelivery)
    assert len(context.temporal.starts) == 1
    async with context.delivery.session_factory() as session:
        row = await session.get(EventDelivery, context.prepared.claim.identity.digest)
        assert row.attempt_count == 1
        assert row.scheduling_failure_count == 0


async def test_other_invocation_attempt_cannot_authorize_start(scheduling_context, monkeypatch) -> None:
    context = scheduling_context
    other_attempt_id = uuid4()
    other = EventAdmissionService(context.delivery.session_factory, context.temporal)
    failure = OperationalError("read before attempt", {}, RuntimeError("PRIVATE"))

    async def failed_write(prepared: PreparedExecution, retention: int, attempt_id: UUID) -> DeliveryClaim | ClaimLost:
        assert attempt_id != other_attempt_id
        # Another invocation with this token commits while this invocation fails
        # before writing. Its counter alone must not authorize our RPC.
        await other._write_attempt(prepared, retention, other_attempt_id)
        raise failure

    monkeypatch.setattr(context.admission, "_write_attempt", failed_write)
    result = await context.admission.schedule(context.prepared)
    assert isinstance(result, RetryDelivery)
    assert result.error_code == SchedulingFailureCode.ATTEMPT_UNCERTAIN
    assert context.temporal.starts == []
    async with context.delivery.session_factory() as session:
        row = await session.get(EventDelivery, context.prepared.claim.identity.digest)
        execution = await session.get(Execution, context.prepared.execution_id)
        assert row.attempt_count == 1
        assert row.state == DeliveryState.IN_PROGRESS
        assert execution.execution_metadata["event_delivery"]["start_attempt_id"] == str(other_attempt_id)


async def test_delayed_rpc_takeover_fences_old_finalization(scheduling_context) -> None:
    context = scheduling_context
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed() -> None:
        entered.set()
        await release.wait()

    context.temporal.before_first_start = delayed
    old = asyncio.create_task(context.admission.schedule(context.prepared))
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        await context.delivery.expire(context.prepared.claim)
        results = await context.recovery.recover_due("takeover", limit=1)
        assert len(results) == 1
        assert isinstance(results[0][1], ResolvedDelivery)
        release.set()
        assert isinstance(await old, ClaimLost)
    finally:
        release.set()
        if not old.done():
            old.cancel()
            await asyncio.gather(old, return_exceptions=True)
    assert len(context.temporal.starts) == 2
    assert context.temporal.starts[0].claim.token != context.temporal.starts[1].claim.token
    assert context.temporal.starts[0].workflow_arguments() == context.temporal.starts[1].workflow_arguments()
    assert len({value.temporal_workflow_id for value in context.temporal.starts}) == 1


@pytest.mark.parametrize("legacy", [False, True])
async def test_expired_or_missing_deadline_blocks_not_found(scheduling_context, *, legacy) -> None:
    context = scheduling_context
    async with context.delivery.session_factory() as session, session.begin():
        attempted = await EventDeliveryStore(session).record_start_attempt(context.prepared.claim)
        assert isinstance(attempted, DeliveryClaim)
        if not legacy:
            await session.execute(
                update(EventDelivery)
                .where(col(EventDelivery.identity_digest) == context.prepared.claim.identity.digest)
                .values(
                    first_start_attempt_at=func.clock_timestamp() - timedelta(days=5),
                    start_retry_deadline=func.clock_timestamp() - timedelta(days=4),
                )
            )
    result = await context.admission.schedule(context.prepared)
    assert isinstance(result, BlockedDelivery)
    assert result.error_code == SchedulingFailureCode.HISTORY_EXPIRED
    assert context.temporal.starts == []
    async with context.delivery.session_factory() as session:
        row = await session.get(EventDelivery, context.prepared.claim.identity.digest)
        assert row.state == DeliveryState.IN_PROGRESS
        assert row.attempt_count == 1


async def test_accepted_repair_after_revocation_and_retirement(scheduling_context, monkeypatch) -> None:
    context = scheduling_context
    original = EventDeliveryStore.finalize_scheduled
    failed = False

    async def fail_once(
        store: EventDeliveryStore, claim: DeliveryClaim, accepted: TemporalAcceptance
    ) -> TerminalDelivery | ClaimLost:
        nonlocal failed
        result = await original(store, claim, accepted)
        if not failed:
            failed = True
            statement = "finalization"
            raise OperationalError(statement, {}, RuntimeError("PRIVATE"))
        return result

    monkeypatch.setattr(EventDeliveryStore, "finalize_scheduled", fail_once)
    assert isinstance(await context.admission.schedule(context.prepared), RetryDelivery)
    async with context.delivery.session_factory() as session, session.begin():
        credential = await session.get(Credential, context.delivery.snapshot.runtime_credential_id)
        integration = await session.get(Integration, context.delivery.snapshot.integration_id)
        subscription = await session.get(EventSubscription, context.delivery.snapshot.subscription_id)
        source = await session.get(EventSubscriptionSource, context.delivery.snapshot.source_id)
        workflow = await session.get(Workflow, context.delivery.snapshot.workflow_id)
        execution = await session.get(Execution, context.prepared.execution_id)
        credential.enabled = integration.enabled = False
        subscription.paused = subscription.retired = True
        subscription.desired_enabled = workflow.is_enabled = False
        workflow.published_version_id = None
        source.retired_at = (await session.exec(select(func.clock_timestamp()))).one()
        execution.status = ExecutionStatus.COMPLETED
        row = await session.get(EventDelivery, context.prepared.claim.identity.digest)
        assert row.state == DeliveryState.IN_PROGRESS
        assert row.temporal_run_id == "one-accepted-run"
        assert execution.execution_metadata["event_delivery"]["scheduling_state"] == "prepared"
    assert await context.recovery.request_retry(context.prepared.claim.identity)
    results = await context.recovery.recover_due("independent-recovery", limit=1)
    assert isinstance(results[0][1], ResolvedDelivery)
    assert len(context.temporal.starts) == 1
    async with context.delivery.session_factory() as session:
        execution = await session.get(Execution, context.prepared.execution_id)
        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.execution_metadata["event_delivery"]["scheduling_state"] == "confirmed"


async def test_unscheduled_revoked_binding_waits_for_correction(scheduling_context) -> None:
    context = scheduling_context
    async with context.delivery.session_factory() as session, session.begin():
        credential = await session.get(Credential, context.delivery.snapshot.runtime_credential_id)
        credential.enabled = False
    result = await context.admission.schedule(context.prepared)
    assert isinstance(result, BlockedDelivery)
    assert result.error_code == SchedulingFailureCode.RUNTIME_UNAVAILABLE
    assert context.temporal.starts == []
    async with context.delivery.session_factory() as session, session.begin():
        credential = await session.get(Credential, context.delivery.snapshot.runtime_credential_id)
        credential.enabled = True
    assert await context.recovery.request_retry(context.prepared.claim.identity)
    assert isinstance((await context.recovery.recover_due("corrected", limit=1))[0][1], ResolvedDelivery)


@pytest.mark.parametrize("phase", ["reload", "confirmation"])
async def test_evidence_mismatch_is_parked_and_releases_claim(scheduling_context, phase) -> None:
    context = scheduling_context

    async def corrupt_input() -> None:
        async with context.delivery.session_factory() as session, session.begin():
            execution = await session.get(Execution, context.prepared.execution_id)
            execution.input_data = {"mismatching": True}

    if phase == "reload":
        await corrupt_input()
    else:
        context.temporal.before_first_start = corrupt_input
    result = await context.admission.schedule(context.prepared)
    assert isinstance(result, BlockedDelivery)
    assert result.error_code == SchedulingFailureCode.EVIDENCE_MISMATCH
    assert len(context.temporal.starts) == (0 if phase == "reload" else 1)
    async with context.delivery.session_factory() as session:
        row = await session.get(EventDelivery, context.prepared.claim.identity.digest)
        execution = await session.get(Execution, context.prepared.execution_id)
        assert row.state == DeliveryState.IN_PROGRESS
        assert row.frozen_binding == context.prepared.claim.binding
        assert row.scheduling_failure_count == 1
        assert row.last_error_code == SchedulingFailureCode.EVIDENCE_MISMATCH.value
        assert row.next_attempt_at.replace(tzinfo=UTC) == datetime.max.replace(tzinfo=UTC)
        assert row.claim_token is row.owner_worker_id is row.lease_until is None
        assert execution.input_data == {"mismatching": True}
        assert execution.execution_metadata["event_delivery"]["scheduling_state"] == "prepared"
        assert execution.execution_metadata["event_delivery"]["last_error_code"] == row.last_error_code
    assert await context.recovery.recover_due("automatic-probe", limit=1) == []

    async with context.delivery.session_factory() as session, session.begin():
        execution = await session.get(Execution, context.prepared.execution_id)
        execution.input_data = context.prepared.input_data
    context.temporal.before_first_start = None
    assert await context.recovery.request_retry(context.prepared.claim.identity)
    recovered = (await context.recovery.recover_due("corrected", limit=1))[0][1]
    assert isinstance(recovered, ResolvedDelivery)
    assert recovered.terminal.execution_id == context.prepared.execution_id
    assert len(context.temporal.starts) == 1


@pytest.mark.parametrize("phase", ["namespace", "start"])
async def test_permanent_temporal_failure_waits_for_correction(scheduling_context, monkeypatch, phase) -> None:
    context = scheduling_context
    original_retention = context.temporal.history_retention_seconds
    original_start = context.temporal.start
    original_describe = context.temporal.describe
    code = (
        SchedulingFailureCode.HISTORY_UNAVAILABLE
        if phase == "namespace"
        else SchedulingFailureCode.TEMPORAL_UNAVAILABLE
    )
    failure = EventLaunchError(code, transient=False)
    inconclusive = EventLaunchError(SchedulingFailureCode.TEMPORAL_UNAVAILABLE)

    async def denied_retention() -> int:
        raise failure

    async def denied_start(_prepared: PreparedExecution) -> TemporalAcceptance:
        raise failure

    async def unavailable_describe(_prepared: PreparedExecution) -> TemporalAcceptance:
        raise inconclusive

    if phase == "namespace":
        monkeypatch.setattr(context.temporal, "history_retention_seconds", denied_retention)
    else:
        monkeypatch.setattr(context.temporal, "start", denied_start)
        monkeypatch.setattr(context.temporal, "describe", unavailable_describe)
    result = await context.admission.schedule(context.prepared)
    assert isinstance(result, BlockedDelivery)
    assert result.error_code == code
    assert context.temporal.accepted is None
    async with context.delivery.session_factory() as session:
        row = await session.get(EventDelivery, context.prepared.claim.identity.digest)
        execution = await session.get(Execution, context.prepared.execution_id)
        assert row.state == DeliveryState.IN_PROGRESS
        assert row.attempt_count == (0 if phase == "namespace" else 1)
        assert row.scheduling_failure_count == 1
        assert row.last_error_code == code.value
        blocked_until = datetime.max.replace(tzinfo=UTC)
        assert row.next_attempt_at.replace(tzinfo=UTC) == blocked_until
        assert row.claim_token is None
        assert execution.execution_metadata["event_delivery"]["last_error_code"] == code.value
        assert execution.execution_metadata["event_delivery"]["next_attempt_at"] == blocked_until.isoformat()
    assert await context.recovery.recover_due("automatic-probe", limit=1) == []

    monkeypatch.setattr(context.temporal, "history_retention_seconds", original_retention)
    monkeypatch.setattr(context.temporal, "start", original_start)
    monkeypatch.setattr(context.temporal, "describe", original_describe)
    assert await context.recovery.request_retry(context.prepared.claim.identity)
    recovered = (await context.recovery.recover_due("corrected", limit=1))[0][1]
    assert isinstance(recovered, ResolvedDelivery)
    assert recovered.terminal.execution_id == context.prepared.execution_id
    assert len(context.temporal.starts) == 1


@pytest.mark.parametrize("status", list(ExecutionStatus))
async def test_confirmation_preserves_every_execution_status(scheduling_context, status) -> None:
    context = scheduling_context
    async with context.delivery.session_factory() as session, session.begin():
        execution = await session.get(Execution, context.prepared.execution_id)
        execution.status = status
    assert isinstance(await context.admission.schedule(context.prepared), ResolvedDelivery)
    async with context.delivery.session_factory() as session:
        execution = await session.get(Execution, context.prepared.execution_id)
        assert execution.status == status


async def test_persisted_retry_budget_survives_restarts_and_bounds_probes(scheduling_context) -> None:
    context = scheduling_context
    context.temporal.fail_starts = True
    result = await context.admission.schedule(context.prepared)
    first_deadline = None
    for failure_count in range(1, 8):
        assert isinstance(result, RetryDelivery)
        assert result.circuit_open is (failure_count >= 5)
        async with context.delivery.session_factory() as session:
            row = await session.get(EventDelivery, context.prepared.claim.identity.digest)
            execution = await session.get(Execution, context.prepared.execution_id)
            now = (await session.exec(select(func.clock_timestamp()))).one()
            assert row.scheduling_failure_count == row.attempt_count == failure_count
            assert execution.execution_metadata["event_delivery"]["scheduling_failure_count"] == failure_count
            assert 0 < (row.next_attempt_at - now).total_seconds() <= (60 if failure_count >= 5 else 30)
            if first_deadline is None:
                first_deadline = row.start_retry_deadline
            assert row.start_retry_deadline == first_deadline
        if failure_count < 7:
            admission = EventAdmissionService(context.delivery.session_factory, context.temporal)
            recovery = EventExecutionRecoveryService(context.delivery.session_factory, admission)
            assert await recovery.request_retry(context.prepared.claim.identity)
            result = (await recovery.recover_due(f"restart-{failure_count}", limit=1))[0][1]


async def test_recovery_does_not_claim_unprepared_work(scheduling_context) -> None:
    context = scheduling_context
    await context.delivery.claim(99)
    await context.delivery.expire(context.prepared.claim)
    assert len(await context.recovery.recover_due("bounded", limit=1)) == 1
    assert await context.recovery.recover_due("bounded", limit=1) == []


async def test_retention_increase_preserves_existing_deadline(scheduling_context, override_settings) -> None:
    context = scheduling_context
    context.temporal.fail_starts = True
    assert isinstance(await context.admission.schedule(context.prepared), RetryDelivery)
    async with context.delivery.session_factory() as session:
        row = await session.get(EventDelivery, context.prepared.claim.identity.digest)
        deadline = row.start_retry_deadline
    with override_settings(event_temporal_history_retention_seconds=172800):
        assert await context.recovery.request_retry(context.prepared.claim.identity)
        assert isinstance((await context.recovery.recover_due("larger-window", limit=1))[0][1], RetryDelivery)
    async with context.delivery.session_factory() as session:
        row = await session.get(EventDelivery, context.prepared.claim.identity.digest)
        assert row.start_retry_deadline == deadline
        assert row.attempt_count == 2


async def test_superseded_token_cannot_start(scheduling_context) -> None:
    context = scheduling_context
    await context.delivery.expire(context.prepared.claim)
    async with context.delivery.session_factory() as session, session.begin():
        claims = await EventDeliveryStore(session).claim_due("new-owner", limit=1, prepared_only=True)
    assert len(claims) == 1
    assert isinstance(await context.admission.schedule(context.prepared), ClaimLost)
    assert context.temporal.starts == []


@pytest.mark.parametrize("lifecycle", ["paused", "unpublished", "retired"])
async def test_prepared_recovery_can_start_without_active_subscription(scheduling_context, lifecycle) -> None:
    context = scheduling_context
    async with context.delivery.session_factory() as session, session.begin():
        subscription = await session.get(EventSubscription, context.delivery.snapshot.subscription_id)
        if lifecycle == "paused":
            subscription.paused = True
        elif lifecycle == "unpublished":
            workflow = await session.get(Workflow, context.delivery.snapshot.workflow_id)
            workflow.published_version_id = None
            workflow.is_enabled = subscription.desired_enabled = False
        else:
            subscription.retired = True
            subscription.desired_enabled = False
            source = await session.get(EventSubscriptionSource, context.delivery.snapshot.source_id)
            source.retired_at = (await session.exec(select(func.clock_timestamp()))).one()
    await context.delivery.expire(context.prepared.claim)
    results = await context.recovery.recover_due("no-consumer", limit=1)
    assert len(results) == 1
    assert isinstance(results[0][1], ResolvedDelivery)
    assert len(context.temporal.starts) == 1
    assert context.temporal.starts[0].workflow_arguments() == context.prepared.workflow_arguments()


@pytest.mark.parametrize("frozen_enabled", [False, True])
async def test_republished_credential_does_not_replace_frozen_binding(scheduling_context, *, frozen_enabled) -> None:
    context = scheduling_context
    async with context.delivery.session_factory() as session, session.begin():
        frozen = await session.get(Credential, context.delivery.snapshot.runtime_credential_id)
        frozen.enabled = frozen_enabled
        replacement = Credential(
            name="replacement",
            project_id=frozen.project_id,
            credential_type_id=frozen.credential_type_id,
            enabled=not frozen_enabled,
            created_by=context.delivery.principal_id,
        )
        session.add(replacement)
        await session.flush()
        subscription = await session.get(EventSubscription, context.delivery.snapshot.subscription_id)
        subscription.runtime_credential_id = replacement.id
        subscription.configuration_revision += 1
    result = await context.admission.schedule(context.prepared)
    if frozen_enabled:
        assert isinstance(result, ResolvedDelivery)
        assert context.temporal.starts[0].claim.binding == context.prepared.claim.binding
    else:
        assert isinstance(result, BlockedDelivery)
        assert result.error_code == SchedulingFailureCode.RUNTIME_UNAVAILABLE
        assert context.temporal.starts == []


async def test_lost_finalization_commit_response_reloads_durable_confirmation(scheduling_context) -> None:
    context = scheduling_context
    failed = False
    failure = OperationalError("commit response", {}, RuntimeError("PRIVATE"))

    def factory() -> AsyncSession:
        session: AsyncSession = context.delivery.session_factory()

        def before_commit(sync_session: Session) -> None:
            if not failed:
                state = sync_session.scalar(
                    select(EventDelivery.state).where(
                        col(EventDelivery.identity_digest) == context.prepared.claim.identity.digest
                    )
                )
                sync_session.info["confirmed"] = state == DeliveryState.SCHEDULED

        def after_commit(sync_session: Session) -> None:
            nonlocal failed
            if not failed and sync_session.info.get("confirmed"):
                failed = True
                raise failure

        event.listen(session.sync_session, "before_commit", before_commit)
        event.listen(session.sync_session, "after_commit", after_commit)
        return session

    admission = EventAdmissionService(factory, context.temporal)
    result = await admission.schedule(context.prepared)
    assert failed
    assert isinstance(result, ResolvedDelivery)
    assert len(context.temporal.starts) == 1
    async with context.delivery.session_factory() as session:
        row = await session.get(EventDelivery, context.prepared.claim.identity.digest)
        execution = await session.get(Execution, context.prepared.execution_id)
        assert row.state == DeliveryState.SCHEDULED
        assert row.scheduling_failure_count == 0
        assert execution.execution_metadata["event_delivery"]["scheduling_state"] == "confirmed"


async def test_retry_evidence_downgrade_refuses_unresolved_preparation(scheduling_context) -> None:
    context = scheduling_context
    migration = importlib.import_module(
        "syntara.core.database.migrations.versions.f84181447c22_add_event_scheduling_retry_evidence"
    )

    def downgrade(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()

    with pytest.raises(RuntimeError, match="Unsafe downgrade"):
        async with context.delivery.session_factory() as session, session.begin():
            connection = await session.connection()
            await connection.run_sync(downgrade)
