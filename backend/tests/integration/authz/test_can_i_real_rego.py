"""Integration test: can-i consistency with the real regopy evaluator.

Exercises the actual in-process evaluator path that all other tests mock out.
Verifies that the embedded evaluator returns ``allow: true`` for permissions
the user actually has.
"""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from sqlalchemy import insert
from sqlmodel.ext.asyncio.session import AsyncSession

from nexus.authz.engine import AuthzRequest, authorize
from nexus.authz.evaluator import RegoEvaluator
from nexus.authz.models import RoleAssignment
from nexus.authz.resolver import resolve_effective_policies
from nexus.authz.seed import seed_authz_data
from nexus.core.models import User
from nexus.core.models.group import Group, user_groups

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def real_authz_evaluator() -> AsyncGenerator[RegoEvaluator, None]:
    """Create the real in-process authz evaluator."""
    evaluator = RegoEvaluator()
    evaluator.start()
    assert await evaluator.health() is True
    yield evaluator
    await evaluator.stop()


@pytest.fixture(autouse=True)
async def _seed(test_db_session: AsyncSession) -> None:
    """Seed built-in policies, roles, and groups before each test."""
    await seed_authz_data(test_db_session)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_user(session: AsyncSession, username: str) -> User:
    user = User(
        id=uuid4(),
        username=username,
        email=f"{username}@test.local",
        first_name=username.title(),
        password_hash="$argon2id$test",  # noqa: S106
        is_enabled=True,
    )
    session.add(user)
    await session.flush()
    return user


async def _assign_role(
    session: AsyncSession,
    user: User,
    role_name: str,
) -> None:
    group = Group(name=f"{role_name}-{uuid4()}", description="", labels={})
    session.add(group)
    await session.flush()
    session.add(RoleAssignment(group_id=group.id, role_name=role_name))
    await session.exec(insert(user_groups).values(user_id=user.id, group_id=group.id))
    await session.commit()


# ---------------------------------------------------------------------------
# Tests — these call authorize() with the real evaluator, not the mock.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_policy_create_allowed(
    test_db_session: AsyncSession,
    real_authz_evaluator: RegoEvaluator,
) -> None:
    """Admin user + policy:create must be allowed via the real evaluator."""
    user = await _make_user(test_db_session, "test-admin")
    await _assign_role(test_db_session, user, "admin")

    result = await authorize(
        test_db_session,
        real_authz_evaluator,
        AuthzRequest(user_id=user.id, action="create", resource_type="policy", resource_id=""),
    )

    assert result.allowed is True, (
        f"real evaluator returned allowed={result.allowed} for admin+policy:create "
        f"(matched_policy='{result.matched_policy}', denied={result.denied})"
    )


@pytest.mark.asyncio
async def test_user_directory_read_allowed(
    test_db_session: AsyncSession,
    real_authz_evaluator: RegoEvaluator,
) -> None:
    """Regular user + user-directory:read must be allowed via the real evaluator."""
    user = await _make_user(test_db_session, "test-user")
    await _assign_role(test_db_session, user, "user")

    result = await authorize(
        test_db_session,
        real_authz_evaluator,
        AuthzRequest(user_id=user.id, action="read", resource_type="user-directory", resource_id=""),
    )

    assert result.allowed is True, (
        f"real evaluator returned allowed={result.allowed} for user+user-directory:read "
        f"(matched_policy='{result.matched_policy}', denied={result.denied})"
    )


@pytest.mark.asyncio
async def test_can_i_consistent_with_what_can_i(
    test_db_session: AsyncSession,
    real_authz_evaluator: RegoEvaluator,
) -> None:
    """Every scope=any allow from what-can-i must match can-i via the real evaluator.

    This is the core assertion from issue #621: what-can-i works but can-i
    returns allowed=false for the same permissions.
    """
    user = await _make_user(test_db_session, "cross-check-user")
    await _assign_role(test_db_session, user, "user")

    effective = await resolve_effective_policies(test_db_session, user.id)
    any_allows = [p for p in effective if p.get("effect") == "allow" and p.get("scope") == "any"]
    assert len(any_allows) > 0, "User should have at least one scope=any allow policy"

    failures: list[str] = []
    for policy in any_allows:
        for action_str in policy.get("actions", []):
            resource_type, action = action_str.split(":", 1)
            result = await authorize(
                test_db_session,
                real_authz_evaluator,
                AuthzRequest(
                    user_id=user.id,
                    action=action,
                    resource_type=resource_type,
                    resource_id="",
                ),
            )
            if not result.allowed:
                failures.append(f"{action_str} (policy '{policy.get('name')}') → allowed={result.allowed}")

    assert not failures, (
        f"can-i disagrees with what-can-i for {len(failures)} permission(s) "
        f"via the real evaluator:\n  " + "\n  ".join(failures)
    )
