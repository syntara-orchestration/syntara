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
from syntara.eventstreams.core.deduplication import DeliveryIdentity, RevisionChanged
from syntara.eventstreams.core.envelope import RawEvent, RawEventHeader, WorkflowEventEnvelope
from syntara.eventstreams.core.preparation import ExecutionCapacityUnavailable, PreparationBlocked, PreparedExecution
from syntara.eventstreams.core.results import EventDecodeFailure, EventFailureCode
from syntara.eventstreams.core.serialization import EventDecodeSuccess, JsonEventDecoder, encoded_envelope_size
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services import execution_preparation_service as module
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
    workflow: Workflow
    version: WorkflowVersion
    settings: SimpleNamespace
    rows: dict[type, object]
    session: MagicMock
    transaction: MagicMock
    provider: AsyncMock
    capacity: AsyncMock
    events: list[str]
    service: EventExecutionPreparationService

    async def prepare(self) -> module.PreparationResult:
        return await self.service.prepare_delivery(
            self.snapshot,
            self.identity,
            self.envelope,
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
        workflow,
        version,
        settings,
        rows,
        session,
        transaction,
        provider,
        capacity,
        events,
        service,
    )


async def test_preparation_keeps_execution_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    result = await context.prepare()
    assert isinstance(result, PreparedExecution)
    assert Execution not in context.rows
    context.session.add.assert_not_called()
    assert result.identity == context.identity
    assert result.input_data == context.envelope.model_dump(mode="json")
    assert result.binding.execution_principal_id == service_principal_id("worker.ao.svc")
    assert result.execution().status == ExecutionStatus.PENDING
    assert context.events == ["begin", "provider", "capacity", "commit"]


async def test_full_workflow_capacity_refuses_new_preparation(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    context.capacity.side_effect = None
    context.capacity.return_value = 2
    assert await context.prepare() == ExecutionCapacityUnavailable(limit=2, active=2)
    context.session.add.assert_not_called()


async def test_unavailable_runtime_is_not_a_content_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    context.provider.side_effect = SafeValueError("Unavailable")
    assert await context.prepare() == PreparationBlocked()
    context.session.add.assert_not_called()


async def test_current_publication_is_required_for_new_work(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    context.workflow.is_enabled = False
    assert await context.prepare() == RevisionChanged()
    context.provider.assert_not_awaited()


async def test_payload_validation_does_not_add_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    context.subscription.input_schema = {"type": "object", "properties": {"extra": {"default": 3}}}
    result = await context.prepare()
    assert isinstance(result, PreparedExecution)
    assert result.input_data == context.envelope.model_dump(mode="json")


async def test_input_schema_failure_does_not_create_work(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    context.subscription.input_schema = {"type": "array"}
    context.snapshot = context.snapshot.model_copy(update={"input_schema": {"type": "array"}})
    assert await context.prepare() == EventDecodeFailure(code=EventFailureCode.schema_mismatch)
    context.provider.assert_not_awaited()


async def test_complete_arguments_are_limited_without_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    assert prepared.encoded_arguments_size() > encoded_envelope_size(context.envelope)
    context.settings.event_max_envelope_bytes = prepared.encoded_arguments_size() - 1
    assert await context.prepare() == EventDecodeFailure(code=EventFailureCode.envelope_too_large)
    context.session.add.assert_not_called()


async def test_source_coordinates_cannot_be_selected_by_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    context = preparation_context(monkeypatch)
    context.envelope = context.envelope.model_copy(
        update={"source_metadata": context.envelope.source_metadata.model_copy(update={"offset": "99"})}
    )
    with pytest.raises(ValueError, match="trusted source identity"):
        await context.prepare()
