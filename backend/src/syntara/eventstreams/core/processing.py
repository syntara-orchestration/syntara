"""Unresolved processing results; never broker acknowledgement evidence."""

from datetime import datetime

from pydantic import Field

from syntara.eventstreams.core.deduplication import DeliveryIdentity, DeliveryValue
from syntara.eventstreams.core.results import EventDecodeFailure

CONTENT_INSPECTION_PENDING = "content_inspection_pending"
CONTENT_VALIDATED = "content_validated"


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
