"""Unit test configuration.

Eagerly initialises the resource-actions registry so that unit tests calling
``validate_statements`` (e.g. via ``PolicyService.create_policy``) work
without booting the full app lifespan.  Integration tests get the registry
via the ``session_app`` fixture's lifespan startup instead.

Application imports are deferred to ``pytest_configure`` and fixture bodies
so that ``pytest-cov`` starts tracking *before* the modules are loaded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User

pytest_plugins = [
    "tests.unit.fixtures.mocks",
    "tests.unit.fixtures.settings",
    "tests.unit.fixtures.tools",
    "tests.unit.fixtures.jwt",
]


def pytest_configure(config: pytest.Config) -> None:
    """Build the resource-actions registry once, after coverage tracking starts."""
    from syntara.authz.resource_actions import _registry, build_resource_actions

    if _registry is None:
        from fastapi import FastAPI

        from syntara.core.router_discovery import discover_and_register_routers

        _init_app = FastAPI()
        discover_and_register_routers(app=_init_app, prefix="", enable_validation=False)
        build_resource_actions(_init_app)


TEST_ENCRYPTION_KEY = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"


@pytest.fixture(autouse=True)
def _set_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide a valid encryption key for all unit tests via env var."""
    from syntara.core.config.base import get_settings

    monkeypatch.setenv("APP_SECRET_ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_opa_cache() -> Generator[None, None, None]:
    """Disable Rego cache between unit tests to prevent cross-test pollution."""
    from syntara.authz.engine import clear_authz_cache, init_authz_cache

    init_authz_cache(enabled=False)
    yield
    clear_authz_cache()
    init_authz_cache(enabled=False)


@pytest_asyncio.fixture
async def test_project_id(test_db_session: AsyncSession) -> UUID:
    """Create a test project and return its ID."""
    from syntara.authz.models.project import Project

    project = Project(name=f"unit-test-project-{uuid4().hex[:8]}", description="Unit test project")
    test_db_session.add(project)
    await test_db_session.flush()
    return project.id


@pytest.fixture
async def users(test_db_session: AsyncSession) -> dict[str, User]:
    """Create test users for authorization tests.

    Returns a dict of users keyed by user_1, user_2, etc.
    """
    from syntara.auth.passwords import hash_password
    from syntara.core.models import User

    test_users = {
        "user_1": User(
            id=uuid4(),
            username="user_1",
            email="user1@example.com",
            first_name="User One",
            password_hash=hash_password("password123"),
            is_enabled=True,
        ),
        "user_2": User(
            id=uuid4(),
            username="user_2",
            email="user2@example.com",
            first_name="User Two",
            password_hash=hash_password("password123"),
            is_enabled=True,
        ),
    }

    for user in test_users.values():
        test_db_session.add(user)

    await test_db_session.commit()

    for user in test_users.values():
        await test_db_session.refresh(user)

    return test_users
