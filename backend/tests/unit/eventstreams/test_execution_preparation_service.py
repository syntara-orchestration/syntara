"""Preparation ordering and frozen recovery, isolated from external systems."""

from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.exceptions import SafeValueError
from syntara.core.models.principal import service_principal_id
from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.adapters.kafka_record_identity import KafkaRecordIdentity
from syntara.eventstreams.core.connection_revision import ConnectionRevision
from syntara.eventstreams.core.deduplication import ClaimLost, DeliveryClaim, DeliveryIdentity, RevisionChanged
from syntara.eventstreams.core.envelope import RawEvent, RawEventHeader, WorkflowEventEnvelope
from syntara.eventstreams.core.preparation import ExecutionCapacityUnavailable, PreparationBlocked, PreparedExecution
from syntara.eventstreams.core.results import EventDecodeFailure, EventFailureCode
from syntara.eventstreams.core.serialization import EventDecodeSuccess, JsonEventDecoder, encoded_envelope_size
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services import execution_preparation_service as module
from syntara.eventstreams.services.deduplication_store import EventDeliveryStore
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from tests.unit.eventstreams.test_connection_provider import connection_context
from tests.unit.eventstreams.test_connection_revision import NOW, revision


@dataclass
class PreparationContext:
    """One preparation attempt with ordered test ports and retained resource rows."""

    snapshot: SubscriptionSnapshot
    subscription: EventSubscription
    identity: DeliveryIdentity
    envelope: WorkflowEventEnvelope
    claim: DeliveryClaim
    workflow: Workflow
    version: WorkflowVersion
    settings: SimpleNamespace
    rows: dict[type, object]
    session: MagicMock
    transaction: MagicMock
    store: MagicMock
    provider: AsyncMock
    capacity: AsyncMock
    events: list[str]
    service: EventExecutionPreparationService

    async def prepare(self, **kwargs: object) -> module.PreparationResult:
        return await self.service.prepare_delivery(
            self.snapshot,
            self.identity,
            self.envelope,
            "worker",
            **kwargs,  # type: ignore[arg-type]
        )


def preparation_context(monkeypatch: pytest.MonkeyPatch, value: bytes = b'{"count":2}') -> PreparationContext:
    """Mock only persistence boundaries and exercise real preparation/model helpers."""
    connection = connection_context()
    snapshot = connection.snapshot
    subscription = EventSubscription(
        id=snapshot.subscription_id,
        workflow_id=snapshot.workflow_id,
        project_id=snapshot.project_id,
        trigger_node_id=snapshot.trigger_node_id,
        published_version_id=snapshot.published_version_id,
        runtime_credential_id=snapshot.runtime_credential_id,
        active_source_generation=snapshot.source_generation,
        configuration_revision=snapshot.configuration_revision,
        input_schema=snapshot.model_dump(mode="json")["input_schema"],
        enabled_by=snapshot.enabled_by,
        created_by=UUID(int=90),
    )
    source = EventSubscriptionSource(
        id=snapshot.source_id,
        subscription_id=snapshot.subscription_id,
        deployment_id=snapshot.deployment_id,
        generation=snapshot.source_generation,
        integration_id=snapshot.integration_id,
        integration_identity=snapshot.integration_identity,
        transport=snapshot.transport,
        configuration=snapshot.configuration,
    )
    identity = DeliveryIdentity(
        deployment_id=snapshot.deployment_id,
        integration_identity=snapshot.integration_identity,
        source_id=snapshot.source_id,
        source_generation=snapshot.source_generation,
        workflow_id=snapshot.workflow_id,
        subscription_id=snapshot.subscription_id,
        record=KafkaRecordIdentity(topic=snapshot.configuration.topic, partition=2, offset=5),
    )
    metadata = KafkaSourceMetadata(
        integration_id=snapshot.integration_identity,
        subscription_id=snapshot.subscription_id,
        source_generation=snapshot.source_generation,
        received_at=NOW,
        topic=snapshot.configuration.topic,
        partition=2,
        offset="5",
    )
    decoded = JsonEventDecoder().decode(
        RawEvent(
            value=value,
            key=b"\xff",
            headers=(RawEventHeader(name="repeat", value=b"\xff"), RawEventHeader(name="repeat", value=None)),
            source_metadata=metadata,
        )
    )
    assert isinstance(decoded, EventDecodeSuccess)
    claim = DeliveryClaim(identity=identity, token=UUID(int=50), owner_worker_id="worker", lease_until=NOW)
    workflow = Workflow(
        id=snapshot.workflow_id,
        project_id=snapshot.project_id,
        name="Original name",
        created_by=UUID(int=91),
        published_version_id=snapshot.published_version_id,
        is_enabled=True,
    )
    version = WorkflowVersion(
        id=snapshot.published_version_id,
        workflow_id=workflow.id,
        version=1,
        created_by=workflow.created_by,
        workflow_definition={
            "schema_version": "2.0.0",
            "triggers": [{"id": snapshot.trigger_node_id, "type": "event_subscribe_trigger"}],
            "nodes": [],
            "edges": [],
        },
    )
    rows: dict[type, object] = {Workflow: workflow, WorkflowVersion: version}
    session = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    session.get = AsyncMock(side_effect=lambda model, _id, **_kwargs: rows.get(model))
    events: list[str] = []
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(side_effect=lambda: events.append("begin"))
    transaction.__aexit__ = AsyncMock(
        side_effect=lambda error, *_args: events.append("rollback" if error else "commit")
    )
    session.begin.return_value = transaction
    store = MagicMock(spec=EventDeliveryStore)

    def acquire(*_args: object) -> DeliveryClaim:
        events.append("acquire")
        return claim

    store.acquire = AsyncMock(side_effect=acquire)
    store.renew = AsyncMock(return_value=claim)

    async def freeze(current: DeliveryClaim, binding: object, execution: Execution) -> DeliveryClaim:
        events.append("freeze")
        rows[Execution] = execution
        execution.execution_metadata = {
            **(execution.execution_metadata or {}),
            "event_delivery": {"scheduling_state": "prepared"},
        }
        return current.model_copy(update={"binding": binding})

    store.freeze = AsyncMock(side_effect=freeze)

    def resolve_revision(_snapshot: SubscriptionSnapshot) -> ConnectionRevision:
        events.append("provider")
        return revision()

    def count_active(_session: AsyncSession) -> int:
        events.append("capacity")
        return 0

    provider = AsyncMock(side_effect=resolve_revision)
    capacity = AsyncMock(side_effect=count_active)
    settings = SimpleNamespace(
        max_concurrent_workflows=2, service_identity="worker.ao.svc", event_max_envelope_bytes=1024 * 1024
    )
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(module, "EventDeliveryStore", lambda *_args, **_kwargs: store)
    monkeypatch.setattr(module, "lock_source_lifecycle", AsyncMock(return_value=(subscription, source)))
    monkeypatch.setattr(module, "EventConnectionProvider", lambda _session: SimpleNamespace(resolve_revision=provider))
    monkeypatch.setattr(module, "count_active_executions", capacity)
    monkeypatch.setattr(module, "resolve_user_display_name", AsyncMock(return_value="Original creator"))
    clock = MagicMock(wraps=datetime)
    clock.now.return_value = NOW
    monkeypatch.setattr(module, "datetime", clock)
    service = EventExecutionPreparationService(lambda: session)
    return PreparationContext(
        snapshot,
        subscription,
        identity,
        decoded.envelope,
        claim,
        workflow,
        version,
        settings,
        rows,
        session,
        transaction,
        store,
        provider,
        capacity,
        events,
        service,
    )


async def test_preparation_commits_frozen_attribution_and_input(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    original = context.envelope.model_dump(mode="json")
    result = await context.prepare()
    assert isinstance(result, PreparedExecution)
    assert context.events == ["begin", "acquire", "provider", "capacity", "freeze", "commit"]
    execution = context.rows[Execution]
    assert isinstance(execution, Execution)
    assert execution.status == ExecutionStatus.PENDING
    assert execution.created_by == execution.updated_by == service_principal_id("worker.ao.svc")
    assert result.execution_id == context.identity.execution_id
    assert result.temporal_workflow_id == context.identity.temporal_workflow_id
    assert execution.input_data == original == context.envelope.model_dump(mode="json")
    creator = result.workflow_metadata["workflow_context"]["execution"]
    assert creator["created_by"] == "Original creator"
    assert creator["created_by_user_id"] == str(context.workflow.created_by)
    assert result.workflow_metadata["event"]["enabled_by"] == str(context.snapshot.enabled_by)
    assert result.claim.binding is not None
    assert result.claim.binding.connection_revision == revision().digest
    assert result.claim.binding.prepared_at == execution.created_at == execution.updated_at == NOW
    assert "PRIVATE" not in result.workflow_metadata


async def test_recovery_ignores_later_publication_capacity_and_principal_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = preparation_context(monkeypatch)
    first = await context.prepare()
    assert isinstance(first, PreparedExecution)
    context.store.acquire.side_effect = None
    context.store.acquire.return_value = first.claim
    context.subscription.configuration_revision += 1
    context.subscription.published_version_id = UUID(int=999)
    context.subscription.paused = True
    context.workflow.name = "Later name"
    context.workflow.is_enabled = False
    context.settings.service_identity = "other.ao.svc"
    context.provider.reset_mock()
    context.provider.side_effect = AssertionError("Recovery must not resolve current credentials")
    context.capacity.reset_mock()
    context.capacity.side_effect = AssertionError("Recovery must not reserve capacity")
    context.store.freeze.reset_mock()
    recovered = await context.service.prepare_delivery(context.snapshot, context.identity, None, "worker")
    assert recovered == first
    context.provider.assert_not_awaited()
    context.capacity.assert_not_awaited()
    context.store.freeze.assert_not_awaited()


async def test_new_admission_at_capacity_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    context.capacity.side_effect = None
    context.capacity.return_value = 2
    assert await context.prepare() == ExecutionCapacityUnavailable(limit=2, active=2)
    assert context.events[-1] == "rollback"
    context.store.freeze.assert_not_awaited()


@pytest.mark.parametrize("failure", [ClaimLost(), RevisionChanged()])
async def test_lost_token_or_revision_never_returns_preparation(
    monkeypatch: pytest.MonkeyPatch, failure: object
) -> None:
    context = preparation_context(monkeypatch)
    context.store.freeze.side_effect = None
    context.store.freeze.return_value = failure
    assert await context.prepare() == failure
    assert context.events[-1] == "rollback"


@pytest.mark.parametrize("failure", [ClaimLost(), RevisionChanged()])
async def test_acquisition_conflict_precedes_validation_and_capacity(
    monkeypatch: pytest.MonkeyPatch, failure: object
) -> None:
    context = preparation_context(monkeypatch)
    context.store.acquire.side_effect = None
    context.store.acquire.return_value = failure
    assert await context.prepare() == failure
    context.provider.assert_not_awaited()
    context.capacity.assert_not_awaited()
    context.store.freeze.assert_not_awaited()


@pytest.mark.parametrize(
    ("value", "schema"),
    [
        (b"null", {"type": "null"}),
        (b"[1]", {"type": "array"}),
        (b"42", {"type": "integer"}),
        (b'"text"', {"type": "string"}),
        (b'{"count":2}', {"type": "object", "properties": {"added": {"default": 99}}}),
    ],
)
async def test_only_payload_is_validated_without_defaults(
    monkeypatch: pytest.MonkeyPatch, value: bytes, schema: dict[str, object]
) -> None:
    context = preparation_context(monkeypatch, value)
    context.subscription.input_schema = schema
    before = context.envelope.model_dump(mode="json")
    result = await context.prepare()
    assert isinstance(result, PreparedExecution)
    assert result.input_data == before


async def test_validation_failure_does_not_freeze_or_resolve_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    context.subscription.input_schema = {"type": "array"}
    assert await context.prepare() == EventDecodeFailure(code=EventFailureCode.schema_mismatch)
    context.store.freeze.assert_not_awaited()
    context.provider.assert_not_awaited()
    assert context.events[-1] == "rollback"


async def test_complete_argument_sizing_counts_definition_context_and_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    first = await context.prepare()
    assert isinstance(first, PreparedExecution)
    size = first.encoded_arguments_size()
    assert size > encoded_envelope_size(context.envelope)
    assert len(first.workflow_arguments()) == 9
    context.settings.event_max_envelope_bytes = size
    assert isinstance(await context.prepare(), PreparedExecution)
    context.store.freeze.reset_mock()
    context.settings.event_max_envelope_bytes = size - 1
    assert await context.prepare() == EventDecodeFailure(code=EventFailureCode.envelope_too_large)
    context.store.freeze.assert_not_awaited()
    assert context.events[-1] == "rollback"


async def test_unavailable_credential_is_blocked_not_content_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    context.provider.side_effect = SafeValueError("Unavailable")
    assert await context.prepare() == PreparationBlocked()
    context.store.freeze.assert_not_awaited()
    assert context.events[-1] == "rollback"


async def test_commit_failure_cannot_return_prepared_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    context.transaction.__aexit__.side_effect = RuntimeError("commit failed")
    with pytest.raises(RuntimeError, match="commit failed"):
        await context.prepare()
    context.store.freeze.assert_awaited_once()


async def test_recovery_renews_current_token_and_rejects_tampered_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    first = await context.prepare()
    assert isinstance(first, PreparedExecution)
    context.store.renew.return_value = first.claim
    context.store.acquire.reset_mock()
    recovered = await context.prepare(claim=context.claim)
    assert recovered == first
    context.store.acquire.assert_not_awaited()
    context.store.renew.assert_awaited_once_with(context.claim)
    execution = context.rows[Execution]
    assert isinstance(execution, Execution)
    execution.input_data = {"tampered": True}
    with pytest.raises(ValueError, match="retained delivery evidence"):
        await context.prepare(claim=first.claim)


async def test_source_coordinates_cannot_be_selected_by_message(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    context.envelope = context.envelope.model_copy(
        update={"source_metadata": context.envelope.source_metadata.model_copy(update={"offset": "99"})}
    )
    with pytest.raises(ValueError, match="trusted delivery identity"):
        await context.prepare()
    context.store.freeze.assert_not_awaited()


async def test_disabled_workflow_blocks_new_admission(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    context.workflow.is_enabled = False
    assert await context.prepare() == RevisionChanged()
    context.provider.assert_not_awaited()


async def test_store_and_preparation_exclude_the_same_scheduling_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    first = await context.prepare()
    assert isinstance(first, PreparedExecution)
    assert first.claim.binding is not None
    execution = context.rows[Execution]
    assert isinstance(execution, Execution)
    execution.execution_metadata = {
        **(execution.execution_metadata or {}),
        "event_delivery": {"scheduling_state": "confirmed", "temporal_run_id": "test-run"},
    }

    assert EventDeliveryStore._fingerprint(execution) == first.claim.binding.input_fingerprint
    recovered = context.service._prepared(first.claim, execution, context.version)
    assert recovered.workflow_arguments() == first.workflow_arguments()

    execution.execution_metadata = {
        **execution.execution_metadata,
        "workflow_context": {"changed": True},
    }
    assert EventDeliveryStore._fingerprint(execution) != first.claim.binding.input_fingerprint
    with pytest.raises(ValueError, match="retained delivery evidence"):
        context.service._prepared(first.claim, execution, context.version)
