"""The transport-neutral handling pipeline.

``DispatchingEventHandler`` is the single place the delivery guarantee lives, and
it is broker-free — it can be unit-tested with a fake handler and no broker
(ADR-0001 §3.2). For each message it runs:

    deserialize -> filter -> dispatch (handler / workflow handoff) -> classify

and returns ``ACK`` or ``RETRY`` per the guarantee:

- content problems (undecodable payload, no filter match, unknown event type,
  or a ``PermanentHandlerError``) are *decisions* -> ``ACK`` (offset advances, so
  a poison message can never block a partition; there is no DLQ);
- only a ``TransientHandlerError`` (or a configured transient exception) withholds
  the commit -> ``RETRY`` -> redelivery + natural back-pressure.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog

from syntara.eventstreams.core.envelope import HandlerResult
from syntara.eventstreams.core.exceptions import (
    PermanentHandlerError,
    TransientHandlerError,
)
from syntara.eventstreams.core.filter import AllowAllFilter
from syntara.eventstreams.core.metrics import (
    HANDOFF_LATENCY,
    MESSAGES_HANDLED,
    REDELIVERIES,
)
from syntara.eventstreams.core.serialization import (
    DeserializationError,
    JsonDeserializer,
)

if TYPE_CHECKING:
    from syntara.eventstreams.core.envelope import EventEnvelope
    from syntara.eventstreams.core.filter import MessageFilter
    from syntara.eventstreams.core.registry import HandlerRegistry
    from syntara.eventstreams.core.serialization import Deserializer

logger = structlog.stdlib.get_logger(__name__)

# Exceptions that always mean "transient infra failure -> redeliver".
_TRANSIENT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    TransientHandlerError,
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
)


class DispatchingEventHandler:
    """Deserialize, filter, and dispatch a message, returning an ACK/RETRY decision.

    Args:
        registry: event_type -> handler map.
        deserializer: payload decoder (defaults to JSON).
        message_filter: trigger gate (defaults to allow-all).
        broker_type: label for metrics only.
        handler_timeout_seconds: per-message timeout; a timeout is transient (RETRY).

    """

    def __init__(
        self,
        registry: HandlerRegistry,
        *,
        deserializer: Deserializer | None = None,
        message_filter: MessageFilter | None = None,
        broker_type: str = "kafka",
        handler_timeout_seconds: float = 300.0,
    ) -> None:
        """Wire the registry, deserializer, filter, and per-message timeout."""
        self._registry = registry
        self._deserializer = deserializer or JsonDeserializer()
        self._filter = message_filter or AllowAllFilter()
        self._broker_type = broker_type
        self._timeout = handler_timeout_seconds

    async def handle(self, envelope: EventEnvelope) -> HandlerResult:  # noqa: PLR0911
        """Run deserialize -> filter -> dispatch and return an ACK/RETRY decision."""
        source = envelope.source
        started = time.monotonic()

        # 1. Deserialize. An undecodable payload is a no-trigger decision, not a failure.
        try:
            payload = self._deserializer.deserialize(envelope)
        except DeserializationError as exc:
            logger.warning(
                "eventstream_deserialize_failed",
                message_id=envelope.message_id,
                source=source,
                error=str(exc),
            )
            return self._decision(source, "ack_no_trigger")

        # 2. Filter. No match -> no-trigger decision.
        if not self._filter.matches(envelope, payload):
            logger.debug("eventstream_filtered_out", message_id=envelope.message_id, source=source)
            return self._decision(source, "ack_no_trigger")

        # 3. Dispatch by event_type. Unknown type with no default -> no-trigger decision.
        handler = self._registry.resolve(envelope.event_type)
        if handler is None:
            logger.warning(
                "eventstream_no_handler",
                message_id=envelope.message_id,
                source=source,
                event_type=envelope.event_type,
            )
            return self._decision(source, "ack_no_trigger")

        # 4. Handoff. Only a transient failure withholds the commit.
        try:
            await asyncio.wait_for(handler(envelope, payload), timeout=self._timeout)
        except _TRANSIENT_EXCEPTIONS as exc:
            logger.warning(
                "eventstream_handoff_transient_failure",
                message_id=envelope.message_id,
                source=source,
                error=str(exc),
            )
            REDELIVERIES.labels(broker_type=self._broker_type, source=source).inc()
            return self._decision(source, "retry")
        except PermanentHandlerError as exc:
            # Non-retriable: ACK anyway so the partition is never blocked (no DLQ).
            # Deliberately logged without a stacktrace — the cause is in the message,
            # not a code path worth a traceback.
            logger.error(  # noqa: TRY400
                "eventstream_handoff_permanent_failure",
                message_id=envelope.message_id,
                source=source,
                error=str(exc),
            )
            return self._decision(source, "error")
        except Exception:
            # Unexpected/unclassified error: treat as permanent to avoid a crash-loop.
            logger.exception(
                "eventstream_handoff_unexpected_error",
                message_id=envelope.message_id,
                source=source,
            )
            return self._decision(source, "error")
        finally:
            HANDOFF_LATENCY.labels(broker_type=self._broker_type, source=source).observe(
                time.monotonic() - started,
            )

        return self._decision(source, "ack_triggered")

    def _decision(self, source: str, outcome: str) -> HandlerResult:
        MESSAGES_HANDLED.labels(broker_type=self._broker_type, source=source, outcome=outcome).inc()
        return HandlerResult.RETRY if outcome == "retry" else HandlerResult.ACK
