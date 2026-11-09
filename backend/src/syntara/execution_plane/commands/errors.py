"""Command-handler failures mapped by the command ingress."""


class CommandDependencyUnavailableError(RuntimeError):
    """A required command dependency is unavailable."""
