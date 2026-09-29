"""Configuration errors distinct from a no-match reconcile outcome."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from execution_plane.models.execution_target import BackendType


class UnknownBackendTypeError(LookupError):
    """Raised when no WorkerManager is registered for an ExecutionTarget backend."""

    def __init__(self, backend_type: BackendType) -> None:
        """Identify the unregistered backend type."""
        self.backend_type = backend_type
        super().__init__(f"No WorkerManager registered for backend_type {backend_type.value!r}")
