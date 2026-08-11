"""Shared fixtures for auth unit tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_session_store() -> Generator[MagicMock]:
    """Prevent DB session store calls by mocking create_session_store in unit tests."""
    mock_store = AsyncMock()
    mock_store.revoke_all_for_user.return_value = 0
    mock_store.increment_token_version.return_value = None
    with (
        patch("syntara.users.services.user_identity_service.create_session_store") as svc_cls,
        patch("syntara.users.users_router.create_session_store") as router_cls,
    ):
        svc_cls.return_value = mock_store
        router_cls.return_value = mock_store
        yield svc_cls
