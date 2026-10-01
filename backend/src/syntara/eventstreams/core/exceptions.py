"""Exception taxonomy for the event-stream consumer runtime.

The pipeline uses these to decide between ACK and RETRY (see
:mod:`syntara.eventstreams.core.pipeline`). The rule mirrors the delivery
guarantee in ADR-0001 §5: only *transient* infrastructure failures withhold the
commit; everything else is a decision that still advances the offset so a poison
message can never block a partition (there is no DLQ).
"""

from __future__ import annotations


class EventStreamError(Exception):
    """Base class for all event-stream errors."""


class ConsumerConnectionError(EventStreamError):
    """Raised when a consumer cannot connect to / authenticate with a broker."""


class TransientHandlerError(EventStreamError):
    """A transient failure before handoff completed (e.g. Temporal unreachable).

    Signals the runtime to withhold acknowledgement -> the broker redelivers.
    """


class PermanentHandlerError(EventStreamError):
    """A non-retriable failure (bad payload, bug).

    The runtime acknowledges anyway (logged + counted) so the partition is never
    blocked. There is no DLQ by design; Temporal owns durable retries downstream.
    """


class UnsupportedBrokerError(EventStreamError):
    """Raised by the adapter factory for a broker type without an adapter yet."""
