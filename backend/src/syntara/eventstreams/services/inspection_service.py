"""Read current subscription projections and preflight unsaved bindings."""

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import tuple_
from sqlmodel import col, select

from syntara.core.exceptions import SafeValueError
from syntara.core.services import BaseService
from syntara.eventstreams.adapters.kafka_parameters import KafkaSubscribeParameters
from syntara.eventstreams.adapters.kafka_preflight import test_kafka_connection
from syntara.eventstreams.exceptions import EventSubscriptionNotFoundError
from syntara.eventstreams.models.responses import (
    EventSubscriptionListParams,
    EventSubscriptionListResponse,
    EventSubscriptionRead,
    EventSubscriptionSourceRead,
    EventSubscriptionTestResponse,
)
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.integrations.models.integration import Integration
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.integrations.services.integration_service import IntegrationService
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
        self, session: "AsyncSession", user: "User", evaluator: "AuthzEvaluator", secret_service: "SecretService"
    ) -> None:
        """Reuse workflow resource checks and platform credential resolution."""
        super().__init__(session, user)
        self.workflows = WorkflowService(session, user, evaluator)
        self.integrations = IntegrationService(session, user, secret_service)

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

        sources: dict[UUID, EventSubscriptionSource] = {}

        async def load_sources(subscriptions: list[EventSubscription]) -> None:
            if subscriptions:
                result = await self.session.exec(
                    select(EventSubscriptionSource).where(
                        tuple_(
                            col(EventSubscriptionSource.subscription_id), col(EventSubscriptionSource.generation)
                        ).in_([(s.id, s.active_source_generation) for s in subscriptions])
                    )
                )
                generations = {s.id: s.active_source_generation for s in subscriptions}
                sources.update(
                    {s.subscription_id: s for s in result.all() if s.generation == generations[s.subscription_id]}
                )

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
            response_type_converter=lambda sub: self._shape(sub, sources[sub.id]),
            post_query_callback=load_sources,
            limit=params.limit,
            cursor=params.cursor,
            sort=params.sort,
            include_total=params.include_total,
            query_params_items=items,
            special_field_handlers={"workflow_id": scope},
        )

    async def get_current(self, workflow_id: UUID, subscription_id: UUID) -> EventSubscriptionRead:
        """Return only a current source belonging to this workflow and project."""
        workflow = await self.workflows.get_workflow_by_id(workflow_id)
        result = await self.session.exec(
            select(EventSubscription, EventSubscriptionSource)
            .join(EventSubscriptionSource, col(EventSubscriptionSource.subscription_id) == EventSubscription.id)
            .where(
                EventSubscription.id == subscription_id,
                EventSubscription.workflow_id == workflow.id,
                EventSubscription.project_id == workflow.project_id,
                col(EventSubscription.retired).is_(False),
                EventSubscriptionSource.generation == EventSubscription.active_source_generation,
                col(EventSubscriptionSource.retired_at).is_(None),
            )
        )
        row = result.one_or_none()
        if row is None:
            raise EventSubscriptionNotFoundError
        return self._shape(*row)

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
        credential = await self.integrations.resolve_credential(parameters.credential_id)
        return await test_kafka_connection(integration.configuration, credential, parameters.topic)
