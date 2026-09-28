"""Configuration errors distinct from a no-match reconcile outcome."""


class UnknownBackendTypeError(LookupError):
    """Raised when no WorkerManager is registered for an ExecutionTarget backend."""

    def __init__(self, backend_type: str) -> None:
        """Identify the unregistered backend type."""
        self.backend_type = backend_type
        super().__init__(f"No WorkerManager registered for backend_type {backend_type!r}")
