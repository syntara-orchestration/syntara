"""Transactional projection of published workflow triggers into subscriptions.

This service runs inside the workflow publication transaction and shares its
session; it never commits, performs broker/Temporal I/O, or imports
``WorkflowService``. It diffs the ``event_subscribe_trigger`` nodes of the
published workflow definition against the persisted subscription projection and
creates, updates or retires subscriptions and their source generations so that
unpublish and same-source republish preserve source identity, generated group and
reading progress.

It also owns the lifecycle locking interface, the immutable
``SubscriptionSnapshot`` builder, and the conservative deletion guards that
protect bound workflow/Integration/credential resources. Recovery-aware release
of those guards is a later story.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID

import structlog
from pydantic import ConfigDict
from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.core.models.installation import Installation
from syntara.core.services import BaseService
from syntara.credentials.models.credential import Credential
from syntara.eventstreams.adapters.source_projection import (
    project_source_configuration,
    source_address_identity,
)
from syntara.eventstreams.adapters.subscribe_parameters import validate_event_subscribe_parameters
from syntara.eventstreams.exceptions import EventStreamError, EventSubscriptionInUseError
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.integrations.models.integration import Integration
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType

if TYPE_CHECKING:
    from syntara.eventstreams.core.subscribe_parameters import EventSubscribeParameters
    from syntara.workflows.models.workflow import Workflow
    from syntara.workflows.models.workflow_version import WorkflowVersion

logger = structlog.stdlib.get_logger(__name__)

_RESOURCE_WORKFLOW = "workflow"
_RESOURCE_INTEGRATION = "integration"
_RESOURCE_CREDENTIAL = "credential"


class SubscriptionChangeSet(SQLModel):
    """Summary of subscription lifecycle changes from one publication sync.

    Carries sanitized references only (identifiers and immutable snapshots); it is
    safe for audit hints and never contains secrets or event payloads.
    """

    created: list[SubscriptionSnapshot] = []
    updated: list[SubscriptionSnapshot] = []
    retired: list[UUID] = []
    disabled: list[UUID] = []

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]

    def is_empty(self) -> bool:
        """Return whether no subscription changed in this sync."""
        return not (self.created or self.updated or self.retired or self.disabled)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class EventSubscriptionService(BaseService):
    """Project and reconcile event subscriptions within the publication transaction."""

    def __init__(self, session: AsyncSession, user: User) -> None:
        """Initialize with the shared publication session and the acting user."""
        super().__init__(session, user)

    # ------------------------------------------------------------------
    # Publication projection
    # ------------------------------------------------------------------
    async def sync_from_published_definition(
        self,
        workflow: "Workflow",
        version: "WorkflowVersion | None" = None,
        *,
        enabled: bool,
    ) -> SubscriptionChangeSet:
        """Project the published definition's Subscribe triggers into subscriptions.

        When ``enabled`` is False (unpublish) every non-retired subscription for the
        workflow has its desired state disabled while identity, group and progress
        are retained; ``version`` may be None in that case. Otherwise subscriptions
        are created/updated for the published Subscribe nodes and any subscription
        whose trigger node disappeared is retired without deleting its evidence.
        """
        changeset = SubscriptionChangeSet()
        existing = await self.lock_workflow_subscriptions(workflow.id)
        existing_by_node = {sub.trigger_node_id: sub for sub in existing}

        if not enabled:
            for sub in existing:
                if sub.desired_enabled:
                    sub.desired_enabled = False
                    sub.configuration_revision += 1
                    sub.updated_by = self.user.id
                    changeset.disabled.append(sub.id)
            await self.session.flush()
            return changeset

        if version is None:
            msg = "A published version is required to project enabled subscriptions"
            raise EventStreamError(msg)

        deployment_id = await self._get_deployment_id()
        published_nodes = self._extract_event_subscribe_nodes(version.workflow_definition)

        for node_id, raw_parameters in published_nodes.items():
            integration, parameters = await self._resolve_binding(raw_parameters, workflow.project_id)
            existing_sub = existing_by_node.pop(node_id, None)
            if existing_sub is None:
                snapshot = await self._create_subscription(
                    workflow, version, node_id, integration, parameters, deployment_id
                )
                changeset.created.append(snapshot)
            else:
                snapshot = await self._update_subscription(
                    existing_sub, version, integration, parameters, deployment_id
                )
                changeset.updated.append(snapshot)

        # Any non-retired subscription whose trigger node is gone is retired.
        for stale_sub in existing_by_node.values():
            await self._retire_subscription(stale_sub)
            changeset.retired.append(stale_sub.id)

        await self.session.flush()
        return changeset

    async def _create_subscription(
        self,
        workflow: "Workflow",
        version: "WorkflowVersion",
        node_id: str,
        integration: Integration,
        parameters: "EventSubscribeParameters",
        deployment_id: UUID,
    ) -> SubscriptionSnapshot:
        """Create a new subscription and its first source generation."""
        subscription = EventSubscription(
            workflow_id=workflow.id,
            project_id=workflow.project_id,
            trigger_node_id=node_id,
            published_version_id=version.id,
            active_source_generation=1,
            configuration_revision=1,
            runtime_credential_id=parameters.credential_id,
            input_schema=parameters.input_schema,
            desired_enabled=True,
            paused=False,
            retired=False,
            enabled_by=self.user.id,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(subscription)
        await self.session.flush()  # assign subscription.id for group/source identity

        source = self._build_source(subscription, integration, parameters, deployment_id, generation=1)
        self.session.add(source)
        await self.session.flush()
        return SubscriptionSnapshot.from_models(subscription, source)

    async def _update_subscription(
        self,
        subscription: EventSubscription,
        version: "WorkflowVersion",
        integration: Integration,
        parameters: "EventSubscribeParameters",
        deployment_id: UUID,
    ) -> SubscriptionSnapshot:
        """Update an existing subscription, replacing the source only on identity change."""
        active_source = await self._get_source(subscription.id, subscription.active_source_generation)
        if active_source is None:
            msg = "Active source generation is missing for an existing subscription"
            raise EventStreamError(msg)

        candidate = project_source_configuration(
            parameters,
            deployment_id=deployment_id,
            subscription_id=subscription.id,
            generation=active_source.generation,
        )
        source_changed = (
            active_source.integration_identity != integration.id
            or active_source.transport != candidate.transport
            or source_address_identity(active_source.configuration) != source_address_identity(candidate)
        )

        active = active_source
        if source_changed:
            active_source.retired_at = _utc_now()
            next_generation = await self._next_generation(subscription.id)
            active = self._build_source(
                subscription, integration, parameters, deployment_id, generation=next_generation
            )
            self.session.add(active)
            subscription.active_source_generation = next_generation

        config_changed = (
            source_changed
            or subscription.runtime_credential_id != parameters.credential_id
            or subscription.input_schema != parameters.input_schema
            or not subscription.desired_enabled
        )

        subscription.published_version_id = version.id
        subscription.runtime_credential_id = parameters.credential_id
        subscription.input_schema = parameters.input_schema
        subscription.desired_enabled = True
        subscription.enabled_by = self.user.id
        subscription.updated_by = self.user.id
        if config_changed:
            subscription.configuration_revision += 1

        await self.session.flush()
        return SubscriptionSnapshot.from_models(subscription, active)

    async def _retire_subscription(self, subscription: EventSubscription) -> None:
        """Retire a subscription whose trigger node was removed; preserve its evidence."""
        subscription.retired = True
        subscription.desired_enabled = False
        subscription.configuration_revision += 1
        subscription.updated_by = self.user.id
        active_source = await self._get_source(subscription.id, subscription.active_source_generation)
        if active_source is not None and active_source.retired_at is None:
            active_source.retired_at = _utc_now()

    def _build_source(
        self,
        subscription: EventSubscription,
        integration: Integration,
        parameters: "EventSubscribeParameters",
        deployment_id: UUID,
        *,
        generation: int,
    ) -> EventSubscriptionSource:
        """Build a source generation row with its projected typed configuration."""
        configuration = project_source_configuration(
            parameters,
            deployment_id=deployment_id,
            subscription_id=subscription.id,
            generation=generation,
        )
        return EventSubscriptionSource(
            subscription_id=subscription.id,
            deployment_id=deployment_id,
            generation=generation,
            integration_id=integration.id,
            integration_identity=integration.id,
            transport=configuration.transport,
            configuration=configuration,
        )

    async def _resolve_binding(
        self, raw_parameters: dict[str, Any], project_id: UUID
    ) -> tuple[Integration, "EventSubscribeParameters"]:
        """Load and validate the Integration and runtime credential for activation.

        Enforces the activation-time resource checks — Integration enablement and
        runtime credential project scope/availability — so an enabling publish,
        including one that republishes an existing version without an inline
        definition, never activates a subscription against an out-of-scope or
        unavailable binding. These are the existing project/resource checks; no
        ``execution:run`` gate is introduced.

        By design, actor-facing Integration *visibility* and ``credential:use``
        are selection-time checks applied when the trigger is edited/saved or
        tested, not on publish: publish/republish requires only ``workflow:update``
        plus publication/project-scope/availability, and these resource-access
        checks do not establish standing execution grants (per the Kafka event
        streams design baseline). Re-enabling a frozen version therefore does not
        re-run visibility/``credential:use``, matching webhook/scheduled publish.
        """
        try:
            parameters = validate_event_subscribe_parameters(raw_parameters)
        except (TypeError, ValueError) as exc:
            msg = "Invalid Event Subscribe trigger parameters"
            raise SafeValueError(msg) from exc
        integration = await self.session.get(Integration, parameters.integration_id)
        if integration is None:
            msg = "Event Subscribe references an Integration that does not exist"
            raise SafeValueError(msg)
        # Re-validate against the resolved Integration type so the transport-specific
        # subclass (e.g. KafkaSubscribeParameters) is returned for source projection,
        # and an Integration type that cannot drive a subscription is rejected.
        try:
            parameters = validate_event_subscribe_parameters(
                raw_parameters, integration_type=integration.integration_type.value
            )
        except (TypeError, ValueError) as exc:
            msg = "Event Subscribe transport does not match the selected Integration type"
            raise SafeValueError(msg) from exc
        if not integration.enabled:
            msg = "Event Subscribe Integration is disabled"
            raise SafeValueError(msg)

        credential = await self.session.get(Credential, parameters.credential_id)
        if credential is None:
            msg = "Event Subscribe runtime credential is invalid"
            raise SafeValueError(msg)
        if credential.project_id != project_id:
            msg = "Event Subscribe runtime credential belongs to a different project"
            raise SafeValueError(msg)
        if not credential.enabled:
            msg = "Event Subscribe runtime credential is disabled"
            raise SafeValueError(msg)
        return integration, parameters

    # ------------------------------------------------------------------
    # Lifecycle locking / snapshot interfaces
    # ------------------------------------------------------------------
    async def lock_workflow_subscriptions(self, workflow_id: UUID) -> list[EventSubscription]:
        """Lock and return the non-retired subscriptions for a workflow (FOR UPDATE).

        Shared lifecycle lock used by publication and by any operation that must
        serialize against superseded state.
        """
        statement = (
            select(EventSubscription)
            .where(col(EventSubscription.workflow_id) == workflow_id)
            .where(col(EventSubscription.retired).is_(False))
            .with_for_update()
        )
        result = await self.session.exec(statement)
        return list(result.all())

    async def build_snapshot(self, subscription: EventSubscription) -> SubscriptionSnapshot | None:
        """Build the immutable snapshot for a subscription's active source."""
        active_source = await self._get_source(subscription.id, subscription.active_source_generation)
        if active_source is None:
            return None
        return SubscriptionSnapshot.from_models(subscription, active_source)

    # ------------------------------------------------------------------
    # Conservative deletion guards
    # ------------------------------------------------------------------
    async def assert_workflow_not_bound(self, workflow_id: UUID, workflow_name: str) -> None:
        """Block workflow deletion while any subscription references it."""
        count = await self._count_subscriptions(col(EventSubscription.workflow_id) == workflow_id)
        if count:
            raise EventSubscriptionInUseError(_RESOURCE_WORKFLOW, workflow_name, count)

    async def assert_integration_not_bound(self, integration_id: UUID, integration_name: str) -> None:
        """Block Integration deletion while any source references it."""
        statement = (
            select(func.count())
            .select_from(EventSubscriptionSource)
            .where(col(EventSubscriptionSource.integration_id) == integration_id)
        )
        count = (await self.session.exec(statement)).one()
        if count:
            raise EventSubscriptionInUseError(_RESOURCE_INTEGRATION, integration_name, count)

    async def assert_credential_not_bound(self, credential_id: UUID, credential_name: str) -> None:
        """Block credential deletion while any subscription references it as runtime credential."""
        count = await self._count_subscriptions(col(EventSubscription.runtime_credential_id) == credential_id)
        if count:
            raise EventSubscriptionInUseError(_RESOURCE_CREDENTIAL, credential_name, count)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _count_subscriptions(self, condition: ColumnElement[bool]) -> int:
        statement = select(func.count()).select_from(EventSubscription).where(condition)
        return (await self.session.exec(statement)).one()

    async def _get_source(self, subscription_id: UUID, generation: int) -> EventSubscriptionSource | None:
        statement = (
            select(EventSubscriptionSource)
            .where(col(EventSubscriptionSource.subscription_id) == subscription_id)
            .where(col(EventSubscriptionSource.generation) == generation)
        )
        return (await self.session.exec(statement)).first()

    async def _next_generation(self, subscription_id: UUID) -> int:
        statement = select(func.max(EventSubscriptionSource.generation)).where(
            col(EventSubscriptionSource.subscription_id) == subscription_id
        )
        current_max = (await self.session.exec(statement)).one()
        return (current_max or 0) + 1

    async def _get_deployment_id(self) -> UUID:
        installation = (await self.session.exec(select(Installation))).first()
        if installation is None:
            msg = "Installation row is missing; deployment namespace is unavailable"
            raise EventStreamError(msg)
        return installation.id

    @staticmethod
    def _extract_event_subscribe_nodes(workflow_definition: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Map trigger node id to its parameters for every Subscribe trigger node.

        Fails closed on a duplicate Subscribe trigger node id rather than silently
        last-wins: a dropped configuration would never be projected, leaving the
        designer with a subscription they did not intend.
        """
        nodes: dict[str, dict[str, Any]] = {}
        for trigger in workflow_definition.get("triggers", []):
            if trigger.get("type") != NodeType.EVENT_SUBSCRIBE_TRIGGER:
                continue
            node_id = trigger.get("id")
            if not node_id:
                continue
            if node_id in nodes:
                msg = "Duplicate Event Subscribe trigger node id in the published definition"
                raise SafeValueError(msg)
            nodes[node_id] = trigger.get("parameters", {})
        return nodes
