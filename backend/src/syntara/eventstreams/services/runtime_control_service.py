"""Short transactions for cross-process consumer registration and acknowledgement."""

from collections.abc import Callable

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.core.runtime import RuntimeState, SubscriptionRuntimeStatus
from syntara.eventstreams.models.control import EventSubscriptionRuntime
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.subscription_service import lock_source_lifecycle
from syntara.workflows.models.workflow import Workflow


class EventRuntimeControlService:
    """Never infer shutdown from elapsed time, lease expiry, or missing workers."""

    def __init__(self, session_factory: Callable[..., AsyncSession], worker_id: str) -> None:
        """Use the same process identity as the consumer clients."""
        self._sessions = session_factory
        self._worker = worker_id

    async def register(self, snapshot: SubscriptionSnapshot) -> bool:
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
                or not workflow.is_enabled
                or workflow.published_version_id != snapshot.published_version_id
            ):
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
            key = (source.id, self._worker)
            row = await session.get(EventSubscriptionRuntime, key)
            if row is None:
                row = EventSubscriptionRuntime(
                    source_id=source.id,
                    worker_id=self._worker,
                    configuration_revision=snapshot.configuration_revision,
                )
                session.add(row)
            row.configuration_revision = snapshot.configuration_revision
            row.applied_revision = None
            row.applied_published_version_id = None
            row.stopped = False
        return True

    async def acknowledge(self, snapshot: SubscriptionSnapshot, status: SubscriptionRuntimeStatus) -> None:
        """Retain participation and content gates after failed or partial stops."""
        async with self._sessions() as session, session.begin():
            if await lock_source_lifecycle(session, snapshot.source_id) is None:
                return
            row = await session.get(EventSubscriptionRuntime, (snapshot.source_id, self._worker), with_for_update=True)
            if row is None or row.configuration_revision != snapshot.configuration_revision:
                return
            row.stopped = status.state == RuntimeState.STOPPED
            row.permanent_content_error = row.permanent_content_error or status.permanent_content_error
            row.applied_revision = (
                status.applied_revision.configuration_revision
                if status.applied_revision is not None and status.applied_revision.source_id == snapshot.source_id
                else None
            )
            row.applied_published_version_id = (
                status.applied_revision.published_version_id
                if status.applied_revision is not None and status.applied_revision.source_id == snapshot.source_id
                else None
            )
