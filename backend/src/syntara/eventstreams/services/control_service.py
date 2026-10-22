"""Workflow-authorized, revision-checked subscription runtime actions."""

from typing import TYPE_CHECKING, Literal, cast
from uuid import UUID

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.engine import AuthzRequest, authorize
from syntara.authz.evaluator import AuthzEvaluator
from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.authz.models.project import Project
from syntara.core.models import User
from syntara.eventstreams.adapters.kafka_initial_position import KafkaPartitionInitialPosition
from syntara.eventstreams.exceptions import EventSubscriptionControlConflictError, EventSubscriptionNotFoundError
from syntara.eventstreams.models.control import EventSubscriptionRecovery, EventSubscriptionRuntime
from syntara.eventstreams.models.controls import (
    SubscriptionControlRequest,
    SubscriptionControlResponse,
    SubscriptionRecoveryRequest,
    SubscriptionRetireRequest,
)
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.connection_provider import EventConnectionProvider
from syntara.eventstreams.services.deduplication_store import EventDeliveryStore
from syntara.eventstreams.services.retirement_service import EventRetirementService, reject_content_gates
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.services.workflow_service import WorkflowService

if TYPE_CHECKING:
    from datetime import datetime


class EventSubscriptionControlService:
    """Commit PostgreSQL fences before responding; brokers run only in workers."""

    def __init__(
        self, session: AsyncSession, user: User, evaluator: AuthzEvaluator, *, is_cert_authenticated: bool = False
    ) -> None:
        """Reuse the request session and workflow access context."""
        self.session, self.user, self.evaluator = session, user, evaluator
        self.workflows = WorkflowService(session, user, evaluator, is_cert_authenticated=is_cert_authenticated)

    async def _load(
        self, workflow_id: UUID, subscription_id: UUID, body: SubscriptionControlRequest
    ) -> tuple[Workflow, EventSubscription, EventSubscriptionSource]:
        workflow = await self.workflows.get_workflow_by_id(workflow_id)
        authorized_project_id = workflow.project_id
        workflow = (
            await self.session.exec(
                select(Workflow)
                .where(Workflow.id == workflow.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).one()
        if workflow.project_id != authorized_project_id:
            msg = "workflow_project_changed"
            raise EventSubscriptionControlConflictError(msg)
        subscription = (
            await self.session.exec(
                select(EventSubscription)
                .where(
                    EventSubscription.id == subscription_id,
                    EventSubscription.workflow_id == workflow.id,
                    EventSubscription.project_id == workflow.project_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if subscription is None:
            raise EventSubscriptionNotFoundError
        source = (
            await self.session.exec(
                select(EventSubscriptionSource)
                .where(
                    EventSubscriptionSource.subscription_id == subscription.id,
                    EventSubscriptionSource.generation == body.source_generation,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if source is None or subscription.configuration_revision != body.configuration_revision:
            msg = "subscription_revision_changed"
            raise EventSubscriptionControlConflictError(msg)
        return workflow, subscription, source

    async def _grant(self, action: str, workflow: Workflow) -> None:
        project = await self.session.get(Project, workflow.project_id)
        if project is None:
            raise EventSubscriptionNotFoundError
        result = await authorize(
            self.session,
            self.evaluator,
            AuthzRequest(
                user_id=self.user.id,
                user_labels=self.user.labels or {},
                action=action,
                resource_type="event_subscription",
                resource_id=str(workflow.id),
                resource_project=project.name,
                resource_labels=workflow.labels or {},
            ),
        )
        if not result.allowed:
            msg = f"event_subscription:{action} is required"
            raise AuthorizationDeniedError(msg)

    @staticmethod
    def _active_source(subscription: EventSubscription, source: EventSubscriptionSource) -> None:
        if (
            subscription.retired
            or source.retired_at is not None
            or subscription.active_source_generation != source.generation
        ):
            msg = "source_retired_or_replaced"
            raise EventSubscriptionControlConflictError(msg)

    async def action(
        self,
        workflow_id: UUID,
        subscription_id: UUID,
        body: SubscriptionControlRequest,
        action: Literal["pause", "resume", "retry"],
    ) -> SubscriptionControlResponse:
        """Reuse workflow:update; retry never changes the frozen delivery context."""
        workflow, subscription, source = await self._load(workflow_id, subscription_id, body)
        self._active_source(subscription, source)
        if action != "pause":
            if (
                not workflow.is_enabled
                or workflow.published_version_id != subscription.published_version_id
                or not subscription.desired_enabled
            ):
                msg = "workflow_not_published"
                raise EventSubscriptionControlConflictError(msg)
            await EventRetirementService(self.session).assert_no_content_gate(source.id)
            await EventConnectionProvider(self.session).resolve_revision(
                SubscriptionSnapshot.from_models(subscription, source)
            )
        if action == "pause":
            subscription.paused = True
        elif action == "resume":
            subscription.paused = False
            subscription.enabled_by = self.user.id
        else:
            deliveries = await EventRetirementService(self.session).deliveries(source.id)
            reject_content_gates(deliveries)
            for delivery in deliveries:
                if delivery.frozen_binding is not None:
                    store = EventDeliveryStore(
                        self.session, execution_principal_id=delivery.frozen_binding.execution_principal_id
                    )
                    if not await store.request_scheduling_retry(delivery.delivery_identity()):
                        msg = "prepared_delivery_retry_busy"
                        raise EventSubscriptionControlConflictError(msg)
        # Every consumer observes a fresh revision, including explicit setup retry.
        # Frozen executions retain the earlier revision and are never re-prepared.
        subscription.configuration_revision += 1
        subscription.updated_by = self.user.id
        await self.session.flush()
        response = await self.response(subscription, source)
        await self.session.commit()
        return response

    async def recover(
        self, workflow_id: UUID, subscription_id: UUID, body: SubscriptionRecoveryRequest
    ) -> SubscriptionControlResponse:
        """Persist only an authorized policy; the current partition owner executes it."""
        workflow, subscription, source = await self._load(workflow_id, subscription_id, body)
        self._active_source(subscription, source)
        if (
            not workflow.is_enabled
            or workflow.published_version_id != subscription.published_version_id
            or not subscription.desired_enabled
            or subscription.paused
        ):
            msg = "active_published_source_required"
            raise EventSubscriptionControlConflictError(msg)
        await self._grant("recover", workflow)
        if body.resolve_unscheduled:
            await self._grant("retire", workflow)
        await EventRetirementService(self.session).assert_no_content_gate(source.id)
        position = await self.session.get(
            KafkaPartitionInitialPosition, (source.id, body.partition), with_for_update=True
        )
        if position is None or position.gap_detected_at is None:
            msg = "no_recorded_recovery_gap"
            raise EventSubscriptionControlConflictError(msg)
        if position.recovery_revision != body.expected_recovery_revision:
            msg = "recovery_revision_changed"
            raise EventSubscriptionControlConflictError(msg)
        reject_content_gates(await EventRetirementService(self.session).deliveries(source.id))
        key = (source.id, body.partition)
        existing = await self.session.get(EventSubscriptionRecovery, key, with_for_update=True)
        if existing is not None and not existing.completed:
            same_decision = existing.policy == body.policy.value and existing.reason == body.reason
            identical = (
                existing.configuration_revision == subscription.configuration_revision
                and existing.expected_recovery_revision == body.expected_recovery_revision
                and existing.acknowledge_duplicate_risk == body.acknowledge_duplicate_risk
                and existing.resolve_unscheduled == body.resolve_unscheduled
            )
            stale_configuration = existing.configuration_revision != subscription.configuration_revision
            if not same_decision or (not identical and position.recovery_token is None and not stale_configuration):
                msg = "recovery_request_pending"
                raise EventSubscriptionControlConflictError(msg)
        request = EventSubscriptionRecovery(
            source_id=source.id,
            partition=body.partition,
            configuration_revision=subscription.configuration_revision,
            expected_recovery_revision=body.expected_recovery_revision,
            policy=body.policy.value,
            reason=body.reason,
            acknowledge_duplicate_risk=body.acknowledge_duplicate_risk,
            resolve_unscheduled=body.resolve_unscheduled,
            requested_by=self.user.id,
        )
        if existing is not None:
            await self.session.delete(existing)
            await self.session.flush()
        self.session.add(request)
        await self.session.flush()
        response = SubscriptionControlResponse(
            subscription_id=subscription.id,
            source_id=source.id,
            configuration_revision=subscription.configuration_revision,
            source_generation=source.generation,
            convergence="pending",
        )
        await self.session.commit()
        return response

    async def retire(
        self, workflow_id: UUID, subscription_id: UUID, body: SubscriptionRetireRequest
    ) -> SubscriptionControlResponse:
        """Ordinary safe retirement needs workflow authority; disposition is exceptional."""
        workflow, subscription, source = await self._load(workflow_id, subscription_id, body)
        if body.resolve_unscheduled:
            await self._grant("retire", workflow)
        await EventRetirementService(self.session).retire(source, resolve_unscheduled=body.resolve_unscheduled)
        source.retirement_reason = body.reason
        source.retirement_authorized_by = self.user.id
        source.retirement_completed_at = cast(
            "datetime", (await self.session.exec(select(func.clock_timestamp()))).one()
        )
        retirement = EventRetirementService(self.session)
        if await retirement.can_detach(source):
            source.integration_id = None
        if subscription.retired:
            sources = (
                await self.session.exec(
                    select(EventSubscriptionSource)
                    .where(EventSubscriptionSource.subscription_id == subscription.id)
                    .order_by(col(EventSubscriptionSource.generation))
                    .with_for_update()
                )
            ).all()
            detachable = [await retirement.can_detach(item) for item in sources]
            if all(detachable):
                subscription.runtime_credential_id = None
        subscription.updated_by = self.user.id
        subscription.configuration_revision += 1
        # Keep source, credential references and terminal identity through retention.
        response = await self.response(subscription, source)
        await self.session.commit()
        return response

    async def response(
        self, subscription: EventSubscription, source: EventSubscriptionSource
    ) -> SubscriptionControlResponse:
        """Only acknowledgements from all registered participants establish convergence."""
        runtime_query = select(EventSubscriptionRuntime).where(EventSubscriptionRuntime.source_id == source.id)
        if source.generation == subscription.active_source_generation:
            runtime_query = (
                select(EventSubscriptionRuntime)
                .join(EventSubscriptionSource)
                .where(EventSubscriptionSource.subscription_id == subscription.id)
            )
        runtimes = list((await self.session.exec(runtime_query)).all())
        active = (
            subscription.desired_enabled
            and not subscription.paused
            and not subscription.retired
            and source.retired_at is None
        )
        applied = (
            (
                bool(runtimes)
                and all(
                    row.stopped
                    or (
                        row.source_id == source.id
                        and row.applied_revision == subscription.configuration_revision
                        and row.applied_published_version_id == subscription.published_version_id
                    )
                    for row in runtimes
                )
                and any(
                    not row.stopped
                    and row.source_id == source.id
                    and row.applied_revision == subscription.configuration_revision
                    and row.applied_published_version_id == subscription.published_version_id
                    for row in runtimes
                )
            )
            if active
            else all(row.stopped for row in runtimes)
        )
        return SubscriptionControlResponse(
            subscription_id=subscription.id,
            source_id=source.id,
            configuration_revision=subscription.configuration_revision,
            source_generation=source.generation,
            convergence="applied" if applied else "pending",
            applied_revision=subscription.configuration_revision if applied else None,
        )
