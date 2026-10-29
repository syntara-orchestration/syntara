"""Authentication utilities.

This module provides JWT token services, session management, authentication
dependencies, and infrastructure for the Syntara platform.

Submodules:
    - services: Token creation, validation, and key management
    - session: PostgreSQL-based refresh token storage
    - exceptions: Authentication-specific exceptions
    - dependencies: FastAPI dependency injection functions

``get_current_user`` is exported lazily so lightweight helpers such as
``syntara.auth.passwords`` can be imported before secrets exist (``make secrets``).
"""

from typing import Any

__all__ = [
    "get_current_user",
]


def __getattr__(name: str) -> Any:  # noqa: ANN401
    """Load FastAPI auth dependencies on first access only."""
    if name == "get_current_user":
        from syntara.auth.dependencies import get_current_user  # noqa: PLC0415

        return get_current_user
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
