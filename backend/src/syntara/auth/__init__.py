"""Authentication utilities.

This module provides JWT token services, session management, authentication
dependencies, and infrastructure for the Nexus platform.

Submodules:
    - services: Token creation, validation, and key management
    - session: PostgreSQL-based refresh token storage
    - exceptions: Authentication-specific exceptions
    - dependencies: FastAPI dependency injection functions
"""

from syntara.auth.dependencies import get_current_user

__all__ = [
    "get_current_user",
]
