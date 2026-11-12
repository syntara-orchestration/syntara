"""Prepare detached event workflow arguments without creating durable work."""

from collections.abc import Callable
from contextlib import nullcontext
from copy import deepcopy
from datetime import UTC, datetime

from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import get_settings
from syntara.core.exceptions import SafeValueError
from syntara.core.models.principal import service_principal_id
from syntara.eventstreams.adapters.record_identity import record_matches_metadata, record_matches_source
from syntara.eventstreams.core.deduplication import (
    DeliveryIdentity,
    FrozenDeliveryBinding,
    RevisionChanged,
    input_fingerprint,
)
from syntara.eventstreams.core.envelope import WorkflowEventEnvelope
from syntara.eventstreams.core.preparation import ExecutionCapacityUnavailable, PreparationBlocked, PreparedExecution
from syntara.eventstreams.core.results import EventDecodeFailure, EventFailureCode
from syntara.eventstreams.core.serialization import validate_payload
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.connection_provider import EventConnectionProvider
from syntara.eventstreams.services.subscription_service import lock_source_lifecycle
from syntara.eventstreams.services.worker_resources import EventWorkerResources
from syntara.integrations.exceptions import IntegrationCredentialNotFoundError
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.services.execution_service import count_active_executions
from syntara.workflows.utils.workflow_metadata import build_workflow_metadata, resolve_user_display_name
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType, resolve_trigger_node

type PreparationResult = (
    PreparedExecution | RevisionChanged | ExecutionCapacityUnavailable | PreparationBlocked | EventDecodeFailure
)


class EventExecutionPreparationService:
    """Use a short read transaction for current lifecycle, resources and soft capacity."""

    def __init__(
        self, session_factory: Callable[..., AsyncSession], *, resources: EventWorkerResources | None = None
    ) -> None:
        """Receive the session factory and process-owned preparation bound."""
        self._sessions = session_factory
        self._resources = resources

    async def prepare_delivery(
        self, snapshot: SubscriptionSnapshot, identity: DeliveryIdentity, envelope: WorkflowEventEnvelope
    ) -> PreparationResult:
        """Return detached start arguments; acceptance and persistence happen later."""
        async with self._resources.preparation if self._resources is not None else nullcontext():
            if self._resources is not None and (not self._resources.accepting or not self._resources.scheduling_open):
                return PreparationBlocked()
            async with self._sessions() as session, session.begin():
                if self._resources is not None and (
                    not self._resources.accepting or not self._resources.scheduling_open
                ):
                    return PreparationBlocked()
                return await self._prepare(session, snapshot, identity, envelope)

    async def _prepare(
        self,
        session: AsyncSession,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        envelope: WorkflowEventEnvelope,
    ) -> PreparationResult:
        lifecycle = await lock_source_lifecycle(session, identity.source_id)
        if lifecycle is None:
            return RevisionChanged()
        current = SubscriptionSnapshot.from_models(*lifecycle, prepare_filter=False)
        workflow = await session.get(Workflow, identity.workflow_id)
        version = await session.get(WorkflowVersion, snapshot.published_version_id)
        if (
            current.published_version_id != snapshot.published_version_id
            or current.configuration_revision != snapshot.configuration_revision
            or current.workflow_id != identity.workflow_id
            or current.subscription_id != identity.subscription_id
            or current.source_generation != identity.source_generation
            or current.deployment_id != identity.deployment_id
            or current.integration_identity != identity.integration_identity
            or not record_matches_source(identity.record, current.configuration)
            or not current.desired_enabled
            or current.paused
            or current.retired
            or lifecycle[1].retired_at is not None
            or workflow is None
            or version is None
            or not workflow.is_enabled
            or workflow.published_version_id != version.id
            or version.workflow_id != workflow.id
            or workflow.project_id != snapshot.project_id
        ):
            return RevisionChanged()
        snapshot = current
        failure = self._validate_content(snapshot, identity, envelope, version)
        if failure is not None:
            return failure
        try:
            connection = await EventConnectionProvider(session).resolve_revision(snapshot)
        except (SafeValueError, IntegrationCredentialNotFoundError):
            return PreparationBlocked()
        settings = get_settings()
        active = await count_active_executions(session) if settings.max_concurrent_workflows > 0 else 0
        if settings.max_concurrent_workflows > 0 and active >= settings.max_concurrent_workflows:
            return ExecutionCapacityUnavailable(limit=settings.max_concurrent_workflows, active=active)
        return await self._arguments(session, snapshot, identity, envelope, workflow, version, connection.digest)

    @staticmethod
    def _validate_content(
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        envelope: WorkflowEventEnvelope,
        version: WorkflowVersion,
    ) -> RevisionChanged | EventDecodeFailure | None:
        metadata = envelope.source_metadata
        if (
            metadata.integration_id != identity.integration_identity
            or metadata.subscription_id != identity.subscription_id
            or metadata.source_generation != identity.source_generation
            or not record_matches_metadata(identity.record, metadata)
        ):
            msg = "Event envelope does not match its trusted source identity"
            raise ValueError(msg)
        _, trigger = resolve_trigger_node(version.workflow_definition, snapshot.trigger_node_id)
        if trigger.get("type") != NodeType.EVENT_SUBSCRIBE_TRIGGER:
            return RevisionChanged()
        return validate_payload(envelope, snapshot.model_dump(mode="json")["input_schema"])

    @staticmethod
    async def _arguments(
        session: AsyncSession,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        envelope: WorkflowEventEnvelope,
        workflow: Workflow,
        version: WorkflowVersion,
        connection_revision: str,
    ) -> PreparedExecution | EventDecodeFailure:
        settings = get_settings()
        metadata = envelope.source_metadata
        principal_id, now = service_principal_id(settings.service_identity), datetime.now(UTC)
        author = await resolve_user_display_name(session, workflow.created_by)
        context = build_workflow_metadata(
            workflow_name=workflow.name,
            workflow_id=workflow.id,
            workflow_version=version.version,
            workflow_published=True,
            workflow_author=author,
            project_id=workflow.project_id,
            execution_id=str(identity.execution_id),
            execution_mode="event",
            created_by=author,
            created_by_user_id=str(workflow.created_by),
            created_at=now.isoformat(),
            workflow_version_id=version.id,
        )
        context["event"] = {
            "identity": identity.model_dump(mode="json"),
            "enabled_by": str(snapshot.enabled_by) if snapshot.enabled_by is not None else None,
            "trigger_node_id": snapshot.trigger_node_id,
            "workflow_version_id": str(version.id),
            "configuration_revision": snapshot.configuration_revision,
            "runtime_credential_id": str(snapshot.runtime_credential_id),
            "connection_revision": connection_revision,
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
            connection_revision=connection_revision,
            execution_principal_id=principal_id,
            enabled_by=snapshot.enabled_by,
            received_at=metadata.received_at,
            prepared_at=now,
            input_fingerprint=input_fingerprint(input_data, context),
        )
        prepared = PreparedExecution(
            identity=identity,
            binding=binding,
            execution_id=identity.execution_id,
            temporal_workflow_id=identity.temporal_workflow_id,
            workflow_version_id=version.id,
            workflow_definition=deepcopy(version.workflow_definition),
            trigger_node_id=snapshot.trigger_node_id,
            input_data=input_data,
            workflow_metadata=context,
            is_builtin=workflow.is_builtin,
        )
        if prepared.encoded_arguments_size() > settings.event_max_envelope_bytes:
            return EventDecodeFailure(code=EventFailureCode.envelope_too_large)
        return prepared
