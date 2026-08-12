"""Shared fixtures for integration API tests.

Provides automatic regopy-based evaluation and authz data seeding so that all
API tests work with authorization always enabled, using the real rego policy
instead of a Python reimplementation.
"""

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.api.main import app
from syntara.auth.dependencies import get_current_user
from syntara.authz.dependencies import get_authz_evaluator
from syntara.authz.evaluator import evaluate_policy_input
from syntara.authz.models import Project, RoleAssignment
from syntara.authz.seed import seed_authz_data
from syntara.core.models import User
from syntara.core.models.group import Group, user_groups

# Name for the test group that grants the 'user' role
_TEST_GROUP_NAME = "test-users"


def _opa_evaluate_cli(opa_input: dict[str, Any]) -> dict[str, Any]:
    """Evaluate authz using regopy against the real rego policy."""
    return evaluate_policy_input(opa_input)


@pytest.fixture(autouse=True)
async def _seed_authz(test_db_session: AsyncSession) -> None:
    """Re-seed built-in authz data and set up default permissions for tests.

    Creates:
    - Built-in policies, roles, groups, and default project
    - A 'test-users' group bound to the 'user' role
    - A dev-user in that group (for unauthenticated base_client requests)
    """
    await seed_authz_data(test_db_session)

    from syntara.workflows.seed_builtin import seed_builtin_workflows

    await seed_builtin_workflows(test_db_session)

    # Create a group with the 'admin' role for test users (functional tests need
    # broad permissions; authz-specific tests create their own limited-role users)
    test_group = Group(id=uuid4(), name=_TEST_GROUP_NAME, description="Test users group", is_builtin=False, labels={})
    test_db_session.add(test_group)
    await test_db_session.flush()
    test_db_session.add(
        RoleAssignment(
            id=uuid4(),
            group_id=test_group.id,
            role_name="admin",
        )
    )

    # Create dev-user and add to the group
    dev_user = User(
        id=uuid4(),
        username="dev-user",
        email="dev@example.com",
        first_name="Development",
        last_name="User",
        password_hash="$argon2id$test",  # noqa: S106
        is_enabled=True,
    )
    test_db_session.add(dev_user)
    await test_db_session.flush()
    await test_db_session.exec(insert(user_groups).values(user_id=dev_user.id, group_id=test_group.id))

    await test_db_session.commit()


@pytest_asyncio.fixture
async def test_user(
    user_factory: Callable[..., Awaitable[User]],
    test_db_session: AsyncSession,
) -> User:
    """Create test user and add to the test-users group for authorization.

    Overrides the root conftest test_user to also grant the 'user' role.
    """
    user = await user_factory()

    test_group = (await test_db_session.exec(select(Group).where(Group.name == _TEST_GROUP_NAME))).first()
    if test_group:
        await test_db_session.exec(insert(user_groups).values(user_id=user.id, group_id=test_group.id))
        await test_db_session.commit()

    return user


@pytest_asyncio.fixture
async def admin_user(
    user_factory: Callable[..., Awaitable[User]],
    test_db_session: AsyncSession,
) -> User:
    """Create a test user with admin role for user/group/idp management tests."""
    user = await user_factory(username="admin-test", email="admin-test@example.com", is_builtin=True)
    await make_admin(test_db_session, user)
    return user


@pytest_asyncio.fixture
async def admin_client(base_client: AsyncClient, admin_user: User) -> AsyncClient:
    """Authenticated client with admin permissions."""

    async def override() -> User:
        return admin_user

    app.dependency_overrides[get_current_user] = override
    return base_client


@pytest.fixture
def auth_as() -> Callable[[User], None]:
    """Return a callable that overrides the current user dependency.

    Usage:
        auth_as(some_user)  # switches auth to some_user
    """

    def _do_auth_as(user: User) -> None:
        async def override() -> User:
            return user

        app.dependency_overrides[get_current_user] = override

    return _do_auth_as


async def _make_role_assignment(
    session: AsyncSession,
    user: User,
    role_name: str,
) -> None:
    """Assign a named role to a user via a dedicated group."""
    group = Group(name=f"{role_name}-grp-{uuid4()}", description="", labels={})
    session.add(group)
    await session.flush()
    session.add(
        RoleAssignment(
            group_id=group.id,
            role_name=role_name,
        )
    )
    await session.exec(insert(user_groups).values(user_id=user.id, group_id=group.id))
    await session.commit()


async def make_admin(session: AsyncSession, user: User) -> None:
    """Assign the admin role to a user via a dedicated group."""
    await _make_role_assignment(session, user, "admin")


async def make_auditor(session: AsyncSession, user: User) -> None:
    """Assign the auditor role to a user via a dedicated group."""
    await _make_role_assignment(session, user, "auditor")


async def make_user_role(session: AsyncSession, user: User) -> None:
    """Assign the user role to a user via a dedicated group."""
    await _make_role_assignment(session, user, "user")


async def make_project_user(
    session: AsyncSession,
    user: User,
    project: "Project",
) -> RoleAssignment:
    """Assign project-user role to a user for a specific project."""
    assignment = RoleAssignment(
        principal_id=user.id,
        project_id=project.id,
        role_name="project-user",
    )
    session.add(assignment)
    await session.commit()
    return assignment


async def make_project_admin(
    session: AsyncSession,
    user: User,
    project: "Project",
) -> RoleAssignment:
    """Assign project-admin role to a user for a specific project."""
    assignment = RoleAssignment(
        principal_id=user.id,
        project_id=project.id,
        role_name="project-admin",
    )
    session.add(assignment)
    await session.commit()
    return assignment


@pytest_asyncio.fixture
async def test_project_id(test_db_session: AsyncSession) -> str:
    """Create a test project and return its ID as a string."""
    project = Project(name=f"test-project-{uuid4().hex[:8]}", description="Test project for API tests")
    test_db_session.add(project)
    await test_db_session.commit()
    await test_db_session.refresh(project)
    return str(project.id)


@pytest.fixture(autouse=True)
def _mock_evaluator(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the authz evaluator with one that uses regopy directly."""
    mock_evaluator = AsyncMock()
    mock_evaluator.evaluate = MagicMock(side_effect=_opa_evaluate_cli)

    def _mock_getter(request: Any = None) -> AsyncMock:  # noqa: ANN401
        return mock_evaluator

    monkeypatch.setattr("syntara.authz.dependencies.get_authz_evaluator", _mock_getter)
    monkeypatch.setattr("syntara.authz.dependencies.get_authz_evaluator", _mock_getter)
    monkeypatch.setattr("syntara.authz.router.get_authz_evaluator", _mock_getter)
    monkeypatch.setattr("syntara.authz.role_assignment_router.get_authz_evaluator", _mock_getter)
    monkeypatch.setattr("syntara.workflows.executions_router.get_authz_evaluator", _mock_getter)

    # Also override via FastAPI dependency_overrides so Depends(...) resolves correctly.
    app.dependency_overrides[get_authz_evaluator] = lambda: mock_evaluator
    app.dependency_overrides[get_authz_evaluator] = lambda: mock_evaluator


def mcp_payload(name: str | None = None, scope: str = "global") -> dict[str, object]:
    """Build an MCP integration creation payload for tests."""
    return {
        "name": name or f"test-intg-{uuid4().hex[:8]}",
        "integration_type": "mcp_server",
        "scope": scope,
        "configuration": {
            "integration_type": "mcp_server",
            "base_url": "https://mcp.example.com",
        },
    }
