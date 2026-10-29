"""Read confirmed placement for control observations, never infer quiescence."""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.core.placement import SubscriptionPlacementLease, WorkerIdentity
from syntara.eventstreams.models.consumer_worker import EventConsumerWorker
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription


async def confirmed_placements(
    session: AsyncSession, bindings: Iterable[tuple[EventSubscription, EventSubscriptionSource]]
) -> dict[UUID, SubscriptionPlacementLease]:
    """Use database time and membership without changing leases or user metadata.

    Callers performing lifecycle writes already hold workflow/subscription/source
    locks. Membership is read without a row lock to retain the placement service's
    membership-before-lifecycle lock order. Expiry only denies active authority.
    """
    bindings = list(bindings)
    owners = {subscription.assigned_worker_id for subscription, _ in bindings} - {None}
    if not owners:
        return {}
    rows = (
        await session.exec(
            select(EventConsumerWorker, func.clock_timestamp()).where(col(EventConsumerWorker.worker_id).in_(owners))
        )
    ).all()
    members = {member.worker_id: (member, now) for member, now in rows}
    placements = {}
    for subscription, source in bindings:
        owner = subscription.assigned_worker_id
        if owner is None:
            continue
        observed = members.get(owner)
        if observed is None:
            continue
        member, now = observed
        expiry = subscription.assignment_lease_until
        if (
            expiry is None
            or expiry <= now
            or member.heartbeat_until <= now
            or member.draining
            or member.deployment_id != source.deployment_id
            or source.subscription_id != subscription.id
            or source.generation != subscription.active_source_generation
            or source.retired_at is not None
            or subscription.retired
            or subscription.paused
            or not subscription.desired_enabled
        ):
            continue
        placements[subscription.id] = SubscriptionPlacementLease(
            subscription_id=subscription.id,
            owner=WorkerIdentity(deployment_id=member.deployment_id, worker_id=member.worker_id),
            confirmed_at=now,
            expires_at=expiry,
        )
    return placements
