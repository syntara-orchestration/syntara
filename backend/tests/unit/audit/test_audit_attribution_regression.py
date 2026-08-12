"""Regression tests for audit actor attribution.

These tests verify that authenticated requests retain actor identity in
audit events.  Verified actor context is set by the auth layer
(``StaleTokenMiddleware`` and FastAPI auth dependencies) after
cryptographic JWT verification, then propagated to ``AuditMiddleware``
via ``scope["state"][VERIFIED_ACTOR_STATE_KEY]``.

The downstream apps in these tests simulate the auth layer by decoding
the JWT from the Authorization header and writing verified identity to
scope state — mirroring what ``_set_verified_actor_context_from_payload``
does in production.

If these tests fail, audit logs lose user attribution — every action
appears anonymous, breaking compliance and forensics.
"""

from collections.abc import MutableMapping
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import jwt
import pytest
from fastapi import FastAPI

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.emitter import (
    VERIFIED_ACTOR_STATE_KEY,
    AuditActorContext,
    actor_context_var,
)
from syntara.audit.events.http_request import HTTPRequestEvent, HTTPRequestHandler
from syntara.audit.middleware import AuditMiddleware
from syntara.audit.models.audit_event import AuditEvent
from syntara.audit.utils import sanitize_actor_username
from syntara.core.auth.jwt_utils import extract_actor_claims
from syntara.core.models.principal import PrincipalType

_EMIT_PATCH = "syntara.audit.emitter._do_emit_audit_event"

_TEST_JWT_KEY = "test-secret"


# ---- helpers ----------------------------------------------------------------


def _sign_jwt(claims: dict[str, Any]) -> str:
    """Create a properly signed JWT (simulating what the auth service issues)."""
    return jwt.encode(claims, key=_TEST_JWT_KEY, algorithm="HS256")


def _actor_from_claims(claims: dict[str, Any]) -> AuditActorContext:
    """Build an AuditActorContext from JWT claims (mirrors auth dependency logic)."""
    actor_claims = extract_actor_claims(claims)
    actor_type = PrincipalType.SERVICE_ACCOUNT if claims.get("token_type") == "service_account" else PrincipalType.USER
    return AuditActorContext(
        actor_id=actor_claims.actor_id,
        actor_username=sanitize_actor_username(actor_claims.actor_username),
        actor_type=actor_type,
    )


def _decode_bearer_from_scope(scope: MutableMapping[str, Any]) -> dict[str, Any] | None:
    """Extract and decode the Bearer JWT from ASGI scope headers."""
    for header_name, header_value in scope.get("headers", []):
        if header_name.lower() == b"authorization":
            parts = header_value.decode("latin-1").split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return jwt.decode(parts[1], key=_TEST_JWT_KEY, algorithms=["HS256"])
    return None


def _make_scope(
    path: str = "/api/v1/workflows",
    method: str = "GET",
    auth_token: str | None = None,
) -> dict[str, Any]:
    headers: list[tuple[bytes, bytes]] = []
    if auth_token:
        headers.append((b"authorization", f"Bearer {auth_token}".encode("latin-1")))
    return {
        "type": "http",
        "path": path,
        "method": method,
        "query_string": b"",
        "headers": headers,
    }


def _make_authenticated_app(status_code: int = 200) -> Any:  # noqa: ANN401
    """Downstream ASGI app that simulates verified auth setting actor context.

    In production, ``StaleTokenMiddleware`` and FastAPI auth dependencies
    perform a verified JWT decode and call
    ``_set_verified_actor_context_from_payload``, which writes to both
    ``actor_context_var`` and ``scope["state"][VERIFIED_ACTOR_STATE_KEY]``.
    This helper mirrors that behavior for unit tests.
    """

    async def app(
        scope: MutableMapping[str, Any],
        receive: Any,  # noqa: ANN401
        send: Any,  # noqa: ANN401
    ) -> None:
        claims = _decode_bearer_from_scope(scope)
        if claims:
            actor = _actor_from_claims(claims)
            actor_context_var.set(actor)
            scope.setdefault("state", {})[VERIFIED_ACTOR_STATE_KEY] = actor
        await send({"type": "http.response.start", "status": status_code, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    return app


def _make_failed_auth_app() -> Any:  # noqa: ANN401
    """Downstream app where auth verified the JWT but rejected the request.

    Simulates a revoked/expired token: ``decode_token()`` succeeded (so
    actor context is set), but a subsequent check (revocation, staleness)
    returned 401.
    """

    async def app(
        scope: MutableMapping[str, Any],
        receive: Any,  # noqa: ANN401
        send: Any,  # noqa: ANN401
    ) -> None:
        claims = _decode_bearer_from_scope(scope)
        if claims:
            actor = _actor_from_claims(claims)
            actor_context_var.set(actor)
            scope.setdefault("state", {})[VERIFIED_ACTOR_STATE_KEY] = actor
        await send({"type": "http.response.start", "status": 401, "headers": []})
        await send({"type": "http.response.body", "body": b"Unauthorized"})

    return app


def _make_fastapi_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/workflows")
    async def list_workflows() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _get_audit_events(mock_emit: MagicMock, event_action: str) -> list[AuditEvent]:
    return [call[0][0] for call in mock_emit.call_args_list if call[0][0].event_action == event_action]


# =============================================================================
# Regression 1: Authenticated requests must have actor in audit
# =============================================================================


class TestAuditAttributionAuthenticated:
    """Authenticated requests must retain actor identity in audit events.

    In production, the auth layer (StaleTokenMiddleware + FastAPI auth
    dependencies) verifies the JWT and sets ``actor_context_var`` and
    ``scope["state"][VERIFIED_ACTOR_STATE_KEY]``.  The audit middleware
    reads verified identity from scope state in its ``finally`` block.
    """

    def setup_method(self) -> None:
        AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})

    @pytest.mark.asyncio
    async def test_authenticated_request_has_actor_in_audit(self) -> None:
        """request_completed event for authenticated request must have actor identity."""
        user_id = str(uuid4())
        username = "real-authenticated-user"
        claims = {"sub": user_id, "preferred_username": username}
        token = _sign_jwt(claims)

        downstream = _make_authenticated_app(status_code=200)
        middleware = AuditMiddleware(downstream, _make_fastapi_app())
        scope = _make_scope(auth_token=token)

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert str(events[0].actor_id) == user_id, (
            "Authenticated request has no actor_id in audit — all actions appear anonymous, compliance broken"
        )
        assert events[0].actor_username == username, "Authenticated request has no actor_username in audit"

    @pytest.mark.asyncio
    async def test_service_account_token_has_actor_type(self) -> None:
        """Service account JWT must produce SERVICE_ACCOUNT actor_type in audit."""
        user_id = str(uuid4())
        claims = {
            "sub": user_id,
            "preferred_username": "my-service-account",
            "token_type": "service_account",
        }
        token = _sign_jwt(claims)

        downstream = _make_authenticated_app(status_code=200)
        middleware = AuditMiddleware(downstream, _make_fastapi_app())
        scope = _make_scope(auth_token=token)

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].actor_type == "service_account", "Service account lost actor_type attribution in audit"

    @pytest.mark.asyncio
    async def test_actor_context_var_populated_during_request(self) -> None:
        """actor_context_var must be set during request processing.

        Business-level audit events emitted by @audit decorator and
        emit_audit_event() read from this context var. If empty,
        all business audit events lose actor attribution.
        """
        user_id = str(uuid4())
        username = "context-var-user"
        claims = {"sub": user_id, "preferred_username": username}
        token = _sign_jwt(claims)

        captured_context: list[AuditActorContext | None] = []

        async def capture_app(
            scope: MutableMapping[str, Any],
            receive: Any,  # noqa: ANN401
            send: Any,  # noqa: ANN401
        ) -> None:
            # Simulate auth layer setting context, then capture it
            jwt_claims = _decode_bearer_from_scope(scope)
            if jwt_claims:
                actor = _actor_from_claims(jwt_claims)
                actor_context_var.set(actor)
                scope.setdefault("state", {})[VERIFIED_ACTOR_STATE_KEY] = actor
            captured_context.append(actor_context_var.get())
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = AuditMiddleware(capture_app, _make_fastapi_app())
        scope = _make_scope(auth_token=token)

        with patch(_EMIT_PATCH):
            await middleware(scope, AsyncMock(), AsyncMock())

        assert len(captured_context) == 1
        ctx = captured_context[0]
        assert ctx is not None
        assert ctx.actor_id is not None, (
            "actor_context_var empty during request processing — "
            "business audit events and DB triggers lose actor attribution"
        )
        assert str(ctx.actor_id) == user_id
        assert ctx.actor_username == username


# =============================================================================
# Regression 2: Failed auth should still show who attempted
# =============================================================================


class TestAuditAttributionFailedAuth:
    """Failed authentication should record attempted identity.

    When ``decode_token()`` succeeds but a subsequent check fails
    (revocation, staleness, disabled principal), the actor context is
    already set from the verified decode.  The 401 audit event retains
    the verified identity for security monitoring (brute-force detection,
    token reuse alerts).
    """

    def setup_method(self) -> None:
        AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})

    @pytest.mark.asyncio
    async def test_failed_auth_shows_attempted_identity(self) -> None:
        """401 response should show who attempted authentication.

        Security teams need this for detecting brute-force attacks,
        stolen token reuse, and enumeration attempts.
        """
        user_id = str(uuid4())
        claims = {"sub": user_id, "preferred_username": "attacker-or-user"}
        token = _sign_jwt(claims)

        downstream = _make_failed_auth_app()
        middleware = AuditMiddleware(downstream, _make_fastapi_app())
        scope = _make_scope(auth_token=token)

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].actor_username == "attacker-or-user", (
            "Failed auth has no actor attribution — security monitoring "
            "cannot detect who is attempting unauthorized access"
        )


# =============================================================================
# Regression 3: Exception path preserves actor
# =============================================================================


class TestAuditAttributionExceptionPath:
    """Actor context must survive exceptions in downstream processing."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})

    @pytest.mark.asyncio
    async def test_exception_preserves_actor_from_jwt(self) -> None:
        """When downstream raises, request_completed (status 500) still has actor."""
        user_id = str(uuid4())
        claims = {"sub": user_id, "preferred_username": "crash-user"}
        token = _sign_jwt(claims)

        async def crashing_app(
            scope: MutableMapping[str, Any],
            receive: Any,  # noqa: ANN401
            send: Any,  # noqa: ANN401
        ) -> None:
            jwt_claims = _decode_bearer_from_scope(scope)
            if jwt_claims:
                actor = _actor_from_claims(jwt_claims)
                actor_context_var.set(actor)
                scope.setdefault("state", {})[VERIFIED_ACTOR_STATE_KEY] = actor
            msg = "boom"
            raise RuntimeError(msg)

        middleware = AuditMiddleware(crashing_app, _make_fastapi_app())
        scope = _make_scope(auth_token=token)
        receive = AsyncMock()
        send = AsyncMock()

        with patch(_EMIT_PATCH) as mock_emit:
            with pytest.raises(RuntimeError, match="boom"):
                await middleware(scope, receive, send)

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert str(events[0].actor_id) == user_id, "Actor lost on exception path — 500 errors appear anonymous"
        assert events[0].actor_username == "crash-user"
