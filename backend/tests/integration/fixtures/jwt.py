"""JWT authentication fixtures for integration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable

    from fastapi import FastAPI
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User


@pytest_asyncio.fixture
async def jwt_client(
    test_db_session: AsyncSession,
    session_app: FastAPI,
    test_user: User,
) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with real JWT authentication."""
    from contextlib import asynccontextmanager

    from httpx import ASGITransport, AsyncClient

    from syntara.auth.services.token_service import TokenService
    from syntara.core.database.session import get_db

    access_token = TokenService().create_access_token(
        subject_id=test_user.id,
        username=test_user.username,
        email=test_user.email or "",
    )

    @asynccontextmanager
    async def _scoped_overrides(app: FastAPI) -> AsyncGenerator[None, None]:
        saved = dict(app.dependency_overrides)
        try:
            yield
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(saved)

    async with _scoped_overrides(session_app):

        async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
            yield test_db_session

        session_app.dependency_overrides[get_db] = override_get_db

        async with AsyncClient(
            transport=ASGITransport(app=session_app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {access_token}"},
        ) as client:
            yield client


@pytest.fixture
def create_jwt_for_user() -> Callable[[User], str]:
    """Factory fixture to create JWT tokens for any user."""
    from syntara.auth.services.token_service import TokenService

    _svc = TokenService()

    def _create_token(user: User) -> str:
        return _svc.create_access_token(
            subject_id=user.id,
            username=user.username,
            email=user.email or "",
        )

    return _create_token
