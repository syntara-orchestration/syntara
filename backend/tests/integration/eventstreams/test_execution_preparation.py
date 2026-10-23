"""Real PostgreSQL preparation transactions; no broker or Temporal acceptance claims."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING
from unittest.mock import PropertyMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import event, func
from sqlmodel import select

from syntara.core.config.base import Settings
from syntara.core.models.principal import Principal
from syntara.core.services.secret_service import create_secret_service
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.core.deduplication import ClaimLost, DeliveryState, RevisionChanged
from syntara.eventstreams.core.envelope import RawEvent, RawEventHeader, WorkflowEventEnvelope
from syntara.eventstreams.core.preparation import ExecutionCapacityUnavailable, PreparationBlocked, PreparedExecution
from syntara.eventstreams.core.results import EventDecodeFailure
from syntara.eventstreams.core.serialization import EventDecodeSuccess, JsonEventDecoder, encoded_envelope_size
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.services.connection_provider import EventConnectionProvider
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from tests.integration.eventstreams.conftest import AvailableCapacity

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from sqlmodel.ext.asyncio.session import AsyncSession

    from tests.integration.eventstreams.conftest import DeliveryContext

pytestmark = pytest.mark.integration
type SettingsOverride = Callable[..., AbstractContextManager[None]]


@pytest_asyncio.fixture
async def preparation_context(delivery_context: DeliveryContext) -> DeliveryContext:
    """Complete the fixture's runtime credential through the real secret service."""
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
    return context


async def envelope(context: DeliveryContext, *, offset: int = 0) -> WorkflowEventEnvelope:
    async with context.session_factory() as session:
        now = (await session.exec(select(func.clock_timestamp()))).one()
    result = JsonEventDecoder().decode(
        RawEvent(
            value=b' {"count":2} \n',
            key=b"\xff",
            headers=(RawEventHeader(name="repeat", value=None), RawEventHeader(name="repeat", value=b"")),
            source_metadata=KafkaSourceMetadata(
                integration_id=context.snapshot.integration_identity,
                subscription_id=context.snapshot.subscription_id,
                source_generation=context.snapshot.source_generation,
                received_at=now,
                topic=context.snapshot.configuration.topic,
                partition=0,
                offset=str(offset),
            ),
        )
    )
    assert isinstance(result, EventDecodeSuccess)
    return result.envelope


def service(context: DeliveryContext) -> EventExecutionPreparationService:
    return EventExecutionPreparationService(context.session_factory, capacity_check=AvailableCapacity())


def fail_outer_commit(session: AsyncSession) -> list[bool]:
    """Record savepoint commits and reject only the final preparation commit."""
    commits: list[bool] = []

    def reject_commit(sync_session: Session) -> None:
        nested = sync_session.in_nested_transaction()
        commits.append(nested)
        if not nested:
            msg = "Preparation commit failed"
            raise RuntimeError(msg)

    event.listen(session.sync_session, "before_commit", reject_commit)
    return commits


async def test_preparation_is_visible_with_frozen_binding_before_return(preparation_context: DeliveryContext) -> None:
    context = preparation_context
    original = await envelope(context)
    result = await service(context).prepare_delivery(context.snapshot, context.identity(), original, "worker")
    assert isinstance(result, PreparedExecution)
    async with context.session_factory() as session:
        execution = await session.get(Execution, result.execution_id)
        delivery = await session.get(EventDelivery, context.identity().digest)
        assert execution is not None
        assert delivery is not None
        assert execution.status == ExecutionStatus.PENDING
        assert execution.created_by == execution.updated_by == context.principal_id
        assert execution.input_data == original.model_dump(mode="json")
        assert execution.execution_metadata is not None
        assert execution.execution_metadata["event_delivery"]["scheduling_state"] == "prepared"
        assert delivery.state == DeliveryState.IN_PROGRESS
        assert delivery.resolved_at is None
        assert delivery.execution_confirmed_at is None
        assert delivery.frozen_binding == result.claim.binding
        assert delivery.execution_id == execution.id == context.identity().execution_id
        assert (await session.exec(select(func.count()).select_from(Execution))).one() == 1


async def test_creator_and_enabler_are_separate_from_platform_attribution(preparation_context: DeliveryContext) -> None:
    context = preparation_context
    enabler = Principal.for_service("enabler.ao.svc")
    async with context.session_factory() as session, session.begin():
        session.add(enabler)
        subscription = await session.get(EventSubscription, context.snapshot.subscription_id)
        workflow = await session.get(Workflow, context.snapshot.workflow_id)
        assert subscription is not None
        assert workflow is not None
        subscription.enabled_by = enabler.id
        creator_id = workflow.created_by
    result = await service(context).prepare_delivery(
        context.snapshot, context.identity(), await envelope(context), "worker"
    )
    assert isinstance(result, PreparedExecution)
    assert result.workflow_metadata["workflow_context"]["execution"]["created_by_user_id"] == str(creator_id)
    assert result.workflow_metadata["event"]["enabled_by"] == str(enabler.id)
    assert result.claim.binding is not None
    assert result.claim.binding.execution_principal_id == context.principal_id


async def test_full_capacity_recovery_preserves_old_publication_and_principal(
    preparation_context: DeliveryContext,
    override_settings: SettingsOverride,
) -> None:
    context = preparation_context
    first = await service(context).prepare_delivery(
        context.snapshot, context.identity(), await envelope(context), "worker"
    )
    assert isinstance(first, PreparedExecution)
    await context.expire(first.claim)
    async with context.session_factory() as session, session.begin():
        workflow = await session.get(Workflow, context.snapshot.workflow_id)
        subscription = await session.get(EventSubscription, context.snapshot.subscription_id)
        credential = await session.get(Credential, context.snapshot.runtime_credential_id)
        assert workflow is not None
        assert subscription is not None
        assert credential is not None
        old_version = await session.get(WorkflowVersion, context.snapshot.published_version_id)
        assert old_version is not None
        version = WorkflowVersion(
            workflow_id=workflow.id,
            version=2,
            schema_version=old_version.schema_version,
            created_by=workflow.created_by,
            workflow_definition=old_version.workflow_definition,
        )
        session.add(version)
        await session.flush()
        workflow.published_version_id = version.id
        workflow.name = "Renamed after preparation"
        subscription.published_version_id = version.id
        subscription.configuration_revision += 1
        subscription.paused = True
        credential.enabled = False
    with (
        override_settings(max_concurrent_workflows=1),
        patch.object(Settings, "service_identity", new_callable=PropertyMock, return_value="new.ao.svc"),
    ):
        recovered = await service(context).prepare_delivery(context.snapshot, context.identity(), None, "recovery")
    assert isinstance(recovered, PreparedExecution)
    assert recovered.claim.binding == first.claim.binding
    assert recovered.execution_id == first.execution_id
    assert recovered.temporal_workflow_id == first.temporal_workflow_id
    assert recovered.workflow_arguments() == first.workflow_arguments()
    async with context.session_factory() as session:
        assert (await session.exec(select(func.count()).select_from(Execution))).one() == 1


async def test_new_admission_at_capacity_does_not_leave_provisional_delivery(
    preparation_context: DeliveryContext,
    override_settings: SettingsOverride,
) -> None:
    context = preparation_context
    first = await service(context).prepare_delivery(
        context.snapshot, context.identity(), await envelope(context), "worker"
    )
    assert isinstance(first, PreparedExecution)
    with override_settings(max_concurrent_workflows=1):
        refused = await service(context).prepare_delivery(
            context.snapshot, context.identity(1), await envelope(context, offset=1), "other"
        )
    assert isinstance(refused, ExecutionCapacityUnavailable)
    async with context.session_factory() as session:
        assert await session.get(EventDelivery, context.identity(1).digest) is None
        assert await session.get(Execution, context.identity(1).execution_id) is None
        assert await session.get(Execution, first.execution_id) is not None


async def test_stale_token_cannot_prepare(preparation_context: DeliveryContext) -> None:
    context = preparation_context
    stale = await context.claim(owner="worker")
    await context.expire(stale)
    replacement = await context.claim(owner="replacement")
    result = await service(context).prepare_delivery(
        context.snapshot, context.identity(), await envelope(context), "worker", claim=stale
    )
    assert isinstance(result, ClaimLost)
    async with context.session_factory() as session:
        row = await session.get(EventDelivery, context.identity().digest)
        assert row is not None
        assert row.claim_token == replacement.token
        assert row.frozen_binding is None
        assert await session.get(Execution, context.identity().execution_id) is None


async def test_revision_conflict_and_schema_failure_leave_no_preparation(preparation_context: DeliveryContext) -> None:
    context = preparation_context
    stale = context.snapshot.model_copy(update={"configuration_revision": 999})
    assert isinstance(
        await service(context).prepare_delivery(stale, context.identity(), await envelope(context), "worker"),
        RevisionChanged,
    )
    async with context.session_factory() as session, session.begin():
        subscription = await session.get(EventSubscription, context.snapshot.subscription_id)
        assert subscription is not None
        subscription.input_schema = {"type": "array"}
    result = await service(context).prepare_delivery(
        context.snapshot, context.identity(), await envelope(context), "worker"
    )
    assert isinstance(result, EventDecodeFailure)
    async with context.session_factory() as session:
        assert await session.get(EventDelivery, context.identity().digest) is None
        assert await session.get(Execution, context.identity().execution_id) is None


async def test_complete_arguments_can_exceed_candidate_limit_before_freeze(
    preparation_context: DeliveryContext,
    override_settings: SettingsOverride,
) -> None:
    context = preparation_context
    value = await envelope(context)
    with override_settings(event_max_envelope_bytes=encoded_envelope_size(value) + 1):
        result = await service(context).prepare_delivery(context.snapshot, context.identity(), value, "worker")
    assert isinstance(result, EventDecodeFailure)
    async with context.session_factory() as session:
        assert await session.get(EventDelivery, context.identity().digest) is None
        assert await session.get(Execution, context.identity().execution_id) is None


async def test_commit_failure_rolls_back_execution_and_delivery(preparation_context: DeliveryContext) -> None:
    context = preparation_context
    session = context.session_factory()
    commits = fail_outer_commit(session)
    failing = EventExecutionPreparationService(lambda: session, capacity_check=AvailableCapacity())
    with pytest.raises(RuntimeError, match="Preparation commit failed"):
        await failing.prepare_delivery(context.snapshot, context.identity(), await envelope(context), "worker")
    assert commits == [True, False]
    async with context.session_factory() as check:
        assert await check.get(EventDelivery, context.identity().digest) is None
        assert await check.get(Execution, context.identity().execution_id) is None


async def test_recovery_commit_failure_preserves_frozen_execution_and_binding(
    preparation_context: DeliveryContext,
) -> None:
    context = preparation_context
    first = await service(context).prepare_delivery(
        context.snapshot, context.identity(), await envelope(context), "worker"
    )
    assert isinstance(first, PreparedExecution)
    await context.expire(first.claim)
    async with context.session_factory() as check:
        execution = await check.get(Execution, first.execution_id)
        delivery = await check.get(EventDelivery, context.identity().digest)
        assert execution is not None
        assert delivery is not None
        execution_before = execution.model_dump(mode="json")
        delivery_before = delivery.model_dump(mode="json")

    session = context.session_factory()
    commits = fail_outer_commit(session)
    failing = EventExecutionPreparationService(lambda: session, capacity_check=AvailableCapacity())
    with pytest.raises(RuntimeError, match="Preparation commit failed"):
        await failing.prepare_delivery(context.snapshot, context.identity(), None, "recovery")
    assert commits == [False]
    async with context.session_factory() as check:
        execution = await check.get(Execution, first.execution_id)
        delivery = await check.get(EventDelivery, context.identity().digest)
        assert execution is not None
        assert delivery is not None
        assert execution.model_dump(mode="json") == execution_before
        assert delivery.model_dump(mode="json") == delivery_before
        assert delivery.frozen_binding == first.claim.binding
        assert delivery.state == DeliveryState.IN_PROGRESS
        assert delivery.resolved_at is None
        assert delivery.execution_confirmed_at is None

    recovered = await service(context).prepare_delivery(context.snapshot, context.identity(), None, "retry")
    assert isinstance(recovered, PreparedExecution)
    assert recovered.workflow_arguments() == first.workflow_arguments()
    assert recovered.claim.binding == first.claim.binding


@pytest.mark.parametrize("inputs", [{}, {"username": "test", "password": ""}])
async def test_incomplete_runtime_authentication_does_not_prepare_execution(
    preparation_context: DeliveryContext,
    inputs: dict[str, str],
) -> None:
    context = preparation_context
    async with context.session_factory() as session, session.begin():
        credential = await session.get(Credential, context.snapshot.runtime_credential_id)
        assert credential is not None
        assert credential.secret_id is not None
        await create_secret_service(session).update_secret(credential.secret_id, inputs)
    result = await service(context).prepare_delivery(
        context.snapshot, context.identity(), await envelope(context), "worker"
    )
    assert isinstance(result, PreparationBlocked)
    async with context.session_factory() as check:
        assert await check.get(EventDelivery, context.identity().digest) is None
        assert await check.get(Execution, context.identity().execution_id) is None


async def test_production_revision_changes_on_real_secret_update(preparation_context: DeliveryContext) -> None:
    context = preparation_context
    async with context.session_factory() as session:
        before = await EventConnectionProvider(session).resolve_revision(context.snapshot)
    async with context.session_factory() as session, session.begin():
        credential = await session.get(Credential, context.snapshot.runtime_credential_id)
        assert credential is not None
        assert credential.secret_id is not None
        await create_secret_service(session).update_secret(
            credential.secret_id, {"username": "test", "password": uuid4().hex}
        )
    async with context.session_factory() as session:
        after = await EventConnectionProvider(session).resolve_revision(context.snapshot)
    assert after.digest != before.digest
    assert after.secret_id == before.secret_id
