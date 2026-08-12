"""User fixtures specific to integration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest_asyncio

from syntara.core.models import User

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest_asyncio.fixture
async def non_local_user(test_db_session: AsyncSession) -> User:
    """Create a non-local (federated) user without a password hash."""
    from syntara.core.models.user import AuthType

    user = User(
        id=uuid4(),
        username="federateduser",
        email="federated@example.com",
        first_name="Federated",
        last_name="User",
        auth_type=AuthType.FEDERATED,
    )
    test_db_session.add(user)
    await test_db_session.commit()
    return user


@pytest_asyncio.fixture
async def auth_client_as_admin(base_client: AsyncClient, admin_user: User) -> AsyncClient:
    """Create an authenticated test client with admin user."""
    from syntara.api.main import app
    from syntara.auth.dependencies import get_current_user

    async def override_get_current_user() -> User:
        return admin_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    return base_client


@pytest_asyncio.fixture
async def multiple_local_users(test_db_session: AsyncSession, test_user: User) -> list[User]:
    """Create multiple test users for pagination, filtering, and sorting tests."""
    from syntara.auth.passwords import hash_password

    users = [
        User(
            id=uuid4(),
            username="alice",
            email="alice@example.com",
            first_name="Alice",
            last_name="Anderson",
            password_hash=hash_password("password123"),
            is_enabled=True,
        ),
        User(
            id=uuid4(),
            username="bob",
            email="bob@example.com",
            first_name="Bob",
            last_name="Brown",
            password_hash=hash_password("password123"),
            is_enabled=True,
        ),
        User(
            id=uuid4(),
            username="charlie",
            email="charlie@example.com",
            first_name="Charlie",
            last_name="Clark",
            password_hash=hash_password("password123"),
            is_enabled=False,
        ),
        User(
            id=uuid4(),
            username="diana",
            email="diana@example.com",
            first_name="Diana",
            last_name="Davis",
            password_hash=hash_password("password123"),
            is_enabled=True,
        ),
        User(
            id=uuid4(),
            username="edward",
            email="edward@example.com",
            first_name="Edward",
            last_name="Evans",
            password_hash=hash_password("password123"),
            is_enabled=True,
        ),
        User(
            id=uuid4(),
            username="fiona",
            email="fiona@example.com",
            first_name="Fiona",
            last_name="Foster",
            password_hash=hash_password("password123"),
            is_enabled=True,
        ),
    ]

    for user in users:
        test_db_session.add(user)

    await test_db_session.commit()

    for user in users:
        await test_db_session.refresh(user)

    return users
