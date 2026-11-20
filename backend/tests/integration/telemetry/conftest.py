"""Fixtures for telemetry integration tests."""

from collections.abc import AsyncGenerator, Callable
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.database.session import get_db


@pytest.fixture
def override_get_db(
    test_db_session: AsyncSession, session_app: FastAPI
) -> Callable[[], AsyncGenerator[AsyncSession, None]]:
    """Create a get_db override that yields the test database session.

    Mirrors the app.dependency_overrides[get_db] pattern used elsewhere
    in the test suite. Sets the override on the FastAPI app and returns
    the callable for direct injection into services that accept a
    session_factory parameter.
    """

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield test_db_session

    session_app.dependency_overrides[get_db] = _override

    return _override


@pytest.fixture
def mock_session_factory(
    test_db_session: AsyncSession,
) -> async_sessionmaker[AsyncSession]:
    """Create a mock async_sessionmaker that returns the test database session.

    This fixture creates a callable that mimics async_sessionmaker behavior
    for use with PeriodicCollector and other services that expect a
    session factory rather than a generator-based dependency.
    """
    factory = MagicMock(spec=async_sessionmaker)

    # Make the factory callable and return an async context manager
    # that yields the test session
    class _SessionContextManager:
        async def __aenter__(self) -> AsyncSession:
            return test_db_session

        async def __aexit__(self, *args: object) -> None:
            pass

    factory.return_value = _SessionContextManager()
    factory.side_effect = lambda: _SessionContextManager()

    return factory
