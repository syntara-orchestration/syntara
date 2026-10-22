"""Authoritative desired-state snapshots for a standalone worker."""

from collections.abc import Callable

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.workflows.models.workflow import Workflow


class EventSubscriptionReader:
    """Open a fresh read session per reconciliation, independent of request DI."""

    def __init__(self, session_factory: Callable[..., AsyncSession]) -> None:
        """Inject the process or isolated test session factory."""
        self._session_factory = session_factory

    async def read(self) -> list[SubscriptionSnapshot]:
        """Read active bindings consistently without resolving customer connections."""
        statement = (
            select(EventSubscription, EventSubscriptionSource)
            .join(
                EventSubscriptionSource,
                (col(EventSubscriptionSource.subscription_id) == EventSubscription.id)
                & (col(EventSubscriptionSource.generation) == EventSubscription.active_source_generation),
            )
            .join(Workflow, col(Workflow.id) == EventSubscription.workflow_id)
            .where(
                col(EventSubscription.desired_enabled).is_(True),
                col(EventSubscription.paused).is_(False),
                col(EventSubscription.retired).is_(False),
                col(EventSubscriptionSource.retired_at).is_(None),
                col(Workflow.is_enabled).is_(True),
                col(Workflow.published_version_id) == EventSubscription.published_version_id,
            )
            .order_by(col(EventSubscription.id))
        )
        async with self._session_factory() as session:
            rows = (await session.exec(statement)).all()
            snapshots = [SubscriptionSnapshot.from_models(subscription, source) for subscription, source in rows]
        return snapshots  # noqa: RET504 - close the read session before dependency construction
