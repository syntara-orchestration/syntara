"""Handler and workflow-launcher protocols.

``EventHandler`` is what the consumer runtime drives per message. ``WorkflowLauncher``
is the seam to Temporal: the pipeline hands off to it and treats its success as
the point at which the message may be acknowledged (ADR-0001 §5 invariant 1).
Keeping it a Protocol lets tests inject a fake (no broker, no Temporal) and lets
the real launcher wrap ``TemporalExecutionService`` without a hard import here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from syntara.eventstreams.core.envelope import EventEnvelope, HandlerResult


@runtime_checkable
class EventHandler(Protocol):
    """Handles one normalized message and returns an ACK/RETRY decision.

    Implementations MUST NOT raise for content problems — they classify them and
    return ``ACK``. Only genuinely transient failures should surface as ``RETRY``.
    """

    async def handle(self, envelope: EventEnvelope) -> HandlerResult:
        """Handle one message and return its ACK/RETRY decision."""
        ...


@runtime_checkable
class WorkflowLauncher(Protocol):
    """Idempotently starts a workflow for a message (the Temporal handoff).

    The implementation derives a deterministic workflow id from
    ``envelope.message_id`` so at-least-once redeliveries dedup natively in
    Temporal, replacing any in-house dedup store (ADR-0001 §5 invariant 2).

    Raises:
        TransientHandlerError: the launch failed transiently (broker/Temporal
            unreachable) and the message should be redelivered.

    """

    async def launch(self, envelope: EventEnvelope, payload: object) -> str | None:
        """Start (or dedup) the workflow for a message; return its workflow id."""
        ...
