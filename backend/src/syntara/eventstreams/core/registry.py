"""Data-driven dispatch: event_type -> handler.

Mirrors the Temporal ``ACTIVITY_REGISTRY`` philosophy — one generic consumer
routes by a message attribute through a registry, instead of hand-wiring each
message type. A per-message handler receives the envelope and decoded payload and
performs the side effect (e.g. launching a workflow).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from syntara.eventstreams.core.envelope import EventEnvelope

MessageHandlerFn = Callable[[EventEnvelope, object], Awaitable[None]]
"""A per-event handler. Raise ``TransientHandlerError`` to force redelivery."""


class HandlerRegistry:
    """Maps an ``event_type`` to the coroutine that processes it.

    A default handler may be registered for messages with no ``event_type`` or an
    unknown one; when absent, unknown types are a no-trigger decision (ACK).
    """

    def __init__(self, default: MessageHandlerFn | None = None) -> None:
        """Create a registry with an optional fallback handler for unknown types."""
        self._handlers: dict[str, MessageHandlerFn] = {}
        self._default = default

    def register(self, event_type: str, handler: MessageHandlerFn) -> None:
        """Map an ``event_type`` to the handler that processes it."""
        self._handlers[event_type] = handler

    def resolve(self, event_type: str | None) -> MessageHandlerFn | None:
        """Return the handler for ``event_type``, falling back to the default."""
        if event_type is not None and event_type in self._handlers:
            return self._handlers[event_type]
        return self._default

    def event_types(self) -> tuple[str, ...]:
        """Return the explicitly registered event types."""
        return tuple(self._handlers)
