"""Read current subscription projections and preflight unsaved bindings."""

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlmodel import col, select

from syntara.core.exceptions import SafeValueError
from syntara.core.services import BaseService
from syntara.credentials.lib.kafka_connection import KafkaSecurityProtocol, resolve_listener_kafka_login


from syntara.eventstreams.adapters.kafka_initial_position import (
    KafkaPartitionInitialPosition,
    KafkaPartitionInitialPositionRead,
)
from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeParameters
from syntara.eventstreams.adapters.kafka_preflight import test_kafka_connection
from syntara.eventstreams.exceptions import EventSubscriptionNotFoundError
from syntara.eventstreams.models.control import EventSubscriptionRecovery, EventSubscriptionRuntime
from syntara.eventstreams.models.responses import (
    EventSubscriptionListParams,
    EventSubscriptionListResponse,
    EventSubscriptionRead,
    EventSubscriptionRecoveryRead,
    EventSubscriptionSourceRead,
    EventSubscriptionTestResponse,
)
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.services.control_service import EventSubscriptionControlService
from syntara.integrations.lib.url_validation import validate_integration_configuration_no_ssrf
from syntara.integrations.models.integration import Integration
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.services.workflow_service import WorkflowService

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.authz.evaluator import AuthzEvaluator
    from syntara.core.models import User
    from syntara.core.services.secret_service import SecretService
    from syntara.workflows.models.workflow import Workflow


class EventSubscriptionInspectionService(BaseService):
    """No persistence, publication or consumer activation operations."""

    def __init__(
        self,
        session: "AsyncSession",
        user: "User",
        evaluator: "AuthzEvaluator",
        secret_service: "SecretService",
        *,
        is_cert_authenticated: bool = False,
    ) -> None:
        """Reuse workflow resource checks and the listener credential resolver."""
        super().__init__(session, user)
        self.controls = EventSubscriptionControlService(
            session, user, evaluator, is_cert_authenticated=is_cert_authenticated
        )
        self.workflows = WorkflowService(session, user, evaluator, is_cert_authenticated=is_cert_authenticated)
        self.secret_service = secret_service

    @staticmethod
    def _shape(subscription: EventSubscription, source: EventSubscriptionSource) -> EventSubscriptionRead:
        return EventSubscriptionRead.model_validate(
            {**subscription.model_dump(), "source": EventSubscriptionSourceRead.model_validate(source)}
        )

    @staticmethod
    def _current_source_query(workflow: "Workflow", transport: str | None = None) -> Any:  # noqa: ANN401
        query = select(EventSubscriptionSource).where(
            EventSubscriptionSource.subscription_id == EventSubscription.id,
            EventSubscriptionSource.generation == EventSubscription.active_source_generation,
            col(EventSubscriptionSource.retired_at).is_(None),
            EventSubscription.workflow_id == workflow.id,
            EventSubscription.project_id == workflow.project_id,
            col(EventSubscription.retired).is_(False),
        )
        if transport is not None:
            query = query.where(EventSubscriptionSource.transport == transport)
        return query

    async def list_current(
        self, workflow_id: UUID, params: EventSubscriptionListParams, query_params: Iterable[tuple[str, str]]
    ) -> EventSubscriptionListResponse:
        """Apply parent scope to every page, count and cursor-existence query."""
        workflow = await self.workflows.get_workflow_by_id(workflow_id)
        source_query = self._current_source_query(workflow, params.transport)

        def scope(query: Any, _filter: Any, _model: Any) -> Any:  # noqa: ANN401
            return query.where(source_query.exists())

        responses: dict[UUID, EventSubscriptionRead] = {}

        async def load_status(subscriptions: list[EventSubscription]) -> None:
            responses.update(await self._read_subscriptions(subscriptions))

        # Parent/lifecycle restrictions are server-owned. Strip bracket variants
        # too so caller filters cannot turn these into OR expressions.
        items = [
            (k, v)
            for k, v in query_params
            if k.split("[", 1)[0] not in {"workflow_id", "project_id", "retired", "transport"}
        ]
        items.append(("workflow_id", str(workflow.id)))
        return await self.list_resources(
            EventSubscription,
            EventSubscriptionListResponse,
            response_type_converter=lambda sub: responses[sub.id],
            post_query_callback=load_status,
            limit=params.limit,
            cursor=params.cursor,
            sort=params.sort,
            include_total=params.include_total,
            query_params_items=items,
            special_field_handlers={"workflow_id": scope},
        )

    async def get_current(self, workflow_id: UUID, subscription_id: UUID) -> EventSubscriptionRead:
        """Read current or retired evidence belonging to this workflow and project."""
        workflow = await self.workflows.get_workflow_by_id(workflow_id)
        result = await self.session.exec(
            select(EventSubscription, EventSubscriptionSource)
            .join(EventSubscriptionSource, col(EventSubscriptionSource.subscription_id) == EventSubscription.id)
            .where(
                EventSubscription.id == subscription_id,
                EventSubscription.workflow_id == workflow.id,
                EventSubscription.project_id == workflow.project_id,
                EventSubscriptionSource.generation == EventSubscription.active_source_generation,
            )
        )
        row = result.one_or_none()
        if row is None:
            raise EventSubscriptionNotFoundError
        subscription, _source = row
        return (await self._read_subscriptions([subscription]))[subscription.id]

    async def _read_subscriptions(self, subscriptions: list[EventSubscription]) -> dict[UUID, EventSubscriptionRead]:
        """Populate list and detail state with a fixed number of page-scoped queries."""
        if not subscriptions:
            return {}
        sources = (
            await self.session.exec(
                select(EventSubscriptionSource)
                .where(col(EventSubscriptionSource.subscription_id).in_([item.id for item in subscriptions]))
                .order_by(col(EventSubscriptionSource.generation))
            )
        ).all()
        generations = {item.id: item.active_source_generation for item in subscriptions}
        current_sources = {
            item.subscription_id: item for item in sources if item.generation == generations[item.subscription_id]
        }
        responses = {item.id: self._shape(item, current_sources[item.id]) for item in subscriptions}
        source_owners = {item.id: item.subscription_id for item in sources}
        for source in sources:
            responses[source.subscription_id].sources.append(EventSubscriptionSourceRead.model_validate(source))
        positions = (
            await self.session.exec(
                select(KafkaPartitionInitialPosition)
                .where(col(KafkaPartitionInitialPosition.source_id).in_(source_owners))
                .order_by(col(KafkaPartitionInitialPosition.source_id), col(KafkaPartitionInitialPosition.partition))
            )
        ).all()
        for position in positions:
            responses[source_owners[position.source_id]].initialization.append(
                KafkaPartitionInitialPositionRead.from_position(position)
            )
        requests = (
            await self.session.exec(
                select(EventSubscriptionRecovery)
                .where(col(EventSubscriptionRecovery.source_id).in_(source_owners))
                .order_by(col(EventSubscriptionRecovery.source_id), col(EventSubscriptionRecovery.partition))
            )
        ).all()
        for request in requests:
            responses[source_owners[request.source_id]].recovery.append(
                EventSubscriptionRecoveryRead.model_validate(request)
            )
        runtimes = (
            await self.session.exec(
                select(EventSubscriptionRuntime).where(col(EventSubscriptionRuntime.source_id).in_(source_owners))
            )
        ).all()
        participants: dict[UUID, list[EventSubscriptionRuntime]] = {item.id: [] for item in subscriptions}
        for runtime in runtimes:
            participants[source_owners[runtime.source_id]].append(runtime)
        for subscription in subscriptions:
            convergence = await self.controls.response(
                subscription, current_sources[subscription.id], runtimes=participants[subscription.id]
            )
            response = responses[subscription.id]
            response.convergence, response.applied_revision = convergence.convergence, convergence.applied_revision
        return responses

    async def test_unsaved(
        self, workflow_id: UUID, parameters: KafkaSubscribeParameters
    ) -> EventSubscriptionTestResponse:
        """Check all references before decrypting the explicitly selected credential."""
        workflow = await self.workflows.get_workflow_by_id(workflow_id)
        await self.workflows.validate_event_subscribe_access(parameters.model_dump(mode="json"), workflow.project_id)
        integration = await self.session.get(Integration, parameters.integration_id)
        if integration is None or not isinstance(integration.configuration, KafkaConfiguration):
            msg = "Selected Kafka Integration is unavailable"
            raise SafeValueError(msg)
        # Recheck stored broker addresses before resolving secrets: DNS may have
        # changed since the Integration was created or last validated.
        try:
            validate_integration_configuration_no_ssrf(integration.configuration)
        except ValueError as exc:
            msg = "bootstrap_servers must not resolve to a private, reserved, or cloud metadata address."
            raise SafeValueError(msg) from exc
        credential = await resolve_listener_kafka_login(
            self.session,
            self.secret_service,
            runtime_credential_id=parameters.credential_id,
            security_protocol=KafkaSecurityProtocol.SASL_SSL,
        )
        return await test_kafka_connection(integration.configuration, credential or {}, parameters.topic)
