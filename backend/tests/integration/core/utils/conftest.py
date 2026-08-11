"""Conftest for utils unit tests.

This module provides shared fixtures for utility function tests.
"""
# ruff: noqa: DTZ001

from datetime import datetime

import pytest_asyncio
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth.passwords import hash_password
from syntara.core.models import User

_TEST_PW_HASH = hash_password("testpassword")


@pytest_asyncio.fixture
async def test_users(test_db_session: AsyncSession) -> list[User]:
    """Create test data for filtering and sorting tests.

    With rollback-based test isolation seeded data (e.g. the bootstrap
    admin user) is visible inside the test session.  We therefore return
    **all** users present in the database so that assertions like
    ``len(result) == len(test_users)`` remain correct.

    Pre-existing users that have timezone-aware ``created_at`` values are
    normalised to naive UTC so that Python-side comparisons in tests
    (e.g. ``u.created_at > datetime(…)``) do not raise ``TypeError``.

    Args:
        test_db_session: Async PostgreSQL test session from conftest

    Returns:
        List of all Users in the database (seeded + fixture-created)

    """
    # Add test data with various label combinations for comprehensive testing
    fixture_users = [
        User(
            username="alice",
            email="alice@example.com",
            first_name="Alice",
            last_name="Smith",
            password_hash=_TEST_PW_HASH,
            is_enabled=True,
            labels={
                "environment": "production",
                "region": "us-east-1",
                "team": "platform",
                "service": "api",
                "version": "v1.2.0",
            },
            created_at=datetime(2025, 1, 1, 10, 0, 0),
        ),
        User(
            username="bob",
            email="bob@example.com",
            first_name="Bob",
            last_name="Johnson",
            password_hash=_TEST_PW_HASH,
            is_enabled=True,
            labels={
                "environment": "production",
                "region": "us-west-2",
                "team": "frontend",
                "service": "web",
                "version": "v2.1.0",
            },
            created_at=datetime(2025, 1, 2, 11, 0, 0),
        ),
        User(
            username="charlie",
            email="charlie@example.com",
            first_name="Charlie",
            last_name="Brown",
            password_hash=_TEST_PW_HASH,
            is_enabled=False,
            labels={
                "environment": "staging",
                "region": "us-east-1",
                "team": "platform",
                "service": "api",
                "version": "v1.3.0-beta",
            },
            created_at=datetime(2025, 1, 3, 12, 0, 0),
        ),
        User(
            username="diana",
            email="diana@example.com",
            first_name="Diana",
            last_name="Prince",
            password_hash=_TEST_PW_HASH,
            is_enabled=True,
            labels={
                "environment": "production",
                "region": "us-east-1",
                "team": "data",
                "service": "processor",
                "version": "v3.0.1",
            },
            created_at=datetime(2025, 1, 4, 13, 0, 0),
        ),
        User(
            username="eve",
            email="eve@example.com",
            first_name="Eve",
            last_name="Davis",
            password_hash=_TEST_PW_HASH,
            is_enabled=False,
            labels={"environment": "development", "region": "us-west-1", "team": "dev", "experimental": "true"},
            created_at=datetime(2025, 1, 5, 14, 0, 0),
        ),
    ]

    for user in fixture_users:
        test_db_session.add(user)
    await test_db_session.flush()

    result = await test_db_session.exec(select(User))
    all_users = list(result.all())

    # Normalise tz-aware created_at to naive UTC so Python comparisons work
    for user in all_users:
        if user.created_at is not None and user.created_at.tzinfo is not None:
            user.created_at = user.created_at.replace(tzinfo=None)

    return all_users
