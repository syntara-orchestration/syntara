"""JWT authentication fixtures for integration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable
    from contextlib import AbstractContextManager

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


@pytest_asyncio.fixture
async def internal_service_client(
    test_db_session: AsyncSession,
    session_app: FastAPI,
    test_user: User,
    override_settings: Callable[..., AbstractContextManager[object]],
) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client that calls the API as an mTLS-authenticated internal service.

    ASGITransport has no TLS handshake, so this reproduces what
    ``ClientCertAuthMiddleware`` sets for an allowlisted client certificate
    (``is_cert_authenticated`` and ``cert_cn`` in the ASGI scope state). S2S
    TLS is enabled for the duration. No bearer token is sent, so
    ``get_current_user`` takes the cert path. ``X-On-Behalf-Of`` attributes
    writes to ``test_user``.
    """
    from typing import Any

    from httpx import ASGITransport, AsyncClient

    from syntara.core.database.session import get_db

    async def cert_authenticated_app(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
        if scope["type"] == "http":
            state = scope.setdefault("state", {})
            state["is_cert_authenticated"] = True
            state["cert_cn"] = "worker.ao.svc"
        await session_app(scope, receive, send)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield test_db_session

    saved = dict(session_app.dependency_overrides)
    session_app.dependency_overrides[get_db] = override_get_db
    try:
        with override_settings(s2s_tls_enabled=True):
            async with AsyncClient(
                transport=ASGITransport(app=cert_authenticated_app),
                base_url="http://test",
                headers={"X-On-Behalf-Of": str(test_user.id)},
            ) as client:
                yield client
    finally:
        session_app.dependency_overrides.clear()
        session_app.dependency_overrides.update(saved)
