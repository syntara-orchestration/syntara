"""Red-green tests for WebSocket authentication, authorization, and connection limits.

These tests verify that WebSocket endpoints reject unauthenticated and unauthorized
connections and enforce connection limits. They are designed to FAIL against the
current unprotected code (RED) and PASS once the fix for AAP-79017 is implemented (GREEN).

The bug: endpoint_factory.py calls ``await websocket.accept()`` unconditionally —
no JWT validation, no authorization check, no connection-limit enforcement.

Run with:
    make -C backend test-integration PYTEST_ARGS="-xvs tests/integration/websocket/test_websocket_auth.py"
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from starlette.websockets import WebSocketDisconnect

from syntara.core.constants import WebSocketConfig
from syntara.core.models import User
from syntara.core.websocket.close_codes import POLICY_VIOLATION
from syntara.core.websocket.connection import get_connection_manager
from syntara.core.websocket.manager import get_connection_lifecycle_manager

if TYPE_CHECKING:
    from collections.abc import Generator

    from starlette.testclient import TestClient

pytestmark = pytest.mark.integration

EXECUTION_WS_PATH = "/ws/workflows/v1/executions"
INVOCATION_WS_PATH = "/ws/agent_orchestrator/v1/invocations"

TRY_AGAIN_LATER = 1013

_PATCH_AUTHN = "syntara.core.websocket.endpoint_factory._authenticate_websocket"
_PATCH_AUTHZ = "syntara.core.websocket.endpoint_factory._check_websocket_authorization"

_FAKE_USER = User(
    id=uuid4(),
    username="ws-test-user",
    email="ws-test@example.com",
    first_name="Test",
    is_enabled=True,
)


@pytest.fixture(autouse=True)
def _reset_connection_managers() -> Generator[None, None, None]:
    manager = get_connection_manager()
    manager.clear_all()
    lifecycle = get_connection_lifecycle_manager()
    lifecycle.clear_all()
    yield
    manager.clear_all()
    lifecycle.clear_all()


# ============================================================================
# Category A: Unauthenticated Connection Rejection
# ============================================================================


class TestUnauthenticatedConnectionRejection:
    """WebSocket endpoints must reject connections that carry no valid JWT."""

    def test_connection_without_token_is_rejected(self, sync_test_client: TestClient) -> None:
        """Connecting without a ?token= param must be closed with 1008 POLICY_VIOLATION."""
        execution_id = uuid4()
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            sync_test_client.websocket_connect(f"{EXECUTION_WS_PATH}/{execution_id}"),
        ):
            pytest.fail("Connection should have been rejected before accept")
        assert exc_info.value.code == POLICY_VIOLATION

    def test_connection_with_invalid_ticket_is_rejected(self, sync_test_client: TestClient) -> None:
        """Connecting with a garbage ?ticket= must be closed with 1008 POLICY_VIOLATION."""
        execution_id = uuid4()
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            sync_test_client.websocket_connect(f"{EXECUTION_WS_PATH}/{execution_id}?ticket=not-a-real-ticket"),
        ):
            pytest.fail("Connection should have been rejected before accept")
        assert exc_info.value.code == POLICY_VIOLATION

    def test_invocation_endpoint_without_token_is_rejected(self, sync_test_client: TestClient) -> None:
        """The invocations WS endpoint must also reject unauthenticated connections."""
        invocation_id = uuid4()
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            sync_test_client.websocket_connect(f"{INVOCATION_WS_PATH}/{invocation_id}"),
        ):
            pytest.fail("Connection should have been rejected before accept")
        assert exc_info.value.code == POLICY_VIOLATION


# ============================================================================
# Category B: Unauthorized Connection Rejection
# ============================================================================


class TestUnauthorizedConnectionRejection:
    """WebSocket endpoints must reject authenticated users who lack resource access."""

    def test_user_without_execution_read_access_is_rejected(
        self,
        sync_test_client: TestClient,
    ) -> None:
        """A valid JWT for a user without read access to the execution must be rejected."""
        execution_id = uuid4()

        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=_FAKE_USER)),
            patch(_PATCH_AUTHZ, AsyncMock(return_value=False)),
            pytest.raises(WebSocketDisconnect) as exc_info,
            sync_test_client.websocket_connect(f"{EXECUTION_WS_PATH}/{execution_id}?ticket=valid-but-unauthorized"),
        ):
            pytest.fail("Connection should have been rejected before accept")
        assert exc_info.value.code == POLICY_VIOLATION

    def test_authenticated_user_with_access_can_connect(
        self,
        sync_test_client: TestClient,
    ) -> None:
        """A valid JWT for a user who owns the resource must be accepted.

        This test is GREEN now (the endpoint accepts everyone) and stays GREEN
        after the fix — it acts as a regression guard ensuring legitimate users
        are not locked out.
        """
        execution_id = uuid4()
        with (
            patch(_PATCH_AUTHN, AsyncMock(return_value=_FAKE_USER)),
            patch(_PATCH_AUTHZ, AsyncMock(return_value=True)),
            sync_test_client.websocket_connect(f"{EXECUTION_WS_PATH}/{execution_id}?ticket=valid") as ws,
        ):
            first_event = ws.receive()
            assert first_event["type"] != "websocket.close" or first_event.get("code") != POLICY_VIOLATION


# ============================================================================
# Category C: Connection Limit Enforcement
# ============================================================================


class TestConnectionLimitEnforcement:
    """WebSocket endpoints must enforce MAX_CONNECTIONS and per-IP limits."""

    def test_max_connections_limit_enforced(
        self,
        sync_test_client: TestClient,
    ) -> None:
        """Once MAX_CONNECTIONS is reached, new connections get close code 1013."""
        execution_id = uuid4()
        manager = get_connection_manager()
        for i in range(WebSocketConfig.MAX_CONNECTIONS):
            manager.add_connection(f"fake-{i}", f"10.0.0.{i}:1234", "test")

        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            sync_test_client.websocket_connect(f"{EXECUTION_WS_PATH}/{execution_id}?ticket=valid"),
        ):
            pytest.fail("Connection should have been rejected — limit reached")
        assert exc_info.value.code == TRY_AGAIN_LATER

    def test_per_ip_connection_limit_enforced(
        self,
        sync_test_client: TestClient,
    ) -> None:
        """A single IP exceeding MAX_CONNECTIONS_PER_IP gets close code 1013."""
        execution_id = uuid4()
        manager = get_connection_manager()
        for i in range(WebSocketConfig.MAX_CONNECTIONS_PER_IP):
            manager.add_connection(f"fake-{i}", f"testclient:{50000 + i}", "test")

        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            sync_test_client.websocket_connect(f"{EXECUTION_WS_PATH}/{execution_id}?ticket=valid"),
        ):
            pytest.fail("Connection should have been rejected — limit reached")
        assert exc_info.value.code == TRY_AGAIN_LATER
