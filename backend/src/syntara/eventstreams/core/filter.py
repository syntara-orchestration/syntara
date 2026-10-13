"""Message filtering — the trigger / no-trigger gate.

A filter produces a single boolean decision per message from headers, key, and
(optionally) the decoded payload. This is a minimal, pluggable seam; the richer
expression language (JMESPath/CEL/Rego per ANSTRAT-1934 P4) can be added as
another :class:`MessageFilter` without touching the runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping

    from syntara.eventstreams.core.envelope import EventEnvelope


@runtime_checkable
class MessageFilter(Protocol):
    """Decides whether a message should trigger a workflow."""

    def matches(self, envelope: EventEnvelope, payload: object) -> bool:
        """Return ``True`` if the message should trigger a workflow."""
        ...


class AllowAllFilter:
    """Default: every message triggers (no filter configured)."""

    def matches(self, envelope: EventEnvelope, payload: object) -> bool:  # noqa: ARG002
        """Return ``True`` for every message."""
        return True


class HeaderEqualityFilter:
    """Triggers only when all configured header key/value pairs match exactly.

    A small, dependency-free filter useful for routing metadata without decoding
    the payload. Intended as a placeholder for the full expression language.
    """

    def __init__(self, required_headers: Mapping[str, str]) -> None:
        """Store the header key/value pairs that must all match to trigger."""
        self._required = dict(required_headers)

    def matches(self, envelope: EventEnvelope, payload: object) -> bool:  # noqa: ARG002
        """Return ``True`` only when every required header matches exactly."""
        return all(envelope.headers.get(k) == v for k, v in self._required.items())
