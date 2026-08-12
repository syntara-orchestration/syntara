"""Integration tests for file upload authorization."""

from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from tests.fixtures.files import get_fixtures_dir
from tests.integration.helpers.error_data import assert_error_data


@pytest.fixture
def sample_pdf_path() -> Path:
    """Provide path to sample PDF file."""
    return get_fixtures_dir() / "sample.pdf"


@pytest_asyncio.fixture
async def authenticated_only_user(
    user_factory: Callable[..., Awaitable[User]],
    test_db_session: AsyncSession,
) -> User:
    """Create a user with only the 'authenticated' role (no 'user' role).

    This user is authenticated but lacks the 'user' role required for file upload.
    Note: user is created but NOT added to the test-users group, so they only have
    the 'authenticated' role, not the 'user' role.
    """
    return await user_factory(username="auth-only", email="auth-only@example.com")


@pytest_asyncio.fixture
async def authenticated_only_client(base_client: AsyncClient, authenticated_only_user: User) -> AsyncClient:
    """Authenticated client with only the 'authenticated' role (no 'user' role)."""
    from syntara.api.main import app
    from syntara.auth.dependencies import get_current_user

    async def override() -> User:
        return authenticated_only_user

    app.dependency_overrides[get_current_user] = override
    return base_client


@pytest.mark.asyncio
async def test_upload_authorised(auth_client: AsyncClient, sample_pdf_path: Path, test_project_id: str) -> None:
    """Test that users with 'user' role can successfully upload files."""
    file_content = sample_pdf_path.read_bytes()
    files = [("files", ("sample.pdf", file_content, "application/pdf"))]

    # Act
    response = await auth_client.post(
        "/api/v1/files",
        files=files,
        data={"project_id": test_project_id},
    )

    # Assert
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_upload_unauthorised(authenticated_only_client: AsyncClient) -> None:
    """Test that authenticated users without 'user' role receive 403 Forbidden.

    The authenticated_only_client provides a user with only the 'authenticated' role,
    lacking the 'user' role required for file upload.
    """
    files: list[tuple[str, tuple[str, bytes, str]]] = []

    # Act
    response = await authenticated_only_client.post(
        "/api/v1/files",
        files=files,
    )

    # Assert
    assert response.status_code == 403
    assert_error_data(
        response,
        error_type="https://api.example.com/errors/forbidden",
        title="Authorization Denied",
        detail="Not authorized to perform upload on files",
        code="AUTHORIZATION_DENIED",
        retryable=False,
    )
