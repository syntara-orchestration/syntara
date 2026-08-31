"""Request-scoped context for distinguishing API edit requests from background writes."""

from contextvars import ContextVar

MUTATING_METHODS = frozenset({"PATCH", "PUT"})

is_mutating_request_context_var: ContextVar[bool] = ContextVar("is_mutating_request", default=False)
