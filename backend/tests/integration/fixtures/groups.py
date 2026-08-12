"""Group-related fixtures for integration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest_asyncio

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User
    from syntara.core.models.group import Group


@pytest_asyncio.fixture
async def test_group(test_db_session: AsyncSession, test_user: User) -> Group:
    """Create a single test group."""
    from syntara.core.models.group import Group

    group = Group(
        id=uuid4(),
        name="test-group",
        description="A test group",
        created_by=test_user.id,
    )
    test_db_session.add(group)
    await test_db_session.commit()
    await test_db_session.refresh(group)
    return group


@pytest_asyncio.fixture
async def group_with_members(
    test_db_session: AsyncSession,
    test_user: User,
    test_group: Group,
    multiple_local_users: list[User],
) -> tuple[Group, list[User]]:
    """Create a group with members for membership tests."""
    from sqlalchemy import insert

    from syntara.core.models.group import user_groups

    members = multiple_local_users[:3]
    for user in members:
        await test_db_session.exec(insert(user_groups).values(user_id=user.id, group_id=test_group.id))
    await test_db_session.commit()

    return test_group, members


@pytest_asyncio.fixture
async def multiple_test_groups(test_db_session: AsyncSession, test_user: User) -> list[Group]:
    """Create multiple test groups for pagination, filtering, and sorting tests."""
    from syntara.core.models.group import Group

    groups = [
        Group(id=uuid4(), name="Alpha Group", description="First group", created_by=test_user.id),
        Group(id=uuid4(), name="Beta Group", description="Second group", created_by=test_user.id),
        Group(id=uuid4(), name="Gamma Group", description="Third group", created_by=test_user.id),
        Group(id=uuid4(), name="Delta Group", description="Fourth group", created_by=test_user.id),
        Group(id=uuid4(), name="Echo Group", description="Fifth group", created_by=test_user.id),
        Group(id=uuid4(), name="Foxtrot Group", description="Sixth group", created_by=test_user.id),
    ]

    for group in groups:
        test_db_session.add(group)

    await test_db_session.commit()

    for group in groups:
        await test_db_session.refresh(group)

    return groups
