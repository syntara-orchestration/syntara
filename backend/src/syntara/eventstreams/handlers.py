"""Temporal-handoff stub + native ``event_type`` dispatch.

This replaces the AO wrapper's ``core.registry.HandlerRegistry`` +
``core.handler.WorkflowLauncher`` protocols + ``handlers.registry`` wiring with a
plain module-level dispatch table. It is deliberately minimal — the point of the
native POC is that dispatch is a small in-process concern folded next to the
broker callback, not a transport-neutral subsystem.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

import structlog

logger = structlog.stdlib.get_logger(__name__)


class TransientHandoffError(Exception):
    """A transient failure before handoff completed (e.g. Temporal unreachable).

    Raised by a handler to signal the broker callback to withhold the commit and
    let the message be redelivered (at-least-once + back-pressure).
    """


class PermanentHandoffError(Exception):
    """A non-retriable failure (bad payload, bug).

    The callback ACKs anyway (logged + counted) so a poison message never blocks a
    partition. There is no DLQ by design; Temporal owns durable retries downstream.
    """


# A handler processes one decoded message. Raise TransientHandoffError to force
# redelivery; any other exception is treated as permanent (ACK) by the callback.
MessageHandler = Callable[..., Awaitable[None]]


async def _launch_workflow_stub(
    payload: object,  # noqa: ARG001 — stub: real launcher passes this to Temporal
    *,
    message_id: str,
    source: str,
    event_type: str | None,
    headers: Mapping[str, str],  # noqa: ARG001
) -> None:
    """No-op Temporal handoff: logs instead of starting a workflow.

    Lets the consumer run end-to-end (receive -> filter -> "handoff" -> commit)
    without the execution service wired in.

    # FUTURE EDA RISK: the real launcher must derive a DETERMINISTIC workflow id from
    # ``message_id`` so at-least-once redeliveries dedup natively in Temporal. Today
    # ``message_id`` is built from Kafka coordinates (topic-partition-offset) in
    # app.py. A second transport has different coordinates (SQS receipt handle,
    # Service Bus sequence number), so the identity scheme — and therefore the dedup
    # guarantee — does not carry over and must be redesigned per broker.
    #
    # FUTURE EDA RISK (fan-out): if one message must trigger N workflows, this handler
    # must launch all N and the callback must commit the single offset only AFTER all
    # N succeed. FastStream's idiomatic fan-out (N subscribers on one topic) gives
    # each subscriber its OWN offset/ack, which fragments that single-commit
    # guarantee — so fan-out cannot use native routing and must be hand-rolled here.
    """
    logger.info(
        "eventstream_workflow_launch_stub",
        message_id=message_id,
        source=source,
        event_type=event_type,
    )


# event_type -> handler. Empty for the POC: every message falls through to the
# default handler (ANSTRAT-1934 will add typed routing later).
#
# FUTURE EDA RISK: this table is consulted inline inside the Kafka callback in
# app.py. In the AO wrapper the same routing lived in a broker-neutral
# ``DispatchingEventHandler`` that every transport shared. Here, a second transport's
# callback would have to re-implement the same "resolve by event_type, fall back to
# default" logic — either by importing this and duplicating the lookup, or by
# reintroducing the shared dispatcher the POC removed.
HANDLERS: dict[str, MessageHandler] = {}

DEFAULT_HANDLER: MessageHandler = _launch_workflow_stub


def resolve_handler(event_type: str | None) -> MessageHandler | None:
    """Return the handler for ``event_type``, falling back to the default."""
    if event_type is not None and event_type in HANDLERS:
        return HANDLERS[event_type]
    return DEFAULT_HANDLER
