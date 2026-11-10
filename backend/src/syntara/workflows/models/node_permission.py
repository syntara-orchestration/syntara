"""Public step-type write denial response, without policy provenance."""

from typing import Literal

from sqlmodel import SQLModel

from syntara.core.models.error import ErrorData


class BlockedStepType(SQLModel):
    """A step type the caller cannot author."""

    kind: str
    label: str
    reason: Literal["explicit_deny", "no_matching_allow"]
    project: str | None


class WorkflowWriteForbiddenProblemDetail(ErrorData):
    """Standard forbidden response with optional step-type denial details."""

    blocked_step_types: list[BlockedStepType] | None = None


class NodeKindWriteDeniedProblemDetail(WorkflowWriteForbiddenProblemDetail):
    """RFC 9457 permission denial with blocked step types."""

    status: int = 403
    code: Literal["NODE_KIND_WRITE_DENIED"] = "NODE_KIND_WRITE_DENIED"
    retryable: bool = False
    blocked_step_types: list[BlockedStepType]
