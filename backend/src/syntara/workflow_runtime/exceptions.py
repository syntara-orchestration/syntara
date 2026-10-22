"""Exceptions owned by workflow runtime integrations."""

from syntara.core.exceptions import SyntaraError


class WorkflowRuntimeError(SyntaraError):
    """Base exception for runtime clients and execution integrations."""
