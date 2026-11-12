"""Release unused sources without erasing resources for accepted workflows."""

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.adapters.kafka_initial_position import KafkaPartitionInitialPosition
from syntara.eventstreams.exceptions import EventSubscriptionControlConflictError
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.workflows.models.execution import Execution


class EventRetirementService:
    """Reuse lifecycle locks and placement leases without per-worker stop rows."""

    def __init__(self, session: AsyncSession) -> None:
        """Use the caller's lifecycle transaction without committing independently."""
        self.session = session

    async def release_empty_source(self, source: EventSubscriptionSource) -> None:
        """Release only never-started sources with no live assigned consumer.

        Lease expiry cannot prove that an accepted Temporal run has its normal
        Execution. Without a handoff ledger or scanner, retain initialized
        sources and their workflow/version resources rather than guess.
        """
        subscription = await self.session.get(EventSubscription, source.subscription_id)
        now = (await self.session.exec(select(func.clock_timestamp()))).one()
        if source.retired_at is None or (
            subscription is not None
            and subscription.assigned_worker_id is not None
            and subscription.assignment_lease_until is not None
            and subscription.assignment_lease_until > now
        ):
            msg = "source_consumer_drain_pending"
            raise EventSubscriptionControlConflictError(msg)
        positions = (
            await self.session.exec(
                select(KafkaPartitionInitialPosition).where(col(KafkaPartitionInitialPosition.source_id) == source.id)
            )
        ).all()
        retained_execution = (
            await self.session.exec(
                select(Execution.id)
                .where(
                    col(Execution.execution_metadata)["event"]["identity"]["source_id"].as_string() == str(source.id)
                )
                .limit(1)
            )
        ).first()
        if source.initialized_at is not None or positions or retained_execution is not None:
            msg = "source_handoff_safety_unproven"
            raise EventSubscriptionControlConflictError(msg)
        await self.session.delete(source)
