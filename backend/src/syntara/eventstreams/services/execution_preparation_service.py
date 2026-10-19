"""Deterministic event Execution preparation; no Temporal or broker calls."""

from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime

from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import Settings, get_settings
from syntara.core.exceptions import SafeValueError
from syntara.core.models.principal import service_principal_id
from syntara.eventstreams.adapters.record_identity import record_matches_metadata
from syntara.eventstreams.core.deduplication import (
    ClaimBusy,
    ClaimLost,
    DeliveryCapacityCheck,
    DeliveryClaim,
    DeliveryExpectation,
    DeliveryIdentity,
    FrozenDeliveryBinding,
    RevisionChanged,
    StorageBackpressure,
    TerminalDelivery,
    input_fingerprint,
)
from syntara.eventstreams.core.envelope import WorkflowEventEnvelope
from syntara.eventstreams.core.preparation import ExecutionCapacityUnavailable, PreparationBlocked, PreparedExecution
from syntara.eventstreams.core.results import EventDecodeFailure, EventFailureCode
from syntara.eventstreams.core.scheduling_metadata import EVENT_DELIVERY_METADATA_KEY
from syntara.eventstreams.core.serialization import validate_payload
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.connection_provider import EventConnectionProvider
from syntara.eventstreams.services.deduplication_store import EventDeliveryStore
from syntara.eventstreams.services.subscription_service import lock_source_lifecycle
from syntara.integrations.exceptions import IntegrationCredentialNotFoundError
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.services.execution_service import count_active_executions
from syntara.workflows.utils.workflow_metadata import build_workflow_metadata, resolve_user_display_name
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType, resolve_trigger_node

type PreparationResult = (
    PreparedExecution
    | ClaimBusy
    | ClaimLost
    | RevisionChanged
    | StorageBackpressure
    | TerminalDelivery
    | ExecutionCapacityUnavailable
    | PreparationBlocked
    | EventDecodeFailure
)


class _PreparationRefusedError(Exception):
    """Roll back provisional acquisition before returning a safe non-prepared result."""

    def __init__(self, result: PreparationResult) -> None:
        self.result = result
        super().__init__(type(result).__name__)


def _require_prepared(result: PreparationResult) -> PreparedExecution:
    if not isinstance(result, PreparedExecution):
        raise _PreparationRefusedError(result)
    return result


class EventExecutionPreparationService:
    """Own one short transaction per preparation; never share a session across tasks."""

    def __init__(
        self,
        session_factory: Callable[..., AsyncSession],
        *,
        capacity_check: DeliveryCapacityCheck | None = None,
    ) -> None:
        """Inject the database factory and optional isolated delivery-capacity check."""
        self._session_factory = session_factory
        self._capacity_check = capacity_check

    async def prepare_delivery(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        envelope: WorkflowEventEnvelope | None,
        owner_worker_id: str,
        *,
        claim: DeliveryClaim | None = None,
    ) -> PreparationResult:
        """Commit preparation before returning; an existing claim may be recovered.

        A recovery caller may omit the envelope: durable input is authoritative.
        Any non-prepared result rolls back provisional writes. Existing evidence
        is retained, and no result from this method grants offset commit authority.
        """
        try:
            async with self._session_factory() as session, session.begin():
                result = _require_prepared(
                    await self._prepare(session, snapshot, identity, envelope, owner_worker_id, claim)
                )
            return result  # noqa: RET504 - return only after the transaction commits
        except _PreparationRefusedError as exc:
            return exc.result

    async def _prepare(
        self,
        session: AsyncSession,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        envelope: WorkflowEventEnvelope | None,
        owner_worker_id: str,
        claim: DeliveryClaim | None,
    ) -> PreparationResult:
        lifecycle = await lock_source_lifecycle(session, identity.source_id)
        if lifecycle is None:
            return RevisionChanged()
        settings = get_settings()
        store = EventDeliveryStore(session, capacity_check=self._capacity_check)
        acquired: DeliveryClaim | ClaimBusy | ClaimLost | TerminalDelivery | RevisionChanged | StorageBackpressure
        if claim is None:
            acquired = await store.acquire(
                identity,
                DeliveryExpectation(
                    published_version_id=snapshot.published_version_id,
                    configuration_revision=snapshot.configuration_revision,
                ),
                owner_worker_id,
            )
        else:
            if claim.identity != identity or claim.owner_worker_id != owner_worker_id:
                return ClaimLost()
            acquired = await store.renew(claim)
        if not isinstance(acquired, DeliveryClaim):
            return acquired
        if acquired.binding is not None:
            return await self._recover(session, acquired)
        current = SubscriptionSnapshot.from_models(*lifecycle)
        if (
            current.subscription_id != snapshot.subscription_id
            or current.workflow_id != snapshot.workflow_id
            or current.published_version_id != snapshot.published_version_id
            or current.configuration_revision != snapshot.configuration_revision
        ):
            return RevisionChanged()
        return await self._prepare_new(session, store, current, acquired, envelope, settings)

    @staticmethod
    def _prepared(claim: DeliveryClaim, execution: Execution, version: WorkflowVersion) -> PreparedExecution:
        context = {
            key: value
            for key, value in (execution.execution_metadata or {}).items()
            if key != EVENT_DELIVERY_METADATA_KEY
        }
        binding = claim.binding
        if (
            binding is None
            or execution.id != claim.identity.execution_id
            or execution.workflow_id != claim.identity.workflow_id
            or execution.workflow_version_id != binding.workflow_version_id
            or version.id != binding.workflow_version_id
            or version.workflow_id != execution.workflow_id
            or execution.temporal_workflow_id != claim.identity.temporal_workflow_id
            or execution.created_by != binding.execution_principal_id
            or input_fingerprint(execution.input_data, context) != binding.input_fingerprint
            or execution.trigger_node_id is None
        ):
            msg = "Prepared Execution does not match retained delivery evidence"
            raise ValueError(msg)
        return PreparedExecution(
            claim=claim,
            execution_id=execution.id,
            temporal_workflow_id=execution.temporal_workflow_id,
            workflow_version_id=version.id,
            workflow_definition=deepcopy(version.workflow_definition),
            trigger_node_id=execution.trigger_node_id,
            input_data=deepcopy(execution.input_data),
            workflow_metadata=deepcopy(context),
            is_builtin=bool(context["event"]["is_builtin"]),
        )

    async def _recover(self, session: AsyncSession, claim: DeliveryClaim) -> PreparedExecution:
        """Load frozen state before any current-publication or new-capacity check."""
        if claim.binding is None:
            msg = "Recovery requires a frozen binding"
            raise ValueError(msg)
        execution = await session.get(Execution, claim.identity.execution_id, populate_existing=True)
        version = await session.get(WorkflowVersion, claim.binding.workflow_version_id)
        if execution is None or version is None:
            msg = "Prepared Execution evidence is unavailable"
            raise ValueError(msg)
        return self._prepared(claim, execution, version)

    @staticmethod
    def _validate_envelope(
        snapshot: SubscriptionSnapshot,
        claim: DeliveryClaim,
        envelope: WorkflowEventEnvelope | None,
        version: WorkflowVersion,
    ) -> WorkflowEventEnvelope | RevisionChanged | EventDecodeFailure:
        """Validate trusted coordinates and payload without generic wrapper defaults."""
        _, trigger = resolve_trigger_node(version.workflow_definition, snapshot.trigger_node_id)
        if trigger.get("type") != NodeType.EVENT_SUBSCRIBE_TRIGGER:
            return RevisionChanged()
        if envelope is None:
            msg = "New event preparation requires a decoded envelope"
            raise ValueError(msg)
        metadata = envelope.source_metadata
        if (
            metadata.integration_id != claim.identity.integration_identity
            or metadata.subscription_id != claim.identity.subscription_id
            or metadata.source_generation != claim.identity.source_generation
            or not record_matches_metadata(claim.identity.record, metadata)
        ):
            msg = "Event envelope does not match its trusted delivery identity"
            raise ValueError(msg)
        failure = validate_payload(envelope, snapshot.model_dump(mode="json")["input_schema"])
        return failure if failure is not None else envelope

    async def _prepare_new(
        self,
        session: AsyncSession,
        store: EventDeliveryStore,
        snapshot: SubscriptionSnapshot,
        claim: DeliveryClaim,
        envelope: WorkflowEventEnvelope | None,
        settings: Settings,
    ) -> PreparationResult:
        workflow = await session.get(Workflow, snapshot.workflow_id)
        version = await session.get(WorkflowVersion, snapshot.published_version_id)
        if (
            workflow is None
            or version is None
            or not workflow.is_enabled
            or workflow.published_version_id != snapshot.published_version_id
            or version.workflow_id != workflow.id
            or workflow.project_id != snapshot.project_id
            or not snapshot.desired_enabled
            or snapshot.paused
            or snapshot.retired
        ):
            return RevisionChanged()
        validated = self._validate_envelope(snapshot, claim, envelope, version)
        if not isinstance(validated, WorkflowEventEnvelope):
            return validated
        envelope = validated
        metadata = envelope.source_metadata
        try:
            connection = await EventConnectionProvider(session).resolve_revision(snapshot)
        except (SafeValueError, IntegrationCredentialNotFoundError):
            return PreparationBlocked()
        limit = settings.max_concurrent_workflows
        if limit > 0:
            active = await count_active_executions(session)
            if active >= limit:
                return ExecutionCapacityUnavailable(limit=limit, active=active)
        principal_id = service_principal_id(settings.service_identity)
        now = datetime.now(UTC)
        author = await resolve_user_display_name(session, workflow.created_by)
        context = build_workflow_metadata(
            workflow_name=workflow.name,
            workflow_id=workflow.id,
            workflow_version=version.version,
            workflow_published=True,
            workflow_author=author,
            project_id=workflow.project_id,
            execution_id=str(claim.identity.execution_id),
            execution_mode="event",
            created_by=author,
            created_by_user_id=str(workflow.created_by),
            created_at=now.isoformat(),
            workflow_version_id=version.id,
        )
        context["event"] = {
            "identity": claim.identity.model_dump(mode="json"),
            "enabled_by": str(snapshot.enabled_by) if snapshot.enabled_by is not None else None,
            "trigger_node_id": snapshot.trigger_node_id,
            "workflow_version_id": str(version.id),
            "configuration_revision": snapshot.configuration_revision,
            "runtime_credential_id": str(snapshot.runtime_credential_id),
            "connection_revision": connection.digest,
            "received_at": metadata.received_at.isoformat(),
            "prepared_at": now.isoformat(),
            "execution_principal_id": str(principal_id),
            "is_builtin": workflow.is_builtin,
        }
        input_data = envelope.model_dump(mode="json", by_alias=True)
        binding = FrozenDeliveryBinding(
            workflow_version_id=version.id,
            configuration_revision=snapshot.configuration_revision,
            runtime_credential_id=snapshot.runtime_credential_id,
            connection_revision=connection.digest,
            execution_principal_id=principal_id,
            enabled_by=snapshot.enabled_by,
            received_at=metadata.received_at,
            prepared_at=now,
            input_fingerprint=input_fingerprint(input_data, context),
        )
        execution = Execution(
            id=claim.identity.execution_id,
            workflow_id=workflow.id,
            workflow_version_id=version.id,
            project_id=workflow.project_id,
            temporal_workflow_id=claim.identity.temporal_workflow_id,
            status=ExecutionStatus.PENDING,
            trigger_node_id=snapshot.trigger_node_id,
            trigger_type=NodeType.EVENT_SUBSCRIBE_TRIGGER,
            input_data=input_data,
            execution_metadata=context,
            created_by=principal_id,
            updated_by=principal_id,
            created_at=now,
            updated_at=now,
        )
        prepared = self._prepared(claim.model_copy(update={"binding": binding}), execution, version)
        if prepared.encoded_arguments_size() > settings.event_max_envelope_bytes:
            return EventDecodeFailure(code=EventFailureCode.envelope_too_large)
        frozen = await store.freeze(claim, binding, execution)
        return prepared.model_copy(update={"claim": frozen}) if isinstance(frozen, DeliveryClaim) else frozen
