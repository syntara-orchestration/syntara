"""Bounded prepared-delivery recovery independent of active consumers."""

from collections.abc import Callable

from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.constants import FieldLimits
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
        """Recover at most 100 deliveries, claiming each only when ready to use it."""
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= FieldLimits.MAX_ITEMS_PER_PAGE:
            msg = "Recovery batch size must be between 1 and 100"
            raise ValueError(msg)
        results: list[tuple[DeliveryIdentity, SchedulingResult]] = []
        for _ in range(limit):
            async with self._session_factory() as session, session.begin():
                claims = await EventDeliveryStore(session).claim_due(owner_worker_id, limit=1, prepared_only=True)
            if not claims:
                break
            claim = claims[0]
            results.append((claim.identity, await self._admission.recover_claim(claim)))
        return results

    async def request_retry(self, identity: DeliveryIdentity) -> bool:
        """Wake recovery after a caller-authorized correction; no new start permission."""
        async with self._session_factory() as session, session.begin():
            changed = await EventDeliveryStore(session).request_scheduling_retry(identity)
        return changed  # noqa: RET504 - success is reported only after commit
