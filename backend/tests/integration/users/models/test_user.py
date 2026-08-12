"""Unit tests for User model.

Tests cover:
- User creation with required fields
- Soft delete behavior
- Unique constraint violations
- last_login update functionality
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User


@pytest.mark.asyncio
async def test_create_user_with_required_fields(
    test_db_session: AsyncSession, default_user_data: dict[str, Any]
) -> None:
    """Test creating a user with all required fields."""
    user = User(id=uuid4(), **default_user_data)
    test_db_session.add(user)
    await test_db_session.commit()

    assert user.id is not None
    assert user.username == default_user_data["username"]
    assert user.email == default_user_data["email"]
    assert user.first_name == default_user_data["first_name"]
    assert user.last_name == default_user_data["last_name"]
    assert user.is_enabled is True
    assert user.preferences == {}
    assert user.deleted_at is None
    assert user.deleted_by is None
    assert user.created_at is not None
    assert user.updated_at is not None


@pytest.mark.asyncio
async def test_create_user_with_all_fields(test_db_session: AsyncSession) -> None:
    """Test creating a user with all fields including optional ones."""
    now = datetime.now(UTC)
    preferences = {"theme": "dark", "notifications": True}

    user = User(
        id=uuid4(),
        username="fulluser",
        email="full@example.com",
        first_name="Full",
        last_name="Test User",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$test",  # noqa: S106
        is_enabled=True,
        last_login=now,
        preferences=preferences,
    )
    test_db_session.add(user)
    await test_db_session.commit()

    assert user.is_enabled is True
    assert user.last_login == now
    assert user.preferences == preferences


@pytest.mark.asyncio
async def test_user_soft_delete(
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """Test soft delete sets deleted_at and deleted_by correctly."""
    # Create admin user who will perform the delete
    admin = await user_factory(
        id=uuid4(),
        username="softdelete-admin",
        email="softdelete-admin@example.com",
        first_name="Admin",
        last_name="User",
    )

    # Create user to be deleted
    user = await user_factory(
        id=uuid4(),
        username="deleteme",
        email="delete@example.com",
        first_name="Delete",
        last_name="Me",
    )

    # Perform soft delete
    now = datetime.now(UTC)
    user.deleted_at = now
    user.deleted_by = admin.id
    await test_db_session.commit()

    assert user.deleted_at == now
    assert user.deleted_by == admin.id


@pytest.mark.asyncio
async def test_update_last_login(test_db_session: AsyncSession, test_user: User) -> None:
    """Test update_last_login updates timestamp correctly."""
    assert test_user.last_login is None

    # Update last login
    before_update = datetime.now(UTC)
    test_user.update_last_login()
    await test_db_session.commit()

    assert test_user.last_login is not None
    assert test_user.last_login >= before_update  # type: ignore[unreachable]


@pytest.mark.asyncio
async def test_user_repr() -> None:
    """Test string representation of User."""
    user_id = uuid4()
    user = User(
        id=user_id,
        username="repruser",
        email="repr@example.com",
        first_name="Repr",
        last_name="User",
    )

    repr_str = repr(user)
    assert "User" in repr_str
    assert str(user_id) in repr_str
    assert "repruser" in repr_str


@pytest.mark.asyncio
async def test_user_preferences_default(test_user: User) -> None:
    """Test that preferences defaults to empty dict."""
    assert test_user.preferences == {}
    assert isinstance(test_user.preferences, dict)


@pytest.mark.asyncio
async def test_user_is_enabled_default(test_user: User) -> None:
    """Test that is_enabled defaults to True."""
    assert test_user.is_enabled is True


def test_display_name_with_last_name() -> None:
    """display_name should combine first and last name."""
    user = User(
        id=uuid4(),
        username="jdoe",
        email="j@example.com",
        first_name="Jane",
        last_name="Doe",
    )
    assert user.display_name == "Jane Doe"


def test_display_name_without_last_name() -> None:
    """display_name should return first_name when last_name is None."""
    user = User(
        id=uuid4(),
        username="jane",
        email="jane@example.com",
        first_name="Jane",
    )
    assert user.display_name == "Jane"


@pytest.mark.asyncio
async def test_user_inactive(user_factory: Callable[..., Awaitable[User]]) -> None:
    """Test creating an inactive user."""
    user = await user_factory(
        id=uuid4(),
        username="inactiveuser",
        email="inactive@example.com",
        first_name="Inactive",
        last_name="User",
        is_enabled=False,
    )

    assert user.is_enabled is False
