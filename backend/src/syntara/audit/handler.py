"""Generic base class for audit event handlers."""

from abc import ABC, abstractmethod

from syntara.audit.models.audit_event import AuditEvent


class AuditEventHandler[T](ABC):
    """Maps a domain-specific event to a normalized AuditEvent.

    Subclasses declare their event type via the generic parameter::

        class LoginAttemptHandler(AuditEventHandler[LoginAttemptEvent]):
            def handle(self, event: LoginAttemptEvent) -> AuditEvent: ...

    Discovery introspects the type parameter to build a
    ``{event_type: handler}`` registry for O(1) dispatch.

    Handlers MUST be zero-arg constructable — auto-discovery
    (:func:`syntara.audit.discovery.discover_handlers`) instantiates each
    concrete subclass via ``cls()``. Handlers that need collaborators
    should resolve them lazily inside :meth:`handle` (e.g. via a module-level
    factory) rather than taking constructor arguments.
    """

    @abstractmethod
    def handle(self, event: T) -> AuditEvent | None:
        """Map a single domain event to a normalized AuditEvent.

        Return ``None`` for side-effect-only handlers (e.g. telemetry
        emitters) that do not produce an audit trail entry.
        """
