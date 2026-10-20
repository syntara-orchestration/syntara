"""Bounded prepared-delivery recovery independent of active consumers."""

from collections.abc import Callable

from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.core.deduplication import DeliveryIdentity
from syntara.eventstreams.services.admission_service import EventAdmissionService, SchedulingResult
from syntara.eventstreams.services.deduplication_store import EventDeliveryStore


class EventExecutionRecoveryService:
    """Finite operations for processing callers and lifecycle/retry controllers."""

    def __init__(self, session_factory: Callable[..., AsyncSession], admission: EventAdmissionService) -> None:
        """Inject the same factory and scheduling service used by processing callers."""
        self._session_factory = session_factory
        self._admission = admission

    async def recover_due(self, owner_worker_id: str, *, limit: int) -> list[tuple[DeliveryIdentity, SchedulingResult]]:
        """Commit at most 100 claims, then recover serially without Kafka ownership."""
        async with self._session_factory() as session, session.begin():
            claims = await EventDeliveryStore(session).claim_due(owner_worker_id, limit=limit, prepared_only=True)
        return [(claim.identity, await self._admission.recover_claim(claim)) for claim in claims]

    async def request_retry(self, identity: DeliveryIdentity) -> bool:
        """Wake recovery after a caller-authorized correction; no new start permission."""
        async with self._session_factory() as session, session.begin():
            changed = await EventDeliveryStore(session).request_scheduling_retry(identity)
        return changed  # noqa: RET504 - success is reported only after commit
