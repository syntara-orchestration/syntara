"""Short transactions for cross-process consumer registration and acknowledgement."""

from collections.abc import Callable

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.core.placement import SubscriptionPlacementLease, WorkerIdentity
from syntara.eventstreams.core.runtime import RuntimeRevision, RuntimeState, SubscriptionRuntimeStatus
from syntara.eventstreams.models.control import EventSubscriptionRuntime
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.runtime_placement import confirmed_placements
from syntara.eventstreams.services.subscription_service import lock_source_lifecycle
from syntara.workflows.models.workflow import Workflow


class EventRuntimeControlService:
    """Never infer shutdown from elapsed time, lease expiry, or missing workers."""

    def __init__(self, session_factory: Callable[..., AsyncSession], worker: WorkerIdentity) -> None:
        """Use the same process identity as the consumer clients."""
        self._sessions = session_factory
        self._worker = worker

    async def register(self, snapshot: SubscriptionSnapshot, lease: SubscriptionPlacementLease) -> bool:
        """Register under lifecycle locks before a consumer can be constructed."""
        async with self._sessions() as session, session.begin():
            lifecycle = await lock_source_lifecycle(session, snapshot.source_id)
            if lifecycle is None:
                return False
            subscription, source = lifecycle
            workflow = await session.get(Workflow, subscription.workflow_id)
            if (
                SubscriptionSnapshot.from_models(subscription, source) != snapshot
                or not subscription.desired_enabled
                or subscription.paused
                or subscription.retired
                or source.retired_at is not None
                or subscription.active_source_generation != source.generation
                or workflow is None
                or workflow.project_id != subscription.project_id
                or not workflow.is_enabled
                or workflow.published_version_id != snapshot.published_version_id
            ):
                return False
            current = (await confirmed_placements(session, [(subscription, source)])).get(subscription.id)
            if not self._matches_lease(current, lease):
                return False
            content_gate = (
                await session.exec(
                    select(EventSubscriptionRuntime.worker_id)
                    .where(
                        EventSubscriptionRuntime.source_id == source.id,
                        col(EventSubscriptionRuntime.permanent_content_error).is_(True),
                    )
                    .limit(1)
                )
            ).first()
            if content_gate is not None:
                return False
            key = (source.id, str(self._worker.worker_id))
            row = await session.get(EventSubscriptionRuntime, key)
            if row is None:
                row = EventSubscriptionRuntime(
                    source_id=source.id,
                    worker_id=str(self._worker.worker_id),
                    configuration_revision=snapshot.configuration_revision,
                )
                session.add(row)
            row.configuration_revision = snapshot.configuration_revision
            row.applied_revision = None
            row.applied_published_version_id = None
            row.stopped = False
            row.runtime_state = RuntimeState.STARTING.value
        return True

    def _matches_lease(
        self, current: SubscriptionPlacementLease | None, lease: SubscriptionPlacementLease | None
    ) -> bool:
        return (
            current is not None
            and lease is not None
            and current.owner == self._worker
            and lease.owner == self._worker
            and lease.subscription_id == current.subscription_id
            and lease.expires_at == current.expires_at
            and lease.expires_at > current.confirmed_at
        )

    async def acknowledge(
        self,
        snapshot: SubscriptionSnapshot,
        status: SubscriptionRuntimeStatus,
        *,
        lease: SubscriptionPlacementLease | None = None,
    ) -> None:
        """Retain participation and content gates after failed or partial stops."""
        async with self._sessions() as session, session.begin():
            lifecycle = await lock_source_lifecycle(session, snapshot.source_id)
            if lifecycle is None or status.subscription_id != snapshot.subscription_id:
                return
            subscription, source = lifecycle
            row = await session.get(
                EventSubscriptionRuntime, (snapshot.source_id, str(self._worker.worker_id)), with_for_update=True
            )
            if row is None:
                return
            row.permanent_content_error = row.permanent_content_error or status.permanent_content_error
            if row.configuration_revision != snapshot.configuration_revision:
                return
            if status.state == RuntimeState.STOPPED:
                row.stopped = True
                row.runtime_state = RuntimeState.STOPPED.value
                row.applied_revision = row.applied_published_version_id = None
                return
            current = (await confirmed_placements(session, [(subscription, source)])).get(subscription.id)
            workflow = await session.get(Workflow, subscription.workflow_id)
            expected = RuntimeRevision.from_snapshot(snapshot)
            if (
                not self._matches_lease(current, lease)
                or SubscriptionSnapshot.from_models(subscription, source) != snapshot
                or status.desired_revision != expected
                or not status.desired_active
                or workflow is None
                or not workflow.is_enabled
                or workflow.project_id != subscription.project_id
                or workflow.published_version_id != snapshot.published_version_id
            ):
                return
            row.stopped = False
            row.runtime_state = status.state.value
            applied = status.applied_revision == expected
            row.applied_revision = snapshot.configuration_revision if applied else None
            row.applied_published_version_id = snapshot.published_version_id if applied else None
