"""The transport-neutral consumer contract.

Every adapter implements :class:`EventConsumer`. The runtime only ever talks to
this interface, so hosting/lifecycle code (``consumer_service``,
``consumer_lifecycle``) is broker-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from syntara.eventstreams.core.envelope import Health


class EventConsumer(ABC):
    """A long-lived consumer that pushes normalized messages to a handler.

    Pull transports (Kafka, SQS, Service Bus) run an internal receive loop and
    call the injected handler; push transports (Event Grid webhook) call the same
    handler from an HTTP entrypoint. Either way ``start()`` blocks until
    ``stop()`` is requested, and acknowledgement happens only after the handler
    returns ``ACK``.
    """

    @abstractmethod
    async def start(self) -> None:
        """Connect and run until stopped. Returns when the loop drains cleanly."""

    @abstractmethod
    async def stop(self) -> None:
        """Request a graceful drain: finish the in-flight handoff, then leave."""

    @abstractmethod
    async def health(self) -> Health:
        """Return a liveness/readiness snapshot for health probes."""
