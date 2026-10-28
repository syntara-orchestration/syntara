"""Approved retained-count hysteresis and capacity-check failure behavior."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.constants import EventDeliveryDefaults
from syntara.eventstreams.services.delivery_capacity_service import PostgreSQLDeliveryCapacityCheck, capacity_paused


@pytest.mark.parametrize(
    ("count", "previously_paused", "expected"),
    [
        (2_999_999, False, False),
        (3_000_000, False, True),
        (3_000_001, False, True),
        (2_500_000, True, True),
        (2_499_999, True, False),
        (2_750_000, True, True),
        (2_750_000, False, False),
    ],
)
def test_approved_hysteresis(count: int, *, previously_paused: bool, expected: bool) -> None:
    """An existing pause persists until count falls strictly below 2.5 million."""
    assert capacity_paused(retained_count=count, previously_paused=previously_paused) is expected


def test_capacity_and_retention_are_independent() -> None:
    """Storage pressure thresholds never shorten lease or evidence lifetimes."""
    assert EventDeliveryDefaults.CAPACITY_PAUSE_ROWS == 3_000_000
    assert EventDeliveryDefaults.CAPACITY_RESUME_ROWS == 2_500_000
    assert EventDeliveryDefaults.CLAIM_LEASE_SECONDS == 60
    assert EventDeliveryDefaults.CLAIM_RENEWAL_INTERVAL_SECONDS == 20
    assert EventDeliveryDefaults.RETENTION_SECONDS == 3600


async def test_unavailable_count_measurement_fails_closed() -> None:
    """A failed measurement cannot reuse an assumed unlimited capacity grant."""
    session = MagicMock(spec=AsyncSession)
    session.begin_nested.side_effect = OperationalError("capacity check", {}, OSError())
    assert not await PostgreSQLDeliveryCapacityCheck(session).permits_new_delivery()


def test_negative_count_is_not_capacity_evidence() -> None:
    """Invalid measurements cannot accidentally reopen admission."""
    with pytest.raises(ValueError, match="negative"):
        capacity_paused(retained_count=-1, previously_paused=True)
