"""Unit tests for the AuditMiddleware ASGI middleware.

Tests cover response logging:
- Response completion logged with method, path, query parameters, status code
- User information logged when authenticated
- Excluded paths are not logged
- Source component resolved from endpoint
- Context IDs (workflow, execution, activity) resolved from path params and context vars
- Path and method sanitization
- Error resilience
- Content-Length header extraction edge cases
"""

# mypy: disable-error-code="attr-defined"

from collections.abc import MutableMapping
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI

from syntara.api.constants import EXCLUDED_PATHS
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.emitter import VERIFIED_ACTOR_STATE_KEY, AuditActorContext, actor_context_var
from syntara.audit.events.http_request import HTTPRequestEvent, HTTPRequestHandler
from syntara.audit.middleware import AuditMiddleware
from syntara.audit.models.audit_event import AuditEvent, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.core.models.principal import PrincipalType

_EMIT_PATCH = "syntara.audit.emitter._do_emit_audit_event"


def _make_scope(
    path: str = "/api/v1/workflows",
    method: str = "GET",
    scope_type: str = "http",
    query_string: bytes = b"",
    path_params: dict[str, Any] | None = None,
    headers: list[tuple[bytes, bytes]] | None = None,
    auth_token: str | None = None,
) -> dict[str, Any]:
    """Build a minimal ASGI scope dict.

    Args:
        path: Request path
        method: HTTP method
        scope_type: ASGI scope type (default: http)
        query_string: Query string bytes
        path_params: Path parameters dict
        headers: List of header tuples
        auth_token: Optional JWT token to add to Authorization header

    Returns:
        ASGI scope dict

    """
    # Start with provided headers or empty list
    scope_headers = list(headers) if headers else []

    # Add Authorization header if token provided
    if auth_token:
        scope_headers.append((b"authorization", f"Bearer {auth_token}".encode("latin-1")))

    scope: dict[str, Any] = {
        "type": scope_type,
        "path": path,
        "method": method,
        "query_string": query_string,
        "headers": scope_headers,
    }
    if path_params is not None:
        scope["path_params"] = path_params
    return scope


def _make_app(
    status_code: int = 200,
    verified_actor: AuditActorContext | None = None,
) -> Any:  # noqa: ANN401
    """Create a fake ASGI app that sends a response with the given status.

    When *verified_actor* is provided, the app writes to both
    ``actor_context_var`` and ``scope["state"]`` to simulate what
    FastAPI auth dependencies do after cryptographic verification.
    The scope-state path is how verified identity crosses the
    ``BaseHTTPMiddleware`` task boundary back to ``AuditMiddleware``.
    """

    async def app(scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
        if verified_actor is not None:
            actor_context_var.set(verified_actor)
            scope.setdefault("state", {})[VERIFIED_ACTOR_STATE_KEY] = verified_actor
        await send({"type": "http.response.start", "status": status_code, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    return app


def _make_fastapi_app() -> FastAPI:
    """Create a minimal FastAPI app with routes for testing context ID extraction."""
    app = FastAPI()

    # Define routes that match the paths used in tests
    @app.get("/api/v1/workflows")
    async def list_workflows() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str) -> dict[str, str]:
        return {"workflow_id": workflow_id}

    @app.get("/api/v1/executions/{execution_id}")
    async def get_execution(execution_id: str) -> dict[str, str]:
        return {"execution_id": execution_id}

    @app.get("/api/v1/executions/{execution_id}/activities/{activity_id}/signal")
    async def signal_activity(execution_id: str, activity_id: str) -> dict[str, str]:
        return {"execution_id": execution_id, "activity_id": activity_id}

    # Generic catch-all for other paths used in tests
    @app.get("/auth/login")
    @app.get("/auth/callback")
    @app.get("/metrics")
    @app.get("/custom-endpoint")
    @app.get("/api/v1/auth")
    async def generic_handler() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _get_audit_events(mock_emit: MagicMock, event_action: str) -> list[AuditEvent]:
    """Extract AuditEvent objects with the given action from mock calls."""
    return [call[0][0] for call in mock_emit.call_args_list if call[0][0].event_action == event_action]


def _get_request_completed_data(mock_emit: MagicMock) -> list[AuditContextData]:
    """Extract typed AuditContextData from request_completed audit events."""
    events = _get_audit_events(mock_emit, "request_completed")
    result: list[AuditContextData] = []
    for event in events:
        assert isinstance(event.structured_data, AuditContextData)
        result.append(event.structured_data)
    return result


# =============================================================================
# AuditMiddleware - basic functionality
# =============================================================================


class TestAuditMiddlewareBasic:
    """Basic audit middleware functionality."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})

    def test_filters_routes_with_context_id_params(self) -> None:
        """Middleware pre-filters routes to only those with context ID path params."""
        app = _make_app(status_code=200)
        fastapi_app = _make_fastapi_app()
        middleware = AuditMiddleware(app, fastapi_app)

        # Verify that _context_routes only contains routes with context ID params
        # Based on _make_fastapi_app(), we have:
        # - /api/v1/workflows/{workflow_id} - has workflow_id ✓
        # - /api/v1/executions/{execution_id} - has execution_id ✓
        # - /api/v1/executions/{execution_id}/activities/{activity_id}/signal - has execution_id and activity_id ✓
        # - /api/v1/workflows - no context IDs ✗
        # - /auth/login - no context IDs ✗
        # - /auth/callback - no context IDs ✗
        # - /metrics - no context IDs ✗
        # - /custom-endpoint - no context IDs ✗
        # - /api/v1/auth - no context IDs ✗

        context_route_paths = {route.path for route in middleware._context_routes}

        # Routes with context IDs should be present
        assert "/api/v1/workflows/{workflow_id}" in context_route_paths
        assert "/api/v1/executions/{execution_id}" in context_route_paths
        assert "/api/v1/executions/{execution_id}/activities/{activity_id}/signal" in context_route_paths

        # Routes without context IDs should NOT be present
        assert "/api/v1/workflows" not in context_route_paths
        assert "/auth/login" not in context_route_paths
        assert "/metrics" not in context_route_paths

        # Verify the optimization: should have 3 context routes, not all 9 routes
        assert len(middleware._context_routes) == 3
        assert len(fastapi_app.router.routes) > len(middleware._context_routes)

    @pytest.mark.asyncio
    async def test_emits_single_request_completed_event(self) -> None:
        """A single request_completed event is emitted per request."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(path="/api/v1/workflows", method="GET")
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        assert mock_emit.call_count == 1
        data = _get_request_completed_data(mock_emit)
        assert len(data) == 1
        assert data[0].method == "GET"
        assert data[0].path == "/api/v1/workflows"
        assert data[0].status_code == 200

    @pytest.mark.asyncio
    async def test_no_request_started_event(self) -> None:
        """No request_started event is emitted."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        started = _get_audit_events(mock_emit, "request_started")
        assert len(started) == 0


# =============================================================================
# AuditMiddleware - query parameters
# =============================================================================


class TestAuditMiddlewareQueryParams:
    """Query parameter parsing and logging."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})

    @pytest.mark.asyncio
    async def test_logs_query_parameters(self) -> None:
        """Query parameters are included in request_completed log."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(
            path="/api/v1/workflows",
            query_string=b"status=active&limit=10",
        )
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert data[0].query_params is not None
        assert data[0].query_params["status"] == "active"
        assert data[0].query_params["limit"] == "10"

    @pytest.mark.asyncio
    async def test_no_query_params_logged_when_empty(self) -> None:
        """No query_params field when query string is empty."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(path="/api/v1/workflows", query_string=b"")
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert data[0].query_params is None

    @pytest.mark.asyncio
    async def test_handles_invalid_query_string(self) -> None:
        """Invalid query strings are handled gracefully."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        # Invalid UTF-8 sequence
        scope = _make_scope(path="/api/v1/workflows", query_string=b"\xff\xfe")
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert data[0].query_params is not None
        assert "raw" in data[0].query_params

    @pytest.mark.asyncio
    async def test_handles_multi_value_query_params(self) -> None:
        """Multi-value query parameters are logged as lists."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(
            path="/api/v1/workflows",
            query_string=b"tag=foo&tag=bar",
        )
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert data[0].query_params is not None
        assert data[0].query_params["tag"] == ["foo", "bar"]

    @pytest.mark.asyncio
    async def test_handles_mixed_single_and_multi_value_params(self) -> None:
        """Mixed single and multi-value params are parsed correctly."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(
            path="/api/v1/workflows",
            query_string=b"status=active&tag=foo&tag=bar&limit=10",
        )
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert data[0].query_params is not None
        assert data[0].query_params["status"] == "active"
        assert data[0].query_params["tag"] == ["foo", "bar"]
        assert data[0].query_params["limit"] == "10"


# =============================================================================
# AuditMiddleware - exclusions
# =============================================================================


class TestAuditMiddlewareExclusions:
    """Excluded paths and non-HTTP scopes are not logged."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", sorted(EXCLUDED_PATHS))
    async def test_excluded_paths_not_logged(self, path: str) -> None:
        """Excluded paths do not generate log entries."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(_make_scope(path=path), AsyncMock(), AsyncMock())

        assert mock_emit.call_count == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", sorted(EXCLUDED_PATHS))
    async def test_excluded_paths_still_pass_to_app(self, path: str) -> None:
        """Excluded paths are still forwarded to the underlying app."""
        call_count = 0

        async def counting_app(scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            nonlocal call_count
            call_count += 1

        middleware = AuditMiddleware(counting_app, _make_fastapi_app())
        await middleware(_make_scope(path=path), AsyncMock(), AsyncMock())

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_non_http_scope_passthrough(self) -> None:
        """WebSocket and other non-HTTP scopes do not generate logs."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(scope_type="websocket")
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        assert mock_emit.call_count == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/workflows",
            "/auth/login",
            "/auth/callback",
            "/metrics",
            "/custom-endpoint",
        ],
    )
    async def test_non_excluded_paths_are_logged(self, path: str) -> None:
        """Non-excluded paths generate log entries."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(_make_scope(path=path), AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert len(data) == 1
        assert data[0].path == path


# =============================================================================
# AuditMiddleware - user context
# =============================================================================


class TestAuditMiddlewareUserContext:
    """User information is logged when available."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})

    @pytest.mark.asyncio
    async def test_logs_user_information(self) -> None:
        """User information is included in request logs when auth dependency sets actor context."""
        user_id = uuid4()
        username = "test-audit-user"
        actor = AuditActorContext(actor_id=user_id, actor_username=username, actor_type=PrincipalType.USER)
        app = _make_app(status_code=200, verified_actor=actor)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(path="/api/v1/workflows")

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].actor_id == user_id
        assert events[0].actor_type == "user"
        assert events[0].actor_username == username
        assert isinstance(events[0].structured_data, AuditContextData)

    @pytest.mark.asyncio
    async def test_cert_authenticated_service_actor(self) -> None:
        """Cert-authenticated request logs actor_type=service with cert CN."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(path="/api/v1/workflows")
        scope["state"] = {"is_cert_authenticated": True, "cert_cn": "worker.ao.svc"}

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].actor_id is None
        assert events[0].actor_type == "service"
        assert events[0].actor_username == "worker.ao.svc"

    @pytest.mark.asyncio
    async def test_cert_cn_control_chars_sanitized(self) -> None:
        """Control characters in cert CN are stripped before audit logging."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(path="/api/v1/workflows")
        scope["state"] = {"is_cert_authenticated": True, "cert_cn": "worker\r\n.ao.svc"}

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].actor_username == "worker.ao.svc"

    @pytest.mark.asyncio
    async def test_cert_cn_without_flag_not_trusted(self) -> None:
        """cert_cn in state without is_cert_authenticated=True is not trusted."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(path="/api/v1/workflows")
        scope["state"] = {"is_cert_authenticated": False, "cert_cn": "spoofed.svc"}

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].actor_id is None
        assert events[0].actor_type is None
        assert events[0].actor_username is None

    @pytest.mark.asyncio
    async def test_no_user_logs_without_authentication(self) -> None:
        """Requests without authentication have no actor identity."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(path="/api/v1/workflows")
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].actor_id is None
        assert events[0].actor_type is None
        assert events[0].actor_username is None
        assert isinstance(events[0].structured_data, AuditContextData)

    @pytest.mark.asyncio
    async def test_bearer_token_without_downstream_auth_produces_anonymous_actor(self) -> None:
        """Bearer token alone (no downstream auth setting actor_context_var) → anonymous actor."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(path="/api/v1/workflows", auth_token="some.bearer.token")  # noqa: S106

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].actor_id is None
        assert events[0].actor_type is None
        assert events[0].actor_username is None
        assert isinstance(events[0].structured_data, AuditContextData)

    @pytest.mark.asyncio
    async def test_forged_alg_none_jwt_produces_anonymous_actor(self) -> None:
        """Forged alg:none JWT (CVE-style attack) produces anonymous actor, not forged identity."""
        import jwt as pyjwt

        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        forged_token = pyjwt.encode(
            {"sub": str(uuid4()), "preferred_username": "forged-admin"},
            key="",
            algorithm="none",
        )
        scope = _make_scope(path="/api/v1/workflows", auth_token=forged_token)

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].actor_id is None
        assert events[0].actor_type is None
        assert events[0].actor_username is None

    @pytest.mark.asyncio
    async def test_downstream_auth_overrides_initial_anonymous(self) -> None:
        """Auth dependency setting actor_context_var propagates to request_completed event."""
        user_id = uuid4()
        actor = AuditActorContext(
            actor_id=user_id,
            actor_username="verified-user",
            actor_type=PrincipalType.USER,
        )
        app = _make_app(status_code=200, verified_actor=actor)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(path="/api/v1/workflows")

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].actor_id == user_id
        assert events[0].actor_type == "user"
        assert events[0].actor_username == "verified-user"

    @pytest.mark.asyncio
    async def test_service_account_actor_type_from_downstream_auth(self) -> None:
        """Service account actor type is correctly propagated from downstream auth."""
        user_id = UUID("550e8400-e29b-41d4-a716-446655440000")
        actor = AuditActorContext(
            actor_id=user_id,
            actor_username="service-account",
            actor_type=PrincipalType.SERVICE_ACCOUNT,
        )
        app = _make_app(status_code=200, verified_actor=actor)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(path="/api/v1/workflows")

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].actor_id == user_id
        assert events[0].actor_type == "service_account"
        assert events[0].actor_username == "service-account"

    @pytest.mark.asyncio
    async def test_auth_failure_produces_anonymous_audit(self) -> None:
        """Failed auth (exception without setting actor_context_var) → anonymous audit event."""

        async def failing_auth_app(
            scope: MutableMapping[str, Any],
            receive: Any,  # noqa: ANN401
            send: Any,  # noqa: ANN401
        ) -> None:
            msg = "authentication failed"
            raise RuntimeError(msg)

        middleware = AuditMiddleware(failing_auth_app, _make_fastapi_app())
        scope = _make_scope(path="/api/v1/workflows", auth_token="some.bearer.token")  # noqa: S106

        receive = AsyncMock()
        send = AsyncMock()
        with patch(_EMIT_PATCH) as mock_emit:
            with pytest.raises(RuntimeError, match="authentication failed"):
                await middleware(scope, receive, send)

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].actor_id is None
        assert events[0].actor_type is None
        assert events[0].actor_username is None


# =============================================================================
# AuditMiddleware - response logging
# =============================================================================


class TestAuditMiddlewareResponse:
    """Response completion is logged with status code."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})

    @pytest.mark.asyncio
    async def test_logs_status_code_from_response(self) -> None:
        """Status code is captured from the downstream app response."""
        app = _make_app(status_code=404)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert data[0].status_code == 404

    @pytest.mark.asyncio
    async def test_logs_500_on_exception(self) -> None:
        """Unhandled exceptions produce a request_completed event with status 500."""

        async def failing_app(scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            msg = "boom"
            raise RuntimeError(msg)

        middleware = AuditMiddleware(failing_app, _make_fastapi_app())
        with patch(_EMIT_PATCH) as mock_emit, pytest.raises(RuntimeError, match="boom"):
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert len(data) == 1
        assert data[0].status_code == 500

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status_code", "expected_event_status"),
        [
            (200, EventStatus.SUCCESS),
            (201, EventStatus.SUCCESS),
            (204, EventStatus.SUCCESS),
            (301, EventStatus.SUCCESS),
            (399, EventStatus.SUCCESS),
            (400, EventStatus.ERROR),
            (403, EventStatus.ERROR),
            (404, EventStatus.ERROR),
            (500, EventStatus.ERROR),
            (503, EventStatus.ERROR),
        ],
    )
    async def test_event_status_derived_from_status_code(
        self, status_code: int, expected_event_status: EventStatus
    ) -> None:
        """event_status is SUCCESS for <400, ERROR for >=400."""
        app = _make_app(status_code=status_code)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].event_status == expected_event_status

    @pytest.mark.asyncio
    async def test_event_status_error_on_exception(self) -> None:
        """event_status is ERROR when the app raises an unhandled exception."""

        async def failing_app(scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            msg = "boom"
            raise RuntimeError(msg)

        middleware = AuditMiddleware(failing_app, _make_fastapi_app())
        with patch(_EMIT_PATCH) as mock_emit, pytest.raises(RuntimeError, match="boom"):
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].event_status == EventStatus.ERROR

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status_code", "expected_event_severity"),
        [
            (200, EventSeverity.INFO),
            (201, EventSeverity.INFO),
            (301, EventSeverity.INFO),
            (399, EventSeverity.INFO),
            (400, EventSeverity.WARNING),
            (403, EventSeverity.WARNING),
            (404, EventSeverity.WARNING),
            (499, EventSeverity.WARNING),
            (500, EventSeverity.ERROR),
            (503, EventSeverity.ERROR),
        ],
    )
    async def test_event_severity_derived_from_status_code(
        self, status_code: int, expected_event_severity: EventSeverity
    ) -> None:
        """event_severity is INFO for <400, WARNING for 4xx, ERROR for 5xx."""
        app = _make_app(status_code=status_code)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].event_severity == expected_event_severity

    @pytest.mark.asyncio
    async def test_event_severity_error_on_exception(self) -> None:
        """event_severity is ERROR when the app raises an unhandled exception (forced 500)."""

        async def failing_app(scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            msg = "boom"
            raise RuntimeError(msg)

        middleware = AuditMiddleware(failing_app, _make_fastapi_app())
        with patch(_EMIT_PATCH) as mock_emit, pytest.raises(RuntimeError, match="boom"):
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].event_severity == EventSeverity.ERROR

    @pytest.mark.asyncio
    async def test_event_severity_matches_event_status_semantics(self) -> None:
        """Severity and status are consistent: a WARNING-severity event has ERROR status (4xx)."""
        app = _make_app(status_code=404)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        # 4xx should be WARNING severity but still ERROR status — the two fields
        # carry distinct information and must not be silently collapsed.
        assert events[0].event_severity == EventSeverity.WARNING
        assert events[0].event_status == EventStatus.ERROR

    @pytest.mark.asyncio
    async def test_fail_closed_when_response_start_never_sent(self) -> None:
        """An app that returns without sending http.response.start is classified as 500/ERROR/ERROR.

        The middleware initialises status_code to 500 fail-closed: if the
        downstream app returns normally but never emits an ``http.response.start``
        message, the audit event must still reflect an ERROR outcome — not a
        misleading INFO/SUCCESS with status_code=0.
        """

        async def silent_app(scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            # Returns without ever calling send — simulates a broken
            # downstream app or a misconfigured middleware chain.
            return

        middleware = AuditMiddleware(silent_app, _make_fastapi_app())
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].event_severity == EventSeverity.ERROR
        assert events[0].event_status == EventStatus.ERROR
        data = _get_request_completed_data(mock_emit)
        assert data[0].status_code == 500

    @pytest.mark.asyncio
    async def test_exception_after_2xx_response_start_emits_500_error(self) -> None:
        """If the app sends a 2xx http.response.start but then raises during body streaming.

        The audit event must reflect 500/ERROR/ERROR — not the intercepted 2xx.
        """

        async def partial_sender(
            scope: MutableMapping[str, Any],
            receive: Any,  # noqa: ANN401
            send: Any,  # noqa: ANN401
        ) -> None:
            await send({"type": "http.response.start", "status": 200, "headers": []})
            msg = "body streaming failed"
            raise RuntimeError(msg)

        middleware = AuditMiddleware(partial_sender, _make_fastapi_app())
        with patch(_EMIT_PATCH) as mock_emit, pytest.raises(RuntimeError, match="body streaming failed"):
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        assert events[0].event_severity == EventSeverity.ERROR
        assert events[0].event_status == EventStatus.ERROR
        data = _get_request_completed_data(mock_emit)
        assert data[0].status_code == 500

    @pytest.mark.asyncio
    async def test_exception_propagates(self) -> None:
        """The original exception is re-raised after logging."""

        async def failing_app(scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            msg = "original error"
            raise ValueError(msg)

        middleware = AuditMiddleware(failing_app, _make_fastapi_app())
        with pytest.raises(ValueError, match="original error"):
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

    @pytest.mark.asyncio
    async def test_completed_event_has_actor(self) -> None:
        """The request_completed event carries the authenticated actor from downstream auth."""
        user_id = uuid4()
        username = "test-completed-user"
        actor = AuditActorContext(actor_id=user_id, actor_username=username, actor_type=PrincipalType.USER)
        app = _make_app(status_code=200, verified_actor=actor)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope()

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert events[0].actor_id == user_id
        assert events[0].actor_type == "user"
        assert events[0].actor_username == username

    @pytest.mark.asyncio
    async def test_exception_preserves_actor_context(self) -> None:
        """Actor context set by auth dependency is preserved on exception path."""
        user_id = uuid4()
        username = "test-exception-user"

        async def failing_app_with_auth(
            scope: MutableMapping[str, Any],
            receive: Any,  # noqa: ANN401
            send: Any,  # noqa: ANN401
        ) -> None:
            actor = AuditActorContext(actor_id=user_id, actor_username=username, actor_type=PrincipalType.USER)
            actor_context_var.set(actor)
            scope.setdefault("state", {})[VERIFIED_ACTOR_STATE_KEY] = actor
            msg = "boom"
            raise RuntimeError(msg)

        middleware = AuditMiddleware(failing_app_with_auth, _make_fastapi_app())
        scope = _make_scope()

        with (
            patch(_EMIT_PATCH) as mock_emit,
            pytest.raises(RuntimeError, match="boom"),
        ):
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert events[0].actor_id == user_id
        assert events[0].actor_type == "user"
        assert events[0].actor_username == username


# =============================================================================
# AuditMiddleware - source component resolution
# =============================================================================


class TestAuditMiddlewareSourceComponent:
    """request_completed uses the resolved endpoint module as source_component."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})

    @pytest.mark.asyncio
    async def test_source_component_from_endpoint(self) -> None:
        """source_component is set to the endpoint's module on request_completed."""

        async def handler(scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            scope["endpoint"] = handler
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = AuditMiddleware(handler, _make_fastapi_app())
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert events[0].source_component == handler.__module__

    @pytest.mark.asyncio
    async def test_source_component_fallback_without_endpoint(self) -> None:
        """source_component falls back to the middleware module when no endpoint is set."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert events[0].source_component == "syntara.audit.middleware"

    @pytest.mark.asyncio
    async def test_source_component_on_exception(self) -> None:
        """source_component resolves from endpoint even on the exception path."""

        async def failing_handler(scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            scope["endpoint"] = failing_handler
            msg = "boom"
            raise RuntimeError(msg)

        middleware = AuditMiddleware(failing_handler, _make_fastapi_app())
        with patch(_EMIT_PATCH) as mock_emit, pytest.raises(RuntimeError, match="boom"):
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert events[0].source_component == failing_handler.__module__


# =============================================================================
# AuditMiddleware - context ID resolution
# =============================================================================


class TestAuditMiddlewareContextIds:
    """Context IDs (workflow, execution, activity) are resolved from the request."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})

    @pytest.mark.asyncio
    async def test_workflow_id_from_path_params(self) -> None:
        """workflow_id is extracted from path_params when available."""
        wf_id = uuid4()
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(
            path=f"/api/v1/workflows/{wf_id}",
            path_params={"workflow_id": str(wf_id)},
        )
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert events[0].workflow_id == wf_id

    @pytest.mark.asyncio
    async def test_execution_id_from_path_params(self) -> None:
        """execution_id is extracted from path_params when available."""
        exec_id = uuid4()
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(
            path=f"/api/v1/executions/{exec_id}",
            path_params={"execution_id": str(exec_id)},
        )
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert events[0].execution_id == exec_id

    @pytest.mark.asyncio
    async def test_activity_id_from_path_params(self) -> None:
        """activity_id is extracted from path_params when available."""
        exec_id = uuid4()
        activity_id = "my-activity"
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(
            path=f"/api/v1/executions/{exec_id}/activities/{activity_id}/signal",
            path_params={"execution_id": str(exec_id), "activity_id": activity_id},
        )
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert events[0].activity_id == activity_id
        assert events[0].execution_id == exec_id

    @pytest.mark.asyncio
    async def test_workflow_id_from_context_var(self) -> None:
        """workflow_id falls back to context variable when not in path_params."""
        wf_id = uuid4()

        async def app_that_sets_context(
            scope: MutableMapping[str, Any],
            receive: Any,  # noqa: ANN401
            send: Any,  # noqa: ANN401
        ) -> None:
            from syntara.audit.emitter import workflow_id_context_var

            workflow_id_context_var.set(wf_id)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = AuditMiddleware(app_that_sets_context, _make_fastapi_app())
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert events[0].workflow_id == wf_id

    @pytest.mark.asyncio
    async def test_path_params_initialize_context_var(self) -> None:
        """Path params initialize context variables that handlers can override."""
        path_wf_id = uuid4()
        ctx_wf_id = uuid4()

        async def app_that_sets_context(
            scope: MutableMapping[str, Any],
            receive: Any,  # noqa: ANN401
            send: Any,  # noqa: ANN401
        ) -> None:
            from syntara.audit.emitter import workflow_id_context_var

            # Handler overwrites the context variable set from path params
            workflow_id_context_var.set(ctx_wf_id)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = AuditMiddleware(app_that_sets_context, _make_fastapi_app())
        scope = _make_scope(
            path=f"/api/v1/workflows/{path_wf_id}",
            path_params={"workflow_id": str(path_wf_id)},
        )
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        # The audit event reflects the overridden value from the handler
        assert events[0].workflow_id == ctx_wf_id

    @pytest.mark.asyncio
    async def test_malformed_workflow_id_defaults_to_none(self) -> None:
        """Malformed workflow_id in path params defaults to None."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(
            path="/api/v1/workflows/not-a-uuid",
            path_params={"workflow_id": "not-a-uuid"},
        )
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert events[0].workflow_id is None

    @pytest.mark.asyncio
    async def test_malformed_execution_id_defaults_to_none(self) -> None:
        """Malformed execution_id in path params defaults to None."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(
            path="/api/v1/executions/not-a-uuid",
            path_params={"execution_id": "not-a-uuid"},
        )
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert events[0].execution_id is None

    @pytest.mark.asyncio
    async def test_context_ids_none_when_not_available(self) -> None:
        """Context IDs are None when not in path params or context vars."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert events[0].workflow_id is None
        assert events[0].execution_id is None
        assert events[0].activity_id is None

    @pytest.mark.asyncio
    async def test_unmatched_route_defaults_to_none(self) -> None:
        """Context IDs are None when path doesn't match any route and scope has no path_params."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        # Send request to a path that doesn't match any registered route
        # with no path_params in scope (simulating pre-routing state)
        scope = _make_scope(path="/unknown/path/123")
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert events[0].workflow_id is None
        assert events[0].execution_id is None
        assert events[0].activity_id is None

    @pytest.mark.asyncio
    async def test_empty_fastapi_app_no_routes(self) -> None:
        """Middleware handles FastAPI app with zero registered routes gracefully."""
        app = _make_app(status_code=200)
        # Create an empty FastAPI app with no routes
        empty_fastapi_app = FastAPI()
        middleware = AuditMiddleware(app, empty_fastapi_app)

        scope = _make_scope(path="/test")
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        # Verify middleware doesn't crash and processes request successfully
        events = _get_audit_events(mock_emit, "request_completed")
        assert len(events) == 1
        # Context IDs should be None since no route matching occurred
        assert events[0].workflow_id is None
        assert events[0].execution_id is None
        assert events[0].activity_id is None


# =============================================================================
# AuditMiddleware - path and method sanitization
# =============================================================================


class TestAuditMiddlewareSanitization:
    """Path normalization, control character stripping, and length capping."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})

    @pytest.mark.asyncio
    async def test_path_normalized_before_logging(self) -> None:
        """Path traversals and redundant separators are normalized."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(path="/api/v1/../v1/workflows")
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert data[0].path == "/api/v1/workflows"

    @pytest.mark.asyncio
    async def test_path_double_slashes_normalized(self) -> None:
        """Double slashes in path are collapsed."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(path="/api//v1///workflows")
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert data[0].path == "/api/v1/workflows"

    @pytest.mark.asyncio
    async def test_control_chars_stripped_from_path(self) -> None:
        """Control characters in path are removed before logging."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(path="/api/v1/work\r\nflows")
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert data[0].path == "/api/v1/workflows"

    @pytest.mark.asyncio
    async def test_null_bytes_stripped_from_path(self) -> None:
        """Null bytes in path are removed."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(path="/api/v1/work\x00flows")
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert data[0].path == "/api/v1/workflows"

    @pytest.mark.asyncio
    async def test_control_chars_stripped_from_method(self) -> None:
        """Control characters in HTTP method are removed."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(method="GE\nT")
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert data[0].method == "GET"

    @pytest.mark.asyncio
    async def test_path_truncated_at_max_length(self) -> None:
        """Paths longer than 2048 characters are truncated."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        long_path = "/" + "a" * 3000
        scope = _make_scope(path=long_path)
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert len(data[0].path) == 2048

    @pytest.mark.asyncio
    async def test_normalized_path_used_for_exclusion_check(self) -> None:
        """Exclusion check uses the normalized path."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        # Use path traversal to reach an excluded path
        excluded = next(iter(sorted(EXCLUDED_PATHS)))
        traversal_path = "/dummy/../" + excluded.lstrip("/")
        scope = _make_scope(path=traversal_path)

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        assert mock_emit.call_count == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "encoded_path",
        [
            "/%68ealthz/live",  # /healthz/live
            "/%68%65althz/live",  # /healthz/live (multiple encoded chars)
            "/hea%6Cthz/live",  # /healthz/live
            "/%68ealthz/ready",  # /healthz/ready
            "/healthz/%72eady",  # /healthz/ready
        ],
    )
    async def test_percent_encoded_excluded_path_still_excluded(self, encoded_path: str) -> None:
        """Percent-encoded excluded paths are decoded before exclusion check."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(_make_scope(path=encoded_path), AsyncMock(), AsyncMock())

        assert mock_emit.call_count == 0

    @pytest.mark.asyncio
    async def test_percent_encoded_path_decoded_in_log(self) -> None:
        """Percent-encoded path segments are decoded before logging."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(path="/api/v1/%77orkflows")
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert data[0].path == "/api/v1/workflows"

    @pytest.mark.asyncio
    async def test_sanitized_values_in_event_message(self) -> None:
        """Event message uses sanitized method and path."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(path="/api//v1/work\nflows", method="PO\rST")
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert events[0].event_message == "Request completed: POST /api/v1/workflows 200"

    @pytest.mark.asyncio
    async def test_event_message_excludes_query_params(self) -> None:
        """Query params are not included in event_message to avoid leaking sensitive values."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(
            path="/api/v1/auth",
            method="GET",
            query_string=b"username=admin&password=hunter2",
        )
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _get_audit_events(mock_emit, "request_completed")
        assert events[0].event_message == "Request completed: GET /api/v1/auth 200"
        assert "hunter2" not in events[0].event_message
        assert "username" not in events[0].event_message


# =============================================================================
# AuditMiddleware - error resilience
# =============================================================================


class TestAuditMiddlewareErrorResilience:
    """Audit event emission failures do not crash requests."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})

    @pytest.mark.asyncio
    async def test_request_succeeds_when_emit_raises(self) -> None:
        """Request completes normally even if audit event emission fails."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        sent_messages: list[MutableMapping[str, Any]] = []

        async def capture_send(message: MutableMapping[str, Any]) -> None:
            sent_messages.append(message)

        dispatch_patch = "syntara.audit.middleware.AuditEventDispatcher.dispatch"
        with patch(dispatch_patch, side_effect=RuntimeError("dispatch broken")):
            await middleware(_make_scope(), AsyncMock(), capture_send)

        assert len(sent_messages) == 2
        assert sent_messages[0]["status"] == 200

    @pytest.mark.asyncio
    async def test_emit_failure_logged_as_warning_with_context(self) -> None:
        """Audit emission failure is logged with error_type and status_code for triage."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        dispatch_patch = "syntara.audit.middleware.AuditEventDispatcher.dispatch"
        with (
            patch(dispatch_patch, side_effect=RuntimeError("dispatch broken")),
            patch("syntara.audit.middleware.logger") as mock_logger,
        ):
            await middleware(_make_scope(), AsyncMock(), AsyncMock())
            assert mock_logger.warning.call_count >= 1
            call_args = mock_logger.warning.call_args
            assert "audit_middleware_failed" in call_args[0]
            assert call_args[1]["error_type"] == "RuntimeError"
            assert call_args[1]["status_code"] == 200


# =============================================================================
# AuditMiddleware - X-Request-Id extraction
# =============================================================================


class TestAuditMiddlewareRequestId:
    """Tests for X-Request-Id header extraction and ContextVar propagation."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})

    @pytest.mark.asyncio
    async def test_valid_request_id_sets_context_var(self) -> None:
        """A valid UUID X-Request-Id header is propagated via ContextVar."""
        rid = uuid4()
        scope = _make_scope(headers=[(b"x-request-id", str(rid).encode())])
        captured: list[UUID | None] = []

        from syntara.audit.emitter import request_id_context_var

        async def capturing_app(scope: Any, receive: Any, send: Any) -> None:  # noqa: ANN401
            captured.append(request_id_context_var.get())
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = AuditMiddleware(capturing_app, _make_fastapi_app())
        with patch(_EMIT_PATCH):
            await middleware(scope, AsyncMock(), AsyncMock())

        assert captured[0] == rid

    @pytest.mark.asyncio
    async def test_missing_request_id_sets_none(self) -> None:
        """Without X-Request-Id header, ContextVar is set to None."""
        scope = _make_scope()
        captured: list[UUID | None] = []

        from syntara.audit.emitter import request_id_context_var

        async def capturing_app(scope: Any, receive: Any, send: Any) -> None:  # noqa: ANN401
            captured.append(request_id_context_var.get())
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = AuditMiddleware(capturing_app, _make_fastapi_app())
        with patch(_EMIT_PATCH):
            await middleware(scope, AsyncMock(), AsyncMock())

        assert captured[0] is None

    @pytest.mark.asyncio
    async def test_invalid_uuid_is_ignored(self) -> None:
        """A malformed X-Request-Id is silently ignored (ContextVar stays None)."""
        scope = _make_scope(headers=[(b"x-request-id", b"not-a-uuid")])
        captured: list[UUID | None] = []

        from syntara.audit.emitter import request_id_context_var

        async def capturing_app(scope: Any, receive: Any, send: Any) -> None:  # noqa: ANN401
            captured.append(request_id_context_var.get())
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = AuditMiddleware(capturing_app, _make_fastapi_app())
        with patch(_EMIT_PATCH):
            await middleware(scope, AsyncMock(), AsyncMock())

        assert captured[0] is None

    @pytest.mark.asyncio
    async def test_context_var_is_reset_after_request(self) -> None:
        """ContextVar is reset to its previous value after the request completes."""
        from syntara.audit.emitter import request_id_context_var

        rid = uuid4()
        scope = _make_scope(headers=[(b"x-request-id", str(rid).encode())])
        middleware = AuditMiddleware(_make_app(), _make_fastapi_app())

        before = request_id_context_var.get()
        with patch(_EMIT_PATCH):
            await middleware(scope, AsyncMock(), AsyncMock())
        after = request_id_context_var.get()

        assert before == after

    @pytest.mark.asyncio
    async def test_mixed_case_header_name(self) -> None:
        """Header name matching is case-insensitive (ASGI may not lowercase)."""
        rid = uuid4()
        scope = _make_scope(headers=[(b"X-Request-Id", str(rid).encode())])
        captured: list[UUID | None] = []

        from syntara.audit.emitter import request_id_context_var

        async def capturing_app(scope: Any, receive: Any, send: Any) -> None:  # noqa: ANN401
            captured.append(request_id_context_var.get())
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = AuditMiddleware(capturing_app, _make_fastapi_app())
        with patch(_EMIT_PATCH):
            await middleware(scope, AsyncMock(), AsyncMock())

        assert captured[0] == rid


# =============================================================================
# AuditMiddleware - Content-Length header extraction
# =============================================================================


class TestAuditMiddlewareContentLength:
    """Tests for Content-Length header extraction and request_payload_size logging."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({HTTPRequestEvent: HTTPRequestHandler()})

    @pytest.mark.asyncio
    async def test_content_length_valid(self) -> None:
        """A valid Content-Length header is captured as request_payload_size."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(headers=[(b"content-length", b"1234")])
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert data[0].request_payload_size == 1234

    @pytest.mark.asyncio
    async def test_content_length_missing(self) -> None:
        """Without Content-Length header, request_payload_size defaults to 0."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope()  # No headers
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert data[0].request_payload_size == 0

    @pytest.mark.asyncio
    async def test_content_length_invalid_string(self) -> None:
        """A non-numeric Content-Length value is silently ignored (defaults to 0)."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(headers=[(b"content-length", b"abc")])
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert data[0].request_payload_size == 0

    @pytest.mark.asyncio
    async def test_content_length_negative(self) -> None:
        """A negative Content-Length value is rejected (defaults to 0)."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(headers=[(b"content-length", b"-100")])
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        # Negative values are invalid and ignored
        assert data[0].request_payload_size == 0

    @pytest.mark.asyncio
    async def test_content_length_float_string(self) -> None:
        """A float string in Content-Length is rejected (int() raises ValueError)."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(headers=[(b"content-length", b"123.45")])
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        # int("123.45") raises ValueError, caught by contextlib.suppress
        assert data[0].request_payload_size == 0

    @pytest.mark.asyncio
    async def test_content_length_empty_string(self) -> None:
        """An empty Content-Length value is silently ignored (defaults to 0)."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(headers=[(b"content-length", b"")])
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert data[0].request_payload_size == 0

    @pytest.mark.asyncio
    async def test_content_length_with_whitespace(self) -> None:
        """Content-Length with leading/trailing whitespace is parsed correctly."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(headers=[(b"content-length", b"  1234  ")])
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        # int() handles whitespace automatically
        assert data[0].request_payload_size == 1234

    @pytest.mark.asyncio
    async def test_content_length_case_insensitive(self) -> None:
        """Header name matching is case-insensitive."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(headers=[(b"Content-Length", b"5678")])
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        assert data[0].request_payload_size == 5678

    @pytest.mark.asyncio
    async def test_multiple_content_length_headers_last_wins(self) -> None:
        """When multiple Content-Length headers are present, the last one wins."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(
            headers=[
                (b"content-length", b"1234"),
                (b"content-length", b"5678"),
            ]
        )
        with patch(_EMIT_PATCH) as mock_emit:
            await middleware(scope, AsyncMock(), AsyncMock())

        data = _get_request_completed_data(mock_emit)
        # The middleware's loop overwrites the value, so the last header wins
        assert data[0].request_payload_size == 5678


# =============================================================================
# AuditMiddleware - interface and endpoint_template
# =============================================================================

_DISPATCH_PATCH = "syntara.audit.dispatcher.AuditEventDispatcher.dispatch"


def _capture_http_events(mock_dispatch: MagicMock) -> list[HTTPRequestEvent]:
    """Extract HTTPRequestEvent objects from dispatch calls."""
    return [call[0][0] for call in mock_dispatch.call_args_list if isinstance(call[0][0], HTTPRequestEvent)]


class TestAuditMiddlewareInterfaceAndEndpointTemplate:
    """interface and endpoint_template fields on HTTPRequestEvent."""

    @pytest.mark.asyncio
    async def test_matched_route_populates_endpoint_template(self) -> None:
        """endpoint_template is set from scope['route'].path when a route is matched."""

        async def app(scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            scope["route"] = MagicMock(path="/api/v1/workflows/{workflow_id}")
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = AuditMiddleware(app, _make_fastapi_app())
        with patch(_DISPATCH_PATCH) as mock_dispatch:
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        events = _capture_http_events(mock_dispatch)
        assert len(events) == 1
        assert events[0].endpoint_template == "/api/v1/workflows/{workflow_id}"

    @pytest.mark.asyncio
    async def test_unmatched_route_leaves_endpoint_template_none(self) -> None:
        """endpoint_template is None when no route is matched (e.g. 404)."""
        app = _make_app(status_code=404)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        scope = _make_scope(path="/api/v1/nonexistent")
        with patch(_DISPATCH_PATCH) as mock_dispatch:
            await middleware(scope, AsyncMock(), AsyncMock())

        events = _capture_http_events(mock_dispatch)
        assert len(events) == 1
        assert events[0].endpoint_template is None

    @pytest.mark.asyncio
    async def test_ui_header_sets_interface_ui(self) -> None:
        """Interface is 'ui' when the interface context var is set."""
        from syntara.metrics.interface_tag import INTERFACE_UI, interface_context_var

        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        token = interface_context_var.set(INTERFACE_UI)
        try:
            with patch(_DISPATCH_PATCH) as mock_dispatch:
                await middleware(_make_scope(), AsyncMock(), AsyncMock())

            events = _capture_http_events(mock_dispatch)
            assert len(events) == 1
            assert events[0].interface == "ui"
        finally:
            interface_context_var.reset(token)

    @pytest.mark.asyncio
    async def test_default_interface_is_api(self) -> None:
        """Interface defaults to 'api' when no header sets it."""
        app = _make_app(status_code=200)
        middleware = AuditMiddleware(app, _make_fastapi_app())

        with patch(_DISPATCH_PATCH) as mock_dispatch:
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        events = _capture_http_events(mock_dispatch)
        assert len(events) == 1
        assert events[0].interface == "api"
