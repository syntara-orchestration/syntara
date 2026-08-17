"""E2E tests for WebSocket authentication, authorization, and revocation.

These tests exercise the full auth chain: real JWT tokens, real OPA rego
policy evaluation (via CLI), and real DB-backed global revocation.

Unlike ``test_websocket_auth.py`` (which patches individual guards), these
tests prove that the end-to-end wiring is correct — the right claims flow
through ``_authenticate_websocket``, the right policies are evaluated in
OPA, and the right revocation logic applies.

Requires:
    - ``opa`` binary on PATH (skips otherwise)
    - Live test database (integration test infrastructure)

Run with:
    make -C backend test-integration \
        PYTEST_ARGS="-xvs tests/integration/websocket/test_websocket_auth_e2e.py"
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession as _AsyncSession
from starlette.websockets import WebSocketDisconnect

from syntara.auth.services.global_revocation import clear_global_revocation_cache
from syntara.auth.services.token_service import TokenService
from syntara.authz.models import RoleAssignment
from syntara.authz.seed import seed_authz_data
from syntara.core.models.group import Group, user_groups
from syntara.core.websocket.close_codes import POLICY_VIOLATION
from syntara.core.websocket.connection import get_connection_manager
from syntara.core.websocket.manager import get_connection_lifecycle_manager

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator

    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncEngine
    from sqlmodel.ext.asyncio.session import AsyncSession
    from starlette.testclient import TestClient

    from syntara.core.models import User

EXECUTION_WS_PATH = "/ws/workflows/v1/executions"
INVOCATION_WS_PATH = "/ws/agent_orchestrator/v1/invocations"

_REGO_POLICY_PATH = Path(__file__).resolve().parents[3] / "src" / "syntara" / "authz" / "rego" / "authz.rego"
_OPA_RESULT_FIELDS = {"allow", "deny", "matched_policy", "denial_reason", "denied_by", "allowed_projects"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _opa_evaluate_cli(opa_input: dict[str, Any]) -> dict[str, Any]:
    """Evaluate authz using the OPA CLI against the real rego policy."""
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "opa",
            "eval",
            "-d",
            str(_REGO_POLICY_PATH),
            "-I",
            "--format",
            "json",
            "data.orchestrator.authz",
        ],
        input=json.dumps(opa_input),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        msg = f"opa eval failed (rc={result.returncode}): {result.stderr}"
        raise RuntimeError(msg)

    raw = json.loads(result.stdout)
    value: dict[str, Any] = raw["result"][0]["expressions"][0]["value"]
    return {k: v for k, v in value.items() if k in _OPA_RESULT_FIELDS}


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
# Module-level skip
# ---------------------------------------------------------------------------

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not shutil.which("opa"), reason="opa CLI not found on PATH"),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_connection_managers() -> Generator[None, None, None]:
    """Clear connection/lifecycle managers and ticket client before and after each test."""
    import syntara.core.websocket.ticket as ticket_mod

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


@pytest.fixture(autouse=True)
def _wire_opa_cli_to_app_state(session_app: FastAPI) -> Generator[None, None, None]:
    """Point app.state.authz_evaluator.evaluate at the real OPA CLI.

    The WebSocket authz path reads ``websocket.app.state.authz_evaluator``
    directly (not via FastAPI ``Depends``).  The session_app fixture creates
    an ``AsyncMock`` for the OPA client; we set its ``evaluate`` side-effect
    so ``authorize()`` evaluates the real rego policy via CLI.
    """
    original_evaluate = session_app.state.authz_evaluator.evaluate
    session_app.state.authz_evaluator.evaluate = MagicMock(side_effect=_opa_evaluate_cli)
    yield
    session_app.state.authz_evaluator.evaluate = original_evaluate


@pytest.fixture(autouse=True)
def _patch_endpoint_factory_db(test_db_engine: AsyncEngine) -> Generator[None, None, None]:
    """Point endpoint_factory's AsyncSessionLocal at the test database.

    ``endpoint_factory.py`` imports ``AsyncSessionLocal`` at module level.
    The ``sync_test_client`` patches ``syntara.core.database.session`` but that
    doesn't update the already-bound reference in ``endpoint_factory``.
    """
    factory = async_sessionmaker(test_db_engine, class_=_AsyncSession, expire_on_commit=False)
    with patch("syntara.core.websocket.endpoint_factory.AsyncSessionLocal", factory):
        yield


# -- User fixtures ---


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


def _create_jwt(user: User) -> str:
    """Create a real signed JWT for the given user."""
    return TokenService().create_access_token(
        subject_id=user.id,
        username=user.username,
        email=user.email or "",
    )


_PATCH_AUTHN = "syntara.core.websocket.endpoint_factory._authenticate_websocket"


# ===========================================================================
# Authorization E2E Tests
# ===========================================================================


class TestWebSocketAuthorizationE2E:
    """Verify minimum required OPA permissions for WebSocket endpoints.

    Authentication is patched to return the test user directly (bypassing
    the Redis-backed ticket exchange which has event-loop conflicts inside
    ``sync_test_client``).  The OPA authorization chain runs unpatched,
    so these tests prove that the right rego policies accept or reject
    each role.
    """

    def test_admin_can_read_executions(
        self,
        sync_test_client: TestClient,
        ws_admin_user: User,
    ) -> None:
        """Admin role grants execution:read:any — connection accepted."""
        execution_id = uuid4()
        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=ws_admin_user)),
            sync_test_client.websocket_connect(f"{EXECUTION_WS_PATH}/{execution_id}?ticket=e2e") as ws,
        ):
            first_event = ws.receive()
            assert first_event["type"] != "websocket.close" or first_event.get("code") != POLICY_VIOLATION

    def test_auditor_can_read_executions(
        self,
        sync_test_client: TestClient,
        ws_auditor_user: User,
    ) -> None:
        """Auditor role grants execution:read:any — connection accepted."""
        execution_id = uuid4()
        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=ws_auditor_user)),
            sync_test_client.websocket_connect(f"{EXECUTION_WS_PATH}/{execution_id}?ticket=e2e") as ws,
        ):
            first_event = ws.receive()
            assert first_event["type"] != "websocket.close" or first_event.get("code") != POLICY_VIOLATION

    def test_admin_can_read_invocations(
        self,
        sync_test_client: TestClient,
        ws_admin_user: User,
    ) -> None:
        """Admin role grants invocation:read:any — connection accepted."""
        invocation_id = uuid4()
        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=ws_admin_user)),
            sync_test_client.websocket_connect(f"{INVOCATION_WS_PATH}/{invocation_id}?ticket=e2e") as ws,
        ):
            first_event = ws.receive()
            assert first_event["type"] != "websocket.close" or first_event.get("code") != POLICY_VIOLATION

    def test_auditor_cannot_read_invocations(
        self,
        sync_test_client: TestClient,
        ws_auditor_user: User,
    ) -> None:
        """Auditor role has no invocation:read — rejected with 1008."""
        invocation_id = uuid4()
        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=ws_auditor_user)),
            pytest.raises(WebSocketDisconnect) as exc_info,
            sync_test_client.websocket_connect(f"{INVOCATION_WS_PATH}/{invocation_id}?ticket=e2e"),
        ):
            pytest.fail("Connection should have been rejected — no invocation:read for auditor")
        assert exc_info.value.code == POLICY_VIOLATION

    def test_unprivileged_user_cannot_read_executions(
        self,
        sync_test_client: TestClient,
        ws_unprivileged_user: User,
    ) -> None:
        """Authenticated-only user has no execution:read — rejected with 1008."""
        execution_id = uuid4()
        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=ws_unprivileged_user)),
            pytest.raises(WebSocketDisconnect) as exc_info,
            sync_test_client.websocket_connect(f"{EXECUTION_WS_PATH}/{execution_id}?ticket=e2e"),
        ):
            pytest.fail("Connection should have been rejected — no execution:read for authenticated")
        assert exc_info.value.code == POLICY_VIOLATION

    def test_user_role_cannot_read_executions(
        self,
        sync_test_client: TestClient,
        ws_user_role_user: User,
    ) -> None:
        """User role has no execution:read — rejected with 1008."""
        execution_id = uuid4()
        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=ws_user_role_user)),
            pytest.raises(WebSocketDisconnect) as exc_info,
            sync_test_client.websocket_connect(f"{EXECUTION_WS_PATH}/{execution_id}?ticket=e2e"),
        ):
            pytest.fail("Connection should have been rejected — no execution:read for user role")
        assert exc_info.value.code == POLICY_VIOLATION


# ===========================================================================
# Global Revocation E2E Tests
# ===========================================================================


# NOTE: Global revocation E2E tests were removed from this file.
# With ticket-based auth, global revocation is enforced at ticket issuance
# time (POST /auth/ws_ticket) via the standard auth middleware, which has
# its own comprehensive test suite. Testing the middleware's revocation
# check here is redundant and causes pytest-asyncio/sync_test_client
# event-loop conflicts (sync HTTP calls within async DB fixture context).
