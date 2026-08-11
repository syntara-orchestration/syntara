"""Session factory utilities for database operations."""

from collections.abc import AsyncGenerator, Callable
from typing import cast

from fastapi import Request
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.database.session import get_db


def create_session_factory_from_request(request: Request) -> Callable[[], AsyncGenerator[AsyncSession, None]]:
    """Create a session factory that respects FastAPI's dependency injection overrides.

    This function creates a session factory that checks for dependency overrides
    in the FastAPI app instance, allowing tests to inject mock database sessions.

    Args:
        request: FastAPI request object (contains app with dependency overrides)

    Returns:
        Session factory function that creates database sessions

    """
    # Access the FastAPI app instance from the request to get dependency overrides
    app = request.app
    dependency_overrides = getattr(app, "dependency_overrides", {})

    # Use the overridden dependency if it exists, otherwise use the default
    return cast("Callable[[], AsyncGenerator[AsyncSession, None]]", dependency_overrides.get(get_db, get_db))
