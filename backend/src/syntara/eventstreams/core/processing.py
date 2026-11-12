"""Unresolved processing results; never broker acknowledgement evidence."""

from datetime import datetime
from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import Field

from syntara.eventstreams.core.deduplication import DeliveryIdentity, DeliveryValue
from syntara.eventstreams.core.results import EventDecodeFailure
from syntara.filtering.models.result import FilterErrorCode

if TYPE_CHECKING:
    from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot


class RecordProcessingGate(Protocol):
    """Shared reconciled lifecycle/dependency state, supplied by process composition.

    Reads must be local and bounded. Unknown/stale lifecycle or placement
    evidence closes admission. Known database outages, failed required durable
    writes, source uncertainty and recovery fences also close resolution.
    Closing admission or placement expiry may leave resolution open for completed
    records, including local CEL skips, and already admitted durable handoffs.
    """

    def transport_open(self, snapshot: "SubscriptionSnapshot") -> bool:
        """Permit the owned transport to repair positions while intake is fenced."""
        ...

    def admission_open(self, snapshot: "SubscriptionSnapshot") -> bool:
        """Require current lifecycle/resources and a trusted, unexpired placement."""
        ...

    def resolution_open(self, snapshot: "SubscriptionSnapshot") -> bool:
        """Permit completed records only while dependency/source state is trusted."""
        ...

    def dependency_failed(self, snapshot: "SubscriptionSnapshot") -> None:
        """Invalidate shared dependency/lifecycle trust until authoritative reconciliation.

        Neither callback cancels already accepted workflows. Partition recovery
        is fenced locally by its runner and persisted position token.
        """
        ...

    def source_failed(self, snapshot: "SubscriptionSnapshot") -> None:
        """Fence an uncertain source without invalidating shared database trust."""
        ...

    def source_verified(self, snapshot: "SubscriptionSnapshot") -> None:
        """Reopen a source after a successful current Kafka identity check."""
        ...


class RecordRunnerControl(Protocol):
    """Local placement-loss control; owns no lease storage or placement policy."""

    async def close_admission(self) -> None:
        """Pause fetching and bound drain, preserving accepted handoffs."""
        ...


class InspectedRecord(DeliveryValue):
    """Content validation completed; no workflow or broker resolution is implied."""

    identity: DeliveryIdentity


class SkippedRecord(DeliveryValue):
    """Local CEL completion, never a durable delivery proof or cacheable outcome."""

    identity: DeliveryIdentity
    configuration_revision: int
    outcome: Literal["no_match", "evaluation_error"]
    error_code: FilterErrorCode | None = None


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
