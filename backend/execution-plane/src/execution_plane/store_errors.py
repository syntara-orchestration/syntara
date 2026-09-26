"""Shared persistence-boundary errors."""


class StoreConfigurationError(ValueError):
    """Raised when a store is created without a database source."""

    def __init__(self) -> None:
        """Explain the required store configuration."""
        super().__init__("database_url is required when engine is not supplied")


class StoreSessionError(RuntimeError):
    """Raised when a store has no usable session source."""
