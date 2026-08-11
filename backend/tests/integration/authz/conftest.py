"""Shared fixtures for integration-level authz tests.

Provides common fixtures for engine/cache tests that use a mocked authz
evaluator.
"""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from nexus.authz import resource_actions as _resource_actions
from nexus.authz.resource_actions import _set_registry
from nexus.authz.seed import seed_authz_data

# ---------------------------------------------------------------------------
# Resource-actions registry — integration tests bypass app startup, so we
# install a registry with the pairs that appear in test statements. This is
# done per-test with save/restore (see ``_install_test_resource_actions``)
# rather than at import time: the registry is a process-global, and a permanent
# module-level mutation here leaks into other tests sharing the worker process
# under xdist (notably the unit ``test_resource_actions`` suite, which validates
# against the full application registry and fails when it sees this stub).
# ---------------------------------------------------------------------------
_TEST_RESOURCE_ACTIONS: dict[str, list[str]] = {
    "execution": ["create", "delete", "read", "run", "write"],
    "group": ["create", "delete", "read", "write"],
    "project": ["create", "delete", "read", "write"],
    "role-assignment": ["create", "delete", "read"],
    "setting": ["read", "write"],
    "user": ["create", "delete", "read", "write"],
    "workflow": ["create", "delete", "read", "run", "write"],
}


@pytest.fixture(autouse=True)
def _install_test_resource_actions() -> Generator[None, None, None]:
    """Install the test resource-actions registry for one test, then restore.

    Snapshots the process-global registry state, installs the test registry for
    the duration of the test, and restores the previous state on teardown so the
    stub never leaks into other tests running in the same process.
    """
    saved = (
        _resource_actions._registry,
        _resource_actions._all_pairs,
        _resource_actions._project_eligible,
    )
    _set_registry(
        _TEST_RESOURCE_ACTIONS,
        project_eligible=frozenset({"workflow", "execution", "project"}),
    )
    try:
        yield
    finally:
        (
            _resource_actions._registry,
            _resource_actions._all_pairs,
            _resource_actions._project_eligible,
        ) = saved


@pytest.fixture
async def seeded_db(test_db_session: AsyncSession) -> AsyncSession:
    """Seed authz data and return the session."""
    await seed_authz_data(test_db_session)
    return test_db_session


@pytest.fixture
def mock_evaluator() -> AsyncMock:
    """Create a mock authz evaluator."""
    evaluator = AsyncMock()
    evaluator.evaluate = MagicMock(
        return_value={
            "allow": True,
            "deny": False,
            "matched_policy": "test-allow",
            "denial_reason": "",
            "denied_by": "",
            "allowed_projects": ["*"],
        }
    )
    return evaluator
