"""User fixtures shared across unit and integration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlmodel import select

from syntara.authz.resolver import AUTHENTICATED_GROUP_NAME
from syntara.core.models import User

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture
def default_user_data() -> dict[str, Any]:
    """Provide default user attributes."""
    from syntara.auth.passwords import hash_password

    return {
        "username": "testuser",
        "email": "testuser@example.com",
        "first_name": "Test",
        "last_name": "User",
        "password_hash": hash_password("password123"),
    }


@pytest_asyncio.fixture
async def user_factory(
    test_db_session: AsyncSession, default_user_data: dict[str, Any]
) -> Callable[..., Awaitable[User]]:
    """Factory fixture for creating a custom user."""

    async def _create_user(**overrides: object) -> User:
        group_names: list[str] | None = overrides.pop("group_names", None)  # type: ignore[assignment]
        if "username" not in overrides and "email" not in overrides:
            unique_suffix = str(uuid4())[:8]
            user_data = {
                **default_user_data,
                "username": f"testuser-{unique_suffix}",
                "email": f"testuser-{unique_suffix}@example.com",
                **overrides,
            }
        else:
            user_data = {**default_user_data, **overrides}
        user = User(**user_data)
        test_db_session.add(user)
        await test_db_session.flush()

        from sqlalchemy import insert

        from syntara.core.models.group import Group, user_groups

        if group_names:
            for name in group_names:
                group = (await test_db_session.exec(select(Group).where(Group.name == name))).one()
                await test_db_session.exec(insert(user_groups).values(user_id=user.id, group_id=group.id))

        if not group_names or AUTHENTICATED_GROUP_NAME not in group_names:
            auth_group = (
                await test_db_session.exec(select(Group).where(Group.name == AUTHENTICATED_GROUP_NAME))
            ).first()
            if auth_group:
                await test_db_session.exec(insert(user_groups).values(user_id=user.id, group_id=auth_group.id))

        await test_db_session.commit()
        return user

    return _create_user


@pytest_asyncio.fixture
async def test_user(user_factory: Callable[..., Awaitable[User]]) -> User:
    """Create test user with default attributes."""
    return await user_factory()


@pytest_asyncio.fixture
async def admin_user(test_db_session: AsyncSession, user_factory: Callable[..., Awaitable[User]]) -> User:
    """Get or create admin user with username 'admin'."""
    async with test_db_session:
        query = select(User).filter(User.username == "admin")  # type: ignore[arg-type]
        result = await test_db_session.exec(query)
        admin = result.one_or_none()
        if admin is None:
            admin = await user_factory(
                username="admin",
                first_name="Admin",
                last_name="User",
            )
        return admin
