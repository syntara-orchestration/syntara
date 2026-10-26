"""Persisted administrative requests dispatched by the assigned consumer."""

from collections.abc import Callable

from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.adapters.kafka_initial_position import (
    PositionResult,
    PositionStatus,
    RecoveryPolicy,
    RecoveryRequest,
)
from syntara.eventstreams.models.control import EventSubscriptionRecovery
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.subscription_service import lock_source_lifecycle


class EventRecoveryRequestService:
    """The database carries authority; Redis and local observations never supply it."""

    def __init__(self, session_factory: Callable[..., AsyncSession]) -> None:
        """Inject fresh short sessions independent of broker operations."""
        self._sessions = session_factory

    async def read(self, snapshot: SubscriptionSnapshot, partition: int, epoch: int) -> RecoveryRequest | None:
        """Load a detached request; assignment epoch is supplied only by the runner."""
        async with self._sessions() as session:
            row = await session.get(EventSubscriptionRecovery, (snapshot.source_id, partition))
            if row is None or row.completed or row.configuration_revision != snapshot.configuration_revision:
                return None
            return RecoveryRequest(
                source_id=snapshot.source_id,
                source_generation=snapshot.source_generation,
                configuration_revision=row.configuration_revision,
                partition=partition,
                assignment_epoch=epoch,
                expected_recovery_revision=row.expected_recovery_revision,
                policy=RecoveryPolicy(row.policy),
                reason=row.reason,
                acknowledge_duplicate_risk=row.acknowledge_duplicate_risk,
                allow_unscheduled_disposition=row.resolve_unscheduled,
            )

    async def record(self, request: RecoveryRequest, result: PositionResult) -> None:
        """Commit only the result of this exact authorized request; failures retain holds."""
        async with self._sessions() as session, session.begin():
            lifecycle = await lock_source_lifecycle(session, request.source_id)
            if lifecycle is None or lifecycle[0].configuration_revision != request.configuration_revision:
                return
            row = await session.get(
                EventSubscriptionRecovery, (request.source_id, request.partition), with_for_update=True
            )
            if row is None or not row.matches_request(request):
                return
            row.completed = result.status == PositionStatus.READY
            row.error_code = result.reason
