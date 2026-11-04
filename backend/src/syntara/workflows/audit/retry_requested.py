"""Domain event for accepted retry requests."""

from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class WorkflowRetryRequestedEvent:
    """Domain event fired when a retry request is accepted and persisted.

    Dispatched from ExecutionService after the new retry execution row is committed.
    Handled by telemetry for Segment emission.

    Attributes:
        execution_id: The new retry execution identifier (UUID).
        source_execution_id: The parent execution being retried (UUID).
        retry_kind: Type of retry (standard, from_failure).
        node_count: Total nodes in the workflow (from_failure only, optional).
        failed_step_types: Normalized, sorted, deduplicated list of failed node types
            (from_failure only). Bounded to maximum 50 entries. Uses existing
            node-type vocabulary.
        request_id: Optional X-Request-Id from the originating HTTP request.

    """

    execution_id: UUID
    source_execution_id: UUID
    retry_kind: str
    node_count: int | None = field(default=None)
    failed_step_types: list[str] = field(default_factory=list)
    request_id: UUID | None = field(default=None)
