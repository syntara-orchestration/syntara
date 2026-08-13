"""Shared user query utilities.

Provides reusable query functions for user lookups, used by both
UsersService and GroupsService to avoid duplication.
"""

from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth.exceptions import UserNotFoundError
from syntara.core.models import User


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User:
    """Get a user by ID, excluding soft-deleted users.

    Args:
        session: Database session
        user_id: User UUID

    Returns:
        User instance

    Raises:
        UserNotFoundError: If user not found or deleted

    """
    result = await session.exec(
        select(User).filter(
            User.id == user_id,  # type: ignore[arg-type]
            User.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    user = result.one_or_none()

    if not user:
        raise UserNotFoundError(user_id)

    return user
