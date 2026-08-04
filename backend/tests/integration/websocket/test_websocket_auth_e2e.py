"""E2E tests for WebSocket authentication and authorization.

These tests exercise the authz chain with patched ticket authentication,
live in-process regopy evaluation, and DB-backed resource lookup.

Unlike ``test_websocket_auth.py`` (which patches individual guards), these
tests prove role allow/deny through the real evaluator against seeded
resources. Missing-resource fail-closed is covered separately in
``test_websocket_project_scoped_auth.py``.

Requires:
    - Live test database (integration test infrastructure)

Run with:
    make -C backend test-integration \
        PYTEST_ARGS="-xvs tests/integration/websocket/test_websocket_auth_e2e.py"
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession as _AsyncSession
from starlette.websockets import WebSocketDisconnect

from nexus.auth.services.global_revocation import clear_global_revocation_cache
from nexus.authz.evaluator import RegoEvaluator
from nexus.authz.models import RoleAssignment
from nexus.authz.seed import seed_authz_data
from nexus.core.models.group import Group, user_groups
from nexus.core.websocket.close_codes import POLICY_VIOLATION
from nexus.core.websocket.connection import get_connection_manager
from nexus.core.websocket.manager import get_connection_lifecycle_manager
from tests.integration.helpers.execution import create_test_execution
from tests.integration.helpers.invocations import create_test_invocation

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable, Generator, Mapping

    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncEngine
    from sqlmodel.ext.asyncio.session import AsyncSession
    from starlette.testclient import TestClient

    from nexus.agent_orchestrator.models.invocation import Invocation
    from nexus.core.models import User
    from nexus.workflows.models.execution import Execution

EXECUTION_WS_PATH = "/ws/workflows/v1/executions"
INVOCATION_WS_PATH = "/ws/agent_orchestrator/v1/invocations"

pytestmark = [pytest.mark.integration]

_PATCH_AUTHN = "nexus.core.websocket.endpoint_factory._authenticate_websocket"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_ws_accepted(first_event: Mapping[str, Any]) -> None:
    """Require the connection to stay open — any close fails the allow path."""
    assert first_event["type"] != "websocket.close", (
        f"expected accepted WebSocket, got close code={first_event.get('code')}"
    )


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_connection_managers() -> Generator[None, None, None]:
    """Clear connection/lifecycle managers and ticket client before and after each test."""
    import nexus.core.websocket.ticket as ticket_mod

    manager = get_connection_manager()
    manager.clear_all()
    lifecycle = get_connection_lifecycle_manager()
    lifecycle.clear_all()
    ticket_mod._client = None
    yield
    manager.clear_all()
    lifecycle.clear_all()
    ticket_mod._client = None


@pytest.fixture(autouse=True)
def _clear_revocation_cache() -> Generator[None, None, None]:
    """Clear the global revocation TTL cache around each test."""
    clear_global_revocation_cache()
    yield
    clear_global_revocation_cache()


@pytest_asyncio.fixture(autouse=True)
async def _seed_authz_for_ws(test_db_session: AsyncSession) -> None:
    """Seed built-in policies, roles, and groups for authorization."""
    await seed_authz_data(test_db_session)


@pytest_asyncio.fixture(autouse=True)
async def authz_evaluate_spy(session_app: FastAPI) -> AsyncGenerator[MagicMock, None]:
    """Replace session_app's mock evaluator with a live RegoEvaluator.

    The WebSocket authz path reads ``websocket.app.state.authz_evaluator``
    directly (not via FastAPI ``Depends``). Yields a ``MagicMock`` spy around
    ``evaluate`` so tests can assert the live evaluator ran.
    """
    previous = session_app.state.authz_evaluator
    evaluator = RegoEvaluator()
    evaluator.start()
    assert await evaluator.health() is True
    session_app.state.authz_evaluator = evaluator
    # Patch after health() so the spy starts at zero calls for each test.
    with patch.object(evaluator, "evaluate", wraps=evaluator.evaluate) as spy:
        try:
            yield spy
        finally:
            session_app.state.authz_evaluator = previous
            await evaluator.stop()


@pytest.fixture(autouse=True)
def _patch_endpoint_factory_db(test_db_engine: AsyncEngine) -> Generator[None, None, None]:
    """Point endpoint_factory's AsyncSessionLocal at the test database.

    ``endpoint_factory.py`` imports ``AsyncSessionLocal`` at module level.
    The ``sync_test_client`` patches ``nexus.core.database.session`` but that
    doesn't update the already-bound reference in ``endpoint_factory``.
    """
    factory = async_sessionmaker(test_db_engine, class_=_AsyncSession, expire_on_commit=False)
    with patch("nexus.core.websocket.endpoint_factory.AsyncSessionLocal", factory):
        yield


@pytest_asyncio.fixture
async def ws_admin_user(
    user_factory: Callable[..., Awaitable[User]],
    test_db_session: AsyncSession,
) -> User:
    """User with the ``admin`` role (has execution:read, invocation:read)."""
    user = await user_factory(username="ws-admin", email="ws-admin@example.com")
    await _make_role_assignment(test_db_session, user, "admin")
    return user


@pytest_asyncio.fixture
async def ws_auditor_user(
    user_factory: Callable[..., Awaitable[User]],
    test_db_session: AsyncSession,
) -> User:
    """User with the ``auditor`` role (has execution:read, NOT invocation:read)."""
    user = await user_factory(username="ws-auditor", email="ws-auditor@example.com")
    await _make_role_assignment(test_db_session, user, "auditor")
    return user


@pytest_asyncio.fixture
async def ws_user_role_user(
    user_factory: Callable[..., Awaitable[User]],
    test_db_session: AsyncSession,
) -> User:
    """User with the ``user`` role (no execution:read or invocation:read)."""
    user = await user_factory(username="ws-userrole", email="ws-userrole@example.com")
    await _make_role_assignment(test_db_session, user, "user")
    return user


@pytest_asyncio.fixture
async def ws_unprivileged_user(
    user_factory: Callable[..., Awaitable[User]],
) -> User:
    """User in the ``authenticated`` group only — no role beyond default."""
    return await user_factory(username="ws-unpriv", email="ws-unpriv@example.com")


@pytest_asyncio.fixture
async def ws_seeded_execution(
    test_db_session: AsyncSession,
    test_project_id: UUID,
    ws_admin_user: User,
) -> Execution:
    """Persisted execution so authz resolves project instead of fail-closing."""
    return await create_test_execution(test_db_session, ws_admin_user, test_project_id)


@pytest_asyncio.fixture
async def ws_seeded_invocation(
    test_db_session: AsyncSession,
    test_project_id: UUID,
    ws_admin_user: User,
) -> Invocation:
    """Persisted invocation so authz resolves project instead of fail-closing."""
    return await create_test_invocation(
        test_db_session,
        project_id=test_project_id,
        created_by=ws_admin_user.id,
    )


# ===========================================================================
# Authorization E2E Tests
# ===========================================================================


class TestWebSocketAuthorizationE2E:
    """Verify minimum required authz permissions for WebSocket endpoints.

    Authentication is patched to return the test user directly (bypassing
    the Redis-backed ticket exchange which has event-loop conflicts inside
    ``sync_test_client``).  The regopy authorization chain runs unpatched
    against seeded resources, so these tests prove role allow/deny — not
    missing-row fail-closed.
    """

    def test_admin_can_read_executions(
        self,
        sync_test_client: TestClient,
        authz_evaluate_spy: MagicMock,
        ws_admin_user: User,
        ws_seeded_execution: Execution,
    ) -> None:
        """Admin role grants execution:read:any — connection accepted."""
        authz_evaluate_spy.reset_mock()
        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=ws_admin_user)),
            sync_test_client.websocket_connect(f"{EXECUTION_WS_PATH}/{ws_seeded_execution.id}?ticket=e2e") as ws,
        ):
            _assert_ws_accepted(ws.receive())
        assert authz_evaluate_spy.call_count >= 1

    def test_auditor_can_read_executions(
        self,
        sync_test_client: TestClient,
        authz_evaluate_spy: MagicMock,
        ws_auditor_user: User,
        ws_seeded_execution: Execution,
    ) -> None:
        """Auditor role grants execution:read:any — connection accepted."""
        authz_evaluate_spy.reset_mock()
        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=ws_auditor_user)),
            sync_test_client.websocket_connect(f"{EXECUTION_WS_PATH}/{ws_seeded_execution.id}?ticket=e2e") as ws,
        ):
            _assert_ws_accepted(ws.receive())
        assert authz_evaluate_spy.call_count >= 1

    def test_admin_can_read_invocations(
        self,
        sync_test_client: TestClient,
        authz_evaluate_spy: MagicMock,
        ws_admin_user: User,
        ws_seeded_invocation: Invocation,
    ) -> None:
        """Admin role grants invocation:read:any — connection accepted."""
        authz_evaluate_spy.reset_mock()
        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=ws_admin_user)),
            sync_test_client.websocket_connect(f"{INVOCATION_WS_PATH}/{ws_seeded_invocation.id}?ticket=e2e") as ws,
        ):
            _assert_ws_accepted(ws.receive())
        assert authz_evaluate_spy.call_count >= 1

    def test_auditor_cannot_read_invocations(
        self,
        sync_test_client: TestClient,
        authz_evaluate_spy: MagicMock,
        ws_auditor_user: User,
        ws_seeded_invocation: Invocation,
    ) -> None:
        """Auditor role has no invocation:read — rejected with 1008."""
        authz_evaluate_spy.reset_mock()
        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=ws_auditor_user)),
            pytest.raises(WebSocketDisconnect) as exc_info,
            sync_test_client.websocket_connect(f"{INVOCATION_WS_PATH}/{ws_seeded_invocation.id}?ticket=e2e"),
        ):
            pytest.fail("Connection should have been rejected — no invocation:read for auditor")
        assert exc_info.value.code == POLICY_VIOLATION
        assert authz_evaluate_spy.call_count >= 1

    def test_unprivileged_user_cannot_read_executions(
        self,
        sync_test_client: TestClient,
        authz_evaluate_spy: MagicMock,
        ws_unprivileged_user: User,
        ws_seeded_execution: Execution,
    ) -> None:
        """Authenticated-only user has no execution:read — rejected with 1008."""
        authz_evaluate_spy.reset_mock()
        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=ws_unprivileged_user)),
            pytest.raises(WebSocketDisconnect) as exc_info,
            sync_test_client.websocket_connect(f"{EXECUTION_WS_PATH}/{ws_seeded_execution.id}?ticket=e2e"),
        ):
            pytest.fail("Connection should have been rejected — no execution:read for authenticated")
        assert exc_info.value.code == POLICY_VIOLATION
        assert authz_evaluate_spy.call_count >= 1

    def test_user_role_cannot_read_executions(
        self,
        sync_test_client: TestClient,
        authz_evaluate_spy: MagicMock,
        ws_user_role_user: User,
        ws_seeded_execution: Execution,
    ) -> None:
        """User role has no execution:read — rejected with 1008."""
        authz_evaluate_spy.reset_mock()
        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=ws_user_role_user)),
            pytest.raises(WebSocketDisconnect) as exc_info,
            sync_test_client.websocket_connect(f"{EXECUTION_WS_PATH}/{ws_seeded_execution.id}?ticket=e2e"),
        ):
            pytest.fail("Connection should have been rejected — no execution:read for user role")
        assert exc_info.value.code == POLICY_VIOLATION
        assert authz_evaluate_spy.call_count >= 1


# ===========================================================================
# Global Revocation E2E Tests
# ===========================================================================


# NOTE: Global revocation E2E tests were removed from this file.
# With ticket-based auth, global revocation is enforced at ticket issuance
# time (POST /auth/ws-ticket) via the standard auth middleware, which has
# its own comprehensive test suite. Testing the middleware's revocation
# check here is redundant and causes pytest-asyncio/sync_test_client
# event-loop conflicts (sync HTTP calls within async DB fixture context).
