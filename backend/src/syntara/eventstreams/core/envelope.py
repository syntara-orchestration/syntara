"""Transport-neutral message model and handler result types.

Every broker adapter (Kafka today; AWS SNS/SQS/EventBridge and Azure Service
Bus/Event Grid in future) normalizes its native message into an
:class:`EventEnvelope` and drives the shared handler pipeline. Handlers never
see a native message, so the same filter + Temporal-handoff logic runs unchanged
across all transports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime


class HandlerResult(Enum):
    """Outcome of handling a single message.

    The consumer runtime maps this onto each transport's acknowledgement
    mechanism (Kafka offset commit, SQS delete, Service Bus ``complete()``,
    webhook HTTP status):

    - ``ACK``   -> the message is fully handled (a workflow was triggered, or a
      deliberate no-trigger decision was made). Acknowledge / commit.
    - ``RETRY`` -> a *transient* infrastructure failure occurred before handoff
      completed. Do NOT acknowledge, so the broker redelivers. This is also the
      natural back-pressure signal.
    """

    ACK = "ack"
    RETRY = "retry"


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """A single inbound message, normalized across all transports.

    ``body`` is kept as raw bytes; deserialization is a separate, explicit step
    (an unparseable payload is a filter *decision*, not a transport error).
    ``raw`` is a sanctioned escape hatch to the native message for the rare case
    an adapter-specific field is needed.
    """

    message_id: str
    """Stable identity used to derive the deterministic workflow id for dedup."""
    source: str
    """Topic / queue / subscription the message arrived on."""
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)
    key: str | None = None
    partition_key: str | None = None
    event_type: str | None = None
    content_type: str | None = None
    subject: str | None = None
    delivery_attempt: int = 1
    enqueued_at: datetime | None = None
    raw: Any = None


@dataclass(frozen=True, slots=True)
class Health:
    """Liveness/readiness snapshot for a consumer, surfaced to health probes."""

    healthy: bool
    detail: str = ""
    assigned_partitions: int = 0
