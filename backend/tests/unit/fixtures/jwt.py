"""JWT authentication fixtures specific to unit tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from syntara.auth.services.token_service import TokenService

if TYPE_CHECKING:
    from collections.abc import Callable

    from syntara.core.models import User


@pytest.fixture
def token_service() -> TokenService:
    """Create a TokenService instance for generating test tokens."""
    return TokenService()


@pytest.fixture
def create_jwt_for_user(token_service: TokenService) -> Callable[[User], str]:
    """Factory fixture to create JWT tokens for any user."""

    def _create_token(user: User) -> str:
        return token_service.create_access_token(
            subject_id=user.id,
            username=user.username,
            email=user.email or "",
        )

    return _create_token
