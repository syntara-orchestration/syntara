"""Unresolved processing results; never broker acknowledgement evidence."""

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from pydantic import Field

from syntara.eventstreams.core.deduplication import DeliveryIdentity, DeliveryValue
from syntara.eventstreams.core.results import EventDecodeFailure

if TYPE_CHECKING:
    from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot

CONTENT_INSPECTION_PENDING = "content_inspection_pending"
CONTENT_VALIDATED = "content_validated"


class RecordProcessingGate(Protocol):
    """Shared reconciled lifecycle/dependency state, supplied by process composition.

    Reads must be local and bounded. Unknown/stale lifecycle or placement
    evidence closes admission. Known database outages, failed required durable
    writes, source uncertainty and recovery fences also close resolution.
    Placement expiry alone may leave resolution open for admitted handoffs.
    """

    def admission_open(self, snapshot: "SubscriptionSnapshot") -> bool:
        """Require current lifecycle/resources and a trusted, unexpired placement."""
        ...

    def resolution_open(self, snapshot: "SubscriptionSnapshot") -> bool:
        """Permit retained terminal evidence only while dependency/source state is trusted."""
        ...

    def dependency_failed(self, snapshot: "SubscriptionSnapshot") -> None:
        """Invalidate shared dependency/lifecycle trust until authoritative reconciliation.

        This also closes a known administrative recovery hold; it does not
        diagnose a database outage or revoke already frozen delivery claims.
        """
        ...


class RecordRunnerControl(Protocol):
    """Local placement-loss control; owns no lease storage or placement policy."""

    async def close_admission(self) -> None:
        """Pause fetching and bound drain, preserving frozen durable handoffs."""
        ...


class InspectedRecord(DeliveryValue):
    """Content validation completed; no workflow or broker resolution is implied."""

    identity: DeliveryIdentity


class PendingContentFailure(DeliveryValue):
    """Bounded identity and optional proven failure for unbufferable content."""

    identity: DeliveryIdentity
    failure: EventDecodeFailure | None = None
    validated: bool = False


class HeldRecord(DeliveryValue):
    """Keep a record blocked or retry at a bounded dependency-probe time."""

    reason: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    retry_at: datetime | None = None
    permanent_content_error: bool = False
