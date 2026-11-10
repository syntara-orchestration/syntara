"""Recovery claims are acquired just before use, without an expiring backlog."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.eventstreams.core.deduplication import ClaimLost, DeliveryClaim
from syntara.eventstreams.services import recovery_service as module
from syntara.eventstreams.services.admission_service import EventAdmissionService
from syntara.eventstreams.services.recovery_service import EventExecutionRecoveryService
from tests.unit.eventstreams.test_delivery_identity import identity
from tests.unit.eventstreams.test_delivery_retention import session_factory


async def test_next_recovery_claim_is_acquired_only_after_previous_finishes(monkeypatch: pytest.MonkeyPatch) -> None:
    factory, sessions = session_factory()
    events: list[str] = []
    claims = [
        DeliveryClaim(
            identity=identity(offset=offset),
            token=uuid4(),
            owner_worker_id="recovery",
            lease_until=datetime.now(UTC) + timedelta(seconds=60),
        )
        for offset in range(2)
    ]
    pending = iter(claims)

    async def claim_due(owner: str, *, limit: int, prepared_only: bool) -> list[DeliveryClaim]:
        assert owner == "recovery"
        assert limit == 1
        assert prepared_only
        if claim := next(pending, None):
            events.append(f"claim:{claim.identity.digest}")
            return [claim]
        return []

    async def recover(claim: DeliveryClaim) -> ClaimLost:
        sessions[-1].begin.return_value.__aexit__.assert_awaited_once_with(None, None, None)
        sessions[-1].__aexit__.assert_awaited_once_with(None, None, None)
        events.append(f"recover:{claim.identity.digest}")
        return ClaimLost()

    store = SimpleNamespace(claim_due=AsyncMock(side_effect=claim_due))
    admission = MagicMock(spec=EventAdmissionService, recover_claim=AsyncMock(side_effect=recover))
    monkeypatch.setattr(module, "EventDeliveryStore", lambda _session: store)

    results = await EventExecutionRecoveryService(factory, admission).recover_due("recovery", limit=10)

    assert [value for value, _ in results] == [claim.identity for claim in claims]
    assert events == [
        f"claim:{claims[0].identity.digest}",
        f"recover:{claims[0].identity.digest}",
        f"claim:{claims[1].identity.digest}",
        f"recover:{claims[1].identity.digest}",
    ]
    assert store.claim_due.await_count == 3


@pytest.mark.parametrize("limit", [0, -1, 101, True, 1.5])
async def test_recovery_preserves_batch_limit_validation(limit: int) -> None:
    factory, _ = session_factory()
    admission = MagicMock(spec=EventAdmissionService, recover_claim=AsyncMock())
    with pytest.raises(ValueError, match="batch size"):
        await EventExecutionRecoveryService(factory, admission).recover_due("recovery", limit=limit)
    factory.assert_not_called()
    admission.recover_claim.assert_not_awaited()
