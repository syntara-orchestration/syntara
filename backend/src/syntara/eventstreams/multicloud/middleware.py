"""Observability middleware — logic HOLDS, registration DUPLICATES.

``BaseMiddleware.consume_scope`` wraps every message on the broker it is registered
on. The middleware *logic* (time the handoff, count it, log outcome) is genuinely
transport-neutral and written once here.

The friction is registration: a middleware instance is attached to a specific broker
(``KafkaBroker(middlewares=[...])`` etc.), so it must be added to each of the three
brokers separately (see ``app.py``). And because ``msg.raw_message`` shape differs
per transport, any middleware that wants transport-specific fields (offset, receipt
handle, sequence number) immediately stops being neutral.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog
from faststream import BaseMiddleware

from syntara.eventstreams.metrics import HANDOFF_LATENCY, MESSAGES_HANDLED, MESSAGES_RECEIVED

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = structlog.stdlib.get_logger(__name__)


class ObservabilityMiddleware(BaseMiddleware):
    """Times, counts, and logs each consumed message.

    Reuses the same Prometheus metrics as the single-broker POC. The ``broker_type``
    label is supplied at construction because the middleware itself cannot tell which
    transport it is bound to — a small but telling sign that "which cloud am I?" is
    not something FastStream threads through neutrally.
    """

    # NOTE: broker_type is captured via a factory (see for_transport) because
    # FastStream instantiates the middleware per-message with a fixed signature.
    broker_type: str = "unknown"

    async def consume_scope(
        self,
        call_next: Callable[[Any], Awaitable[Any]],
        msg: Any,
    ) -> Any:
        """Wrap one message: count received, time the handoff, record the outcome."""
        MESSAGES_RECEIVED.labels(broker_type=self.broker_type, source=self.broker_type).inc()
        started = time.monotonic()
        outcome = "ack_triggered"
        try:
            return await call_next(msg)
        except Exception:
            outcome = "error"
            raise
        finally:
            HANDOFF_LATENCY.labels(broker_type=self.broker_type, source=self.broker_type).observe(
                time.monotonic() - started,
            )
            MESSAGES_HANDLED.labels(broker_type=self.broker_type, source=self.broker_type, outcome=outcome).inc()


def observability_for(broker_type: str) -> type[ObservabilityMiddleware]:
    """Build a middleware subclass bound to a transport label.

    # DUPLICACY RISK [BROKER-SPECIFIC]: we need one middleware *class* per transport
    # only so the metric label can differ. In our own wrapper the broker_type flowed
    # through a neutral envelope, so a single middleware sufficed. FastStream's
    # middleware has no neutral "which transport" context, forcing this per-broker
    # subclass factory.
    """
    return type(
        f"ObservabilityMiddleware_{broker_type}",
        (ObservabilityMiddleware,),
        {"broker_type": broker_type},
    )
