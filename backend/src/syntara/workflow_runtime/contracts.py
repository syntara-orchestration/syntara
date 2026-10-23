"""Engine-independent contracts for registered business activities."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class ActivityContext:
    """Trusted identity of one logical node occurrence and its current attempt."""

    execution_id: UUID
    project_id: UUID
    node_execution_id: str
    idempotency_key: str
    completion_ref: UUID | None = None


@dataclass(frozen=True)
class Completed:
    """Final business output, before the runtime adds the V2 output envelope."""

    output: dict[str, Any]


@dataclass(frozen=True)
class Deferred:
    """Handoff to durable work that will complete through the completion service."""

    completion_ref: UUID
    external_operation_id: str


class ActivityError(Exception):
    """Business failure with an engine-independent retry classification."""

    def __init__(self, message: str, *, code: str = "ActivityError", retryable: bool = False) -> None:
        """Describe a failure without importing the engine SDK."""
        super().__init__(message)
        self.code = code
        self.retryable = retryable
