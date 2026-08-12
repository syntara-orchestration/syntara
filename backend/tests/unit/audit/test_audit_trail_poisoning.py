"""Reproducer tests for AAP-83648: audit trail poisoning via unverified JWT claims.

AuditMiddleware decodes JWT with verify_signature=False, trusting attacker-
controlled claims (sub, preferred_username, token_type) for audit actor
identity.  Three escalating attack surfaces:

1. Any request — request_completed emitted in finally block before auth
2. Cookie-auth endpoints — auth via cookie, audit reads forged Authorization header
3. Anonymous webhooks — no auth required, forged header poisons all audit layers

These tests prove the vulnerability exists (should FAIL before fix, PASS after).
"""

from collections.abc import MutableMapping
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import jwt
import pytest
from fastapi import FastAPI

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.emitter import AuditActorContext, actor_context_var
from syntara.audit.events.http_request import HTTPRequestEvent, HTTPRequestHandler
from syntara.audit.middleware import AuditMiddleware
from syntara.audit.models.audit_event import AuditEvent
from syntara.audit.models.structured_data import AuditContextData

_EMIT_PATCH = "syntara.audit.emitter._do_emit_audit_event"


# ---- helpers ----------------------------------------------------------------

FORGED_USER_ID = str(uuid4())
FORGED_USERNAME = "admin-victim"
VICTIM_TOKEN_TYPE = "service_account"  # noqa: S105


def _forge_alg_none_jwt(
    sub: str = FORGED_USER_ID,
    preferred_username: str = FORGED_USERNAME,
    token_type: str | None = None,
) -> str:
    """Create an alg:none JWT with forged claims — no credentials needed."""
    claims: dict[str, Any] = {"sub": sub, "preferred_username": preferred_username}
    if token_type is not None:
        claims["token_type"] = token_type
    return jwt.encode(claims, key="", algorithm="none")


def _make_scope(
    path: str = "/api/v1/workflows",
    method: str = "GET",
    headers: list[tuple[bytes, bytes]] | None = None,
    auth_token: str | None = None,
) -> dict[str, Any]:
    scope_headers = list(headers) if headers else []
    if auth_token:
        scope_headers.append((b"authorization", f"Bearer {auth_token}".encode("latin-1")))
    return {
        "type": "http",
        "path": path,
        "method": method,
        "query_string": b"",
        "headers": scope_headers,
    }


def _make_app(status_code: int = 200) -> Any:  # noqa: ANN401
    async def app(
        scope: MutableMapping[str, Any],
        receive: Any,  # noqa: ANN401
        send: Any,  # noqa: ANN401
    ) -> None:
        await send({"type": "http.response.start", "status": status_code, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    return app


def _make_401_app() -> Any:  # noqa: ANN401
    """Simulate downstream auth rejecting the request with 401."""

    async def app(
        scope: MutableMapping[str, Any],
        receive: Any,  # noqa: ANN401
        send: Any,  # noqa: ANN401
    ) -> None:
        await send({"type": "http.response.start", "status": 401, "headers": []})
        await send({"type": "http.response.body", "body": b"Unauthorized"})

    return app


def _make_fastapi_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/workflows")
    async def list_workflows() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/auth/refresh")
    async def refresh_token() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/webhooks/{path:path}")
    async def receive_webhook(path: str) -> dict[str, str]:
        return {"accepted": "true"}

    return app


def _get_audit_events(mock_emit: MagicMock, event_action: str) -> list[AuditEvent]:
    return [call[0][0] for call in mock_emit.call_args_list if call[0][0].event_action == event_action]


# =============================================================================
# Attack Vector 1: Any request — forged JWT poisons audit before auth runs
# =============================================================================


class TestAuditTrailPoisoningAnyRequest:
    """Vector 1: forged alg:none JWT on any request.

    Forged alg:none JWT causes audit event to record attacker-controlled
    identity, even when downstream auth rejects the request (401).
    The audit middleware emits request_completed in a finally block, so the
    poisoned identity is already written before real authentication runs.
    """

    def setup_method(self) -> None:
        AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})

    @pytest.mark.asyncio
    async def test_forged_jwt_actor_not_trusted_on_auth_failure(self) -> None:
        """Forged alg:none JWT must NOT populate audit actor on 401 response.

        Current bug: middleware decodes unverified JWT and writes forged
        sub/preferred_username to the audit event even when auth fails.
        """
        downstream = _make_401_app()
        middleware = AuditMiddleware(downstream, _make_fastapi_app())

        forged_token = _forge_alg_none_jwt()
        scope = _make_scope(path="/api/v1/workflows", auth_token=forged_token)

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        # Forged identity must NOT appear in audit event for failed auth
        assert events[0].actor_id is None, (
            f"Forged actor_id '{events[0].actor_id}' written to audit on 401 — "
            "attacker can attribute failed requests to arbitrary users"
        )
        assert events[0].actor_username is None, (
            f"Forged actor_username '{events[0].actor_username}' written to audit on 401"
        )

    @pytest.mark.asyncio
    async def test_forged_jwt_actor_not_trusted_on_success(self) -> None:
        """Even on 200, unverified JWT claims must NOT be used for actor identity.

        The middleware should only trust verified authentication, not raw JWT decode.
        """
        downstream = _make_app(status_code=200)
        middleware = AuditMiddleware(downstream, _make_fastapi_app())

        forged_token = _forge_alg_none_jwt()
        scope = _make_scope(path="/api/v1/workflows", auth_token=forged_token)

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].actor_id is None, f"Unverified JWT claim used as actor_id: '{events[0].actor_id}'"
        assert events[0].actor_username is None, (
            f"Unverified JWT claim used as actor_username: '{events[0].actor_username}'"
        )

    @pytest.mark.asyncio
    async def test_alg_none_jwt_with_empty_signature_accepted(self) -> None:
        """alg:none JWT with empty signature is decoded successfully.

        PyJWT 2.10.1 with verify_signature=False disables algorithms allowlist,
        so alg:none tokens bypass the algorithms=['ES256'] parameter.
        """
        forged_token = _forge_alg_none_jwt(
            sub=FORGED_USER_ID,
            preferred_username=FORGED_USERNAME,
            token_type="service_account",  # noqa: S106
        )
        downstream = _make_app(status_code=200)
        middleware = AuditMiddleware(downstream, _make_fastapi_app())

        scope = _make_scope(auth_token=forged_token)

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        # After fix: forged claims should not appear
        assert events[0].actor_type != "service_account", (
            "Forged token_type='service_account' promoted to actor_type — "
            "attacker can impersonate service accounts in audit trail"
        )

    @pytest.mark.asyncio
    async def test_forged_username_not_in_audit_event_structured_data(self) -> None:
        """Forged preferred_username must not leak into structured audit data."""
        downstream = _make_app(status_code=200)
        middleware = AuditMiddleware(downstream, _make_fastapi_app())

        forged_token = _forge_alg_none_jwt(
            preferred_username="ceo@company.com",
        )
        scope = _make_scope(auth_token=forged_token)

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].actor_username != "ceo@company.com", (
            "Forged preferred_username 'ceo@company.com' written to audit — attacker can impersonate any user"
        )


# =============================================================================
# Attack Vector 2: Cookie-auth endpoint — forged header overrides real identity
# =============================================================================


class TestAuditTrailPoisoningCookieAuth:
    """Vector 2: cookie-auth endpoint with forged Authorization header.

    POST /api/v1/auth/refresh authenticates via cookie but
    AuditMiddleware reads identity from the forged Authorization header.
    The middleware sets forged actor into actor_context_var BEFORE downstream
    auth runs. Any business-level audit event emitted during request
    processing uses the forged identity.
    """

    def setup_method(self) -> None:
        AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})

    @pytest.mark.asyncio
    async def test_forged_identity_visible_during_request_processing(self) -> None:
        """Forged JWT identity is in actor_context_var BEFORE auth runs.

        The middleware sets forged actor at line 347, then calls downstream.
        Any code that reads actor_context_var before auth dependency runs
        sees the forged identity. This is the timing window that enables
        business-level audit event poisoning.
        """
        captured_pre_auth: list[AuditActorContext | None] = []

        async def capture_before_auth(
            scope: MutableMapping[str, Any],
            receive: Any,  # noqa: ANN401
            send: Any,  # noqa: ANN401
        ) -> None:
            # Capture context var BEFORE auth would run
            # In real FastAPI, middleware runs before auth dependencies
            captured_pre_auth.append(actor_context_var.get())
            # Then auth would correct it...
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = AuditMiddleware(capture_before_auth, _make_fastapi_app())
        forged_token = _forge_alg_none_jwt(sub=FORGED_USER_ID, preferred_username=FORGED_USERNAME)
        scope = _make_scope(
            path="/api/v1/auth/refresh",
            method="POST",
            auth_token=forged_token,
            headers=[(b"cookie", b"refresh_token=valid-session-cookie")],
        )

        with patch(_EMIT_PATCH):
            await middleware(scope, AsyncMock(), AsyncMock())

        assert len(captured_pre_auth) == 1
        ctx = captured_pre_auth[0]
        # Bug: forged identity is accessible via context var during processing
        assert ctx is None or ctx.actor_id is None, (
            f"Forged actor_id '{ctx.actor_id if ctx else None}' visible in "
            "actor_context_var during request processing — any business audit "
            "event emitted before auth runs uses forged identity"
        )

    @pytest.mark.asyncio
    async def test_business_audit_event_emitted_with_forged_identity(self) -> None:
        """Business-level audit events must not inherit forged identity.

        emit_audit_event() injects actor from context var when event.actor_id
        is None. If middleware set forged actor, business events are poisoned.
        """
        from syntara.audit.emitter import emit_audit_event

        captured_events: list[AuditEvent] = []

        async def emit_during_processing(
            scope: MutableMapping[str, Any],
            receive: Any,  # noqa: ANN401
            send: Any,  # noqa: ANN401
        ) -> None:
            # Simulate a business audit event emitted during request processing
            # (before auth dependency would correct context var)
            from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus

            event = AuditEvent(
                event_category=EventCategory.SECURITY_EVENT,
                event_action="refresh_token",
                event_message="Token refreshed",
                event_status=EventStatus.SUCCESS,
                event_severity=EventSeverity.INFO,
                source_component="syntara.auth.router",
                structured_data=AuditContextData(data_type="session_lifecycle"),
            )
            # emit_audit_event will inject actor from context var
            emit_audit_event(event)
            captured_events.append(event)

            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = AuditMiddleware(emit_during_processing, _make_fastapi_app())
        forged_token = _forge_alg_none_jwt(sub=FORGED_USER_ID, preferred_username=FORGED_USERNAME)
        scope = _make_scope(
            path="/api/v1/auth/refresh",
            method="POST",
            auth_token=forged_token,
        )

        with patch(_EMIT_PATCH):
            await middleware(scope, AsyncMock(), AsyncMock())

        assert len(captured_events) == 1
        # The business event should NOT have forged actor identity
        assert captured_events[0].actor_id is None or str(captured_events[0].actor_id) != FORGED_USER_ID, (
            f"Business audit event 'refresh_token' has forged actor_id "
            f"'{captured_events[0].actor_id}' — cookie-auth action attributed "
            "to attacker-chosen victim"
        )
        assert captured_events[0].actor_username is None or captured_events[0].actor_username != FORGED_USERNAME, (
            f"Business audit event has forged actor_username '{captured_events[0].actor_username}'"
        )


# =============================================================================
# Attack Vector 3: Anonymous webhooks — forged header poisons all audit layers
# =============================================================================


class TestAuditTrailPoisoningWebhooks:
    """Vector 3: POST /api/v1/webhooks/{path} requires no auth.

    Forged Authorization header poisons:
    1. HTTP middleware audit events (request_completed)
    2. Business-level audit events (via actor_context_var propagation)
    3. PostgreSQL CRUD trigger events (via SET LOCAL app.actor_id)
    """

    def setup_method(self) -> None:
        AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})

    @pytest.mark.asyncio
    async def test_anonymous_webhook_forged_header_poisons_http_audit(self) -> None:
        """Anonymous webhook with forged JWT must NOT have forged actor in audit.

        Webhooks require no authentication. Attacker sends forged Authorization
        header → middleware extracts forged identity → audit event attributes
        the webhook to arbitrary user.
        """
        downstream = _make_app(status_code=202)
        middleware = AuditMiddleware(downstream, _make_fastapi_app())

        forged_token = _forge_alg_none_jwt(
            sub=FORGED_USER_ID,
            preferred_username=FORGED_USERNAME,
            token_type="service_account",  # noqa: S106
        )
        scope = _make_scope(
            path="/api/v1/webhooks/github/push",
            method="POST",
            auth_token=forged_token,
        )

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].actor_id is None, (
            f"Forged actor_id '{events[0].actor_id}' written to audit for "
            "anonymous webhook — all three audit layers poisoned"
        )
        assert events[0].actor_username is None, (
            f"Forged actor_username '{events[0].actor_username}' written to anonymous webhook audit"
        )
        assert events[0].actor_type is None, (
            f"Forged actor_type '{events[0].actor_type}' written to anonymous webhook audit"
        )

    @pytest.mark.asyncio
    async def test_forged_identity_propagates_to_context_var(self) -> None:
        """Forged JWT identity must NOT propagate via actor_context_var.

        actor_context_var is read by:
        - emit_audit_event() for business-level audit events
        - set_audit_context() for PostgreSQL SET LOCAL commands

        If the middleware sets forged identity into the context var, ALL
        downstream audit is poisoned.
        """
        captured_context: list[AuditActorContext | None] = []

        async def capture_context_app(
            scope: MutableMapping[str, Any],
            receive: Any,  # noqa: ANN401
            send: Any,  # noqa: ANN401
        ) -> None:
            # Capture what the middleware put in actor_context_var
            captured_context.append(actor_context_var.get())
            await send({"type": "http.response.start", "status": 202, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = AuditMiddleware(capture_context_app, _make_fastapi_app())

        forged_token = _forge_alg_none_jwt()
        scope = _make_scope(
            path="/api/v1/webhooks/eda/event",
            method="POST",
            auth_token=forged_token,
        )

        with patch(_EMIT_PATCH):
            await middleware(scope, AsyncMock(), AsyncMock())

        assert len(captured_context) == 1
        ctx = captured_context[0]
        # After fix: anonymous endpoint should not have forged actor in context
        assert ctx is None or ctx.actor_id is None, (
            f"Forged actor_id '{ctx.actor_id if ctx else None}' propagated "
            "via actor_context_var — poisons business events and DB triggers"
        )
        assert ctx is None or ctx.actor_username is None, (
            f"Forged actor_username '{ctx.actor_username if ctx else None}' propagated via actor_context_var"
        )

    @pytest.mark.asyncio
    async def test_forged_username_length_not_capped(self) -> None:
        """Forged preferred_username with excessive length must not be stored.

        Jira notes: 'actor_username capped and sanitized' in expected behavior.
        Current code does not cap username length from unverified JWT.
        """
        long_username = "A" * 10000
        downstream = _make_app(status_code=202)
        middleware = AuditMiddleware(downstream, _make_fastapi_app())

        forged_token = _forge_alg_none_jwt(preferred_username=long_username)
        scope = _make_scope(
            path="/api/v1/webhooks/test",
            method="POST",
            auth_token=forged_token,
        )

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        # After fix: either actor_username is None (best) or capped
        username = events[0].actor_username
        assert username is None or len(username) <= 255, (
            f"Uncapped forged username length {len(username)} chars — potential for log injection and storage abuse"
        )
