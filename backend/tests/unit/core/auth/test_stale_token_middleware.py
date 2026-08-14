"""Unit tests for StaleTokenMiddleware.

Tests cover:
- Pass-through when no Authorization header is present
- X-Token-Stale header set when token_ver < DB version
- No X-Token-Stale header when token_ver >= DB version
- Graceful handling of DB or decode errors
- Disabled user rejection with 401
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from syntara.auth.exceptions import InvalidTokenError
from syntara.auth.middleware import StaleTokenMiddleware, _cred_status_cache, _sa_status_cache, _user_status_cache
from syntara.auth.services.token_service import TokenPayload


def _build_app() -> Starlette:
    """Build a minimal Starlette app with the StaleTokenMiddleware."""

    async def homepage(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app = Starlette(
        routes=[
            Route("/", homepage),
            Route("/api/v1/auth/logout", homepage, methods=["POST"]),
            Route("/api/v1/auth/refresh", homepage, methods=["POST"]),
        ]
    )
    app.add_middleware(StaleTokenMiddleware)
    return app


def _make_payload(sub: str = "user-123", token_version: int = 0) -> TokenPayload:
    """Create a TokenPayload for testing."""
    now = datetime.now(UTC)
    return TokenPayload(
        sub=sub,
        iss="orchestrator",
        iat=now,
        exp=now,
        token_type="access",  # noqa: S106
        token_version=token_version,
    )


def _mock_token_service(payload: TokenPayload | None = None, error: Exception | None = None) -> MagicMock:
    """Create a mock TokenService."""
    mock = MagicMock()
    if error:
        mock.decode_token.side_effect = error
    else:
        mock.decode_token.return_value = payload
    return mock


def _mock_async_session(
    token_version: int | None = None,
    *,
    is_enabled: bool = True,
    error: Exception | None = None,
) -> AsyncMock:
    """Create a mock AsyncSessionLocal context manager that returns a mock session."""
    mock_session = AsyncMock()
    if error:
        mock_session.exec.side_effect = error
    else:
        mock_result = MagicMock()
        if token_version is not None:
            mock_result.one_or_none.return_value = (token_version, is_enabled)
        else:
            mock_result.one_or_none.return_value = None
        mock_session.exec.return_value = mock_result

    # Build the async context manager
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx


def _build_app_with_impostor_routes() -> Starlette:
    """Build an app that also has paths ending in /auth/logout and /auth/refresh but under a different prefix."""

    async def homepage(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app = Starlette(
        routes=[
            Route("/", homepage),
            Route("/api/v1/auth/logout", homepage, methods=["POST"]),
            Route("/api/v1/auth/refresh", homepage, methods=["POST"]),
            Route("/some-other/auth/logout", homepage, methods=["POST"]),
            Route("/some-other/auth/refresh", homepage, methods=["POST"]),
        ]
    )
    app.add_middleware(StaleTokenMiddleware)
    return app


class TestStaleTokenMiddleware:
    """Tests for StaleTokenMiddleware."""

    def setup_method(self) -> None:
        """Clear the TTL cache between tests."""
        _user_status_cache.clear()

    def test_no_auth_header_passes_through(self) -> None:
        """When no Authorization header is present, response passes through unchanged."""
        app = _build_app()

        client = TestClient(app)
        response = client.get("/")

        assert response.status_code == 200
        assert "X-Token-Stale" not in response.headers

    def test_stale_token_returns_401(self) -> None:
        """When token token_ver < DB version, middleware returns 401 TOKEN_STALE."""
        app = _build_app()
        payload = _make_payload(sub="user-123", token_version=1)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_async_session(token_version=5)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer some-jwt"})

        assert response.status_code == 401
        body = response.json()
        assert body["code"] == "TOKEN_STALE"
        assert body["retryable"] is True

    def test_no_stale_header_when_token_current(self) -> None:
        """When token token_ver >= DB version, no X-Token-Stale header."""
        app = _build_app()
        payload = _make_payload(sub="user-123", token_version=5)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_async_session(token_version=5)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer some-jwt"})

        assert response.status_code == 200
        assert "X-Token-Stale" not in response.headers

    def test_no_stale_header_when_token_ahead(self) -> None:
        """When token token_ver > DB version, no X-Token-Stale header."""
        app = _build_app()
        payload = _make_payload(sub="user-123", token_version=10)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_async_session(token_version=3)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer some-jwt"})

        assert response.status_code == 200
        assert "X-Token-Stale" not in response.headers

    def test_db_error_passes_through(self) -> None:
        """When DB connection fails, response passes through without error."""
        app = _build_app()
        payload = _make_payload(sub="user-123", token_version=0)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_async_session(error=OSError("connection refused"))

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer some-jwt"})

        assert response.status_code == 200
        assert "X-Token-Stale" not in response.headers

    def test_decode_error_passes_through(self) -> None:
        """When token cannot be decoded, response passes through without error."""
        app = _build_app()

        mock_ts = _mock_token_service(error=InvalidTokenError())

        with (
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer not-a-jwt"})

        assert response.status_code == 200
        assert "X-Token-Stale" not in response.headers

    def test_disabled_user_returns_401(self) -> None:
        """When user is disabled in DB, middleware returns 401 before handler runs."""
        app = _build_app()
        payload = _make_payload(sub="user-123", token_version=1)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_async_session(token_version=1, is_enabled=False)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer some-jwt"})

        assert response.status_code == 401
        body = response.json()
        assert body["code"] == "ACCOUNT_DISABLED"
        assert body["detail"] == "User account is disabled"

    def test_disabled_user_cached_returns_401(self) -> None:
        """When cache has is_enabled=False, return 401 without DB query."""
        app = _build_app()
        payload = _make_payload(sub="user-123", token_version=1)

        _user_status_cache["user-123"] = (1, False)

        mock_ts = _mock_token_service(payload=payload)

        with (
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer some-jwt"})

        assert response.status_code == 401

    def test_disabled_and_stale_returns_disabled(self) -> None:
        """Disabled user rejection takes priority over stale token rejection."""
        app = _build_app()
        payload = _make_payload(sub="user-123", token_version=1)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_async_session(token_version=5, is_enabled=False)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer some-jwt"})

        assert response.status_code == 401
        body = response.json()
        assert body["code"] == "ACCOUNT_DISABLED"

    def test_user_not_found_passes_through(self) -> None:
        """When user row not found, default to enabled and pass through."""
        app = _build_app()
        payload = _make_payload(sub="nonexistent-user", token_version=0)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_async_session(token_version=None)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer some-jwt"})

        assert response.status_code == 200

    def test_disabled_user_can_still_logout(self) -> None:
        """Disabled users must be able to POST /auth/logout to clear their session."""
        app = _build_app()
        payload = _make_payload(sub="user-123", token_version=1)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_async_session(token_version=1, is_enabled=False)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.post("/api/v1/auth/logout", headers={"Authorization": "Bearer some-jwt"})

        assert response.status_code == 200

    def test_stale_token_can_still_logout(self) -> None:
        """Users with stale tokens must be able to POST /auth/logout."""
        app = _build_app()
        payload = _make_payload(sub="user-123", token_version=1)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_async_session(token_version=5)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.post("/api/v1/auth/logout", headers={"Authorization": "Bearer some-jwt"})

        assert response.status_code == 200

    def test_stale_token_can_still_refresh(self) -> None:
        """Users with stale tokens must be able to POST /auth/refresh to get a new token."""
        app = _build_app()
        payload = _make_payload(sub="user-123", token_version=1)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_async_session(token_version=5)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.post("/api/v1/auth/refresh", headers={"Authorization": "Bearer some-jwt"})

        assert response.status_code == 200

    def test_group_change_seamless_refresh(self) -> None:
        """After admin bumps token_version, user is rejected then refreshes seamlessly.

        Simulates: token_ver=1, admin bumps to 2, request rejected,
        refresh allowed, new token with ver=2 succeeds.
        """
        app = _build_app()
        stale_payload = _make_payload(sub="user-123", token_version=1)
        fresh_payload = _make_payload(sub="user-123", token_version=2)

        mock_ts = _mock_token_service(payload=stale_payload)
        mock_ctx = _mock_async_session(token_version=2)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)

            # Step 1: Regular request with stale token → 401 TOKEN_STALE
            response = client.get("/", headers={"Authorization": "Bearer stale-jwt"})
            assert response.status_code == 401
            assert response.json()["code"] == "TOKEN_STALE"
            assert response.json()["retryable"] is True

            # Step 2: Refresh request with stale token → allowed through (exempted path)
            response = client.post("/api/v1/auth/refresh", headers={"Authorization": "Bearer stale-jwt"})
            assert response.status_code == 200

        # Step 3: Retry with fresh token (version matches DB) → 200 success
        mock_ts_fresh = _mock_token_service(payload=fresh_payload)
        mock_ctx_fresh = _mock_async_session(token_version=2)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx_fresh),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts_fresh),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer fresh-jwt"})
            assert response.status_code == 200

    @pytest.mark.parametrize(
        ("host_header", "description"),
        [
            ("evil@/api/v1/auth/refresh:real", "@ userinfo separator"),
            ("evil?/api/v1/auth/refresh", "? query-string shift"),
            ("evil#/api/v1/auth/refresh", "# fragment shift"),
        ],
    )
    def test_crafted_host_header_does_not_bypass_stale_rejection(self, host_header, description) -> None:
        """CVE-2026-48710: injected characters in Host header must not bypass stale-token rejection."""
        app = _build_app()
        payload = _make_payload(sub="user-123", token_version=1)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_async_session(token_version=5)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.get(
                "/",
                headers={"Authorization": "Bearer some-jwt", "Host": host_header},
            )

        assert response.status_code in {400, 401}, f"Expected 400 or 401 for {description}, got {response.status_code}"
        if response.status_code == 401:
            assert response.json()["code"] == "TOKEN_STALE"

    def test_impostor_logout_path_not_exempted(self) -> None:
        """A path that ends with /auth/logout but under a different prefix must NOT be exempted."""
        app = _build_app_with_impostor_routes()
        payload = _make_payload(sub="user-123", token_version=1)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_async_session(token_version=5)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.post("/some-other/auth/logout", headers={"Authorization": "Bearer some-jwt"})

        assert response.status_code == 401
        assert response.json()["code"] == "TOKEN_STALE"

    def test_impostor_refresh_path_not_exempted(self) -> None:
        """A path that ends with /auth/refresh but under a different prefix must NOT be exempted."""
        app = _build_app_with_impostor_routes()
        payload = _make_payload(sub="user-123", token_version=1)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_async_session(token_version=5)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.post("/some-other/auth/refresh", headers={"Authorization": "Bearer some-jwt"})

        assert response.status_code == 401
        assert response.json()["code"] == "TOKEN_STALE"


def _make_sa_payload(
    sub: str = "sa-456",
    token_version: int = 0,
    credential_id: str | None = None,
) -> TokenPayload:
    """Create a service account TokenPayload for testing."""
    now = datetime.now(UTC)
    return TokenPayload(
        sub=sub,
        iss="orchestrator",
        iat=now,
        exp=now,
        token_type="service_account",  # noqa: S106
        token_version=token_version,
        credential_id=credential_id,
    )


def _mock_sa_async_session(
    sa_status: str = "active",
    *,
    token_version: int = 0,
    not_found: bool = False,
) -> AsyncMock:
    """Create a mock AsyncSessionLocal that returns SA status rows."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    if not_found:
        mock_result.one_or_none.return_value = None
    else:
        mock_result.one_or_none.return_value = (sa_status, token_version)
    mock_session.exec.return_value = mock_result

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx


class TestStaleTokenMiddlewareSA:
    """Tests for StaleTokenMiddleware service account handling."""

    def setup_method(self) -> None:
        """Clear caches between tests."""
        _sa_status_cache.clear()
        _user_status_cache.clear()
        _cred_status_cache.clear()

    def test_active_sa_with_current_token_passes(self) -> None:
        """Active SA with matching token_ver and active credential passes through."""
        app = _build_app()
        payload = _make_sa_payload(sub="sa-456", token_version=1, credential_id="cred-001")

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_sa_async_session(sa_status="active", token_version=1)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
            patch("syntara.auth.middleware._check_cred_status", return_value=("active", None)),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer sa-jwt"})

        assert response.status_code == 200

    def test_disabled_sa_returns_401(self) -> None:
        """Disabled SA returns 401 SA_DISABLED."""
        app = _build_app()
        payload = _make_sa_payload(sub="sa-456", token_version=0)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_sa_async_session(sa_status="disabled", token_version=0)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer sa-jwt"})

        assert response.status_code == 401
        assert response.json()["code"] == "SA_DISABLED"

    def test_deleted_sa_returns_401(self) -> None:
        """Hard-deleted SA (not found in DB) returns 401 SA_DELETED."""
        app = _build_app()
        payload = _make_sa_payload(sub="sa-456", token_version=0)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_sa_async_session(not_found=True)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer sa-jwt"})

        assert response.status_code == 401
        assert response.json()["code"] == "SA_DELETED"

    def test_stale_sa_token_returns_401(self) -> None:
        """SA token with token_ver < DB version returns 401 SA_TOKEN_REVOKED."""
        app = _build_app()
        payload = _make_sa_payload(sub="sa-456", token_version=1)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_sa_async_session(sa_status="active", token_version=3)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer sa-jwt"})

        assert response.status_code == 401
        assert response.json()["code"] == "SA_TOKEN_REVOKED"
        assert response.json()["retryable"] is False

    def test_sa_not_found_returns_401(self) -> None:
        """SA not found in DB returns 401 SA_DELETED."""
        app = _build_app()
        payload = _make_sa_payload(sub="sa-nonexistent", token_version=0)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_sa_async_session(not_found=True)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer sa-jwt"})

        assert response.status_code == 401
        assert response.json()["code"] == "SA_DELETED"


class TestStaleTokenMiddlewareSACredential:
    """Tests for StaleTokenMiddleware SA credential-level checks."""

    def setup_method(self) -> None:
        """Clear caches between tests."""
        _sa_status_cache.clear()
        _user_status_cache.clear()
        _cred_status_cache.clear()

    def test_disabled_credential_returns_401(self) -> None:
        """Active SA with disabled credential returns 401 SA_CREDENTIAL_DISABLED."""
        app = _build_app()
        payload = _make_sa_payload(sub="sa-456", token_version=1, credential_id="cred-001")

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_sa_async_session(sa_status="active", token_version=1)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
            patch("syntara.auth.middleware._check_cred_status", return_value=("disabled", None)),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer sa-jwt"})

        assert response.status_code == 401
        assert response.json()["code"] == "SA_CREDENTIAL_DISABLED"

    def test_deleted_credential_returns_401(self) -> None:
        """Active SA with deleted credential (not found) returns 401 SA_CREDENTIAL_DISABLED."""
        app = _build_app()
        payload = _make_sa_payload(sub="sa-456", token_version=1, credential_id="cred-gone")

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_sa_async_session(sa_status="active", token_version=1)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
            patch("syntara.auth.middleware._check_cred_status", return_value=None),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer sa-jwt"})

        assert response.status_code == 401
        assert response.json()["code"] == "SA_CREDENTIAL_DISABLED"

    def test_active_credential_passes(self) -> None:
        """Active SA with active credential passes through."""
        app = _build_app()
        payload = _make_sa_payload(sub="sa-456", token_version=1, credential_id="cred-001")

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_sa_async_session(sa_status="active", token_version=1)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
            patch("syntara.auth.middleware._check_cred_status", return_value=("active", None)),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer sa-jwt"})

        assert response.status_code == 200

    def test_missing_cred_id_returns_401(self) -> None:
        """SA token without cred_id claim is rejected as SA_TOKEN_REVOKED and dispatches audit event."""
        app = _build_app()
        payload = _make_sa_payload(sub="sa-456", token_version=1, credential_id=None)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_sa_async_session(sa_status="active", token_version=1)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
            patch("syntara.audit.dispatcher.AuditEventDispatcher.dispatch") as mock_dispatch,
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer sa-jwt"})

        assert response.status_code == 401
        assert response.json()["code"] == "SA_TOKEN_REVOKED"
        mock_dispatch.assert_called_once()
        dispatched = mock_dispatch.call_args[0][0]
        from syntara.auth.audit.sa_rejection import MissingSACredentialClaimEvent

        assert isinstance(dispatched, MissingSACredentialClaimEvent)
        assert dispatched.service_account_id == "sa-456"

    def test_cred_check_failure_passes_through(self) -> None:
        """When credential status check raises, request passes through (fail-open)."""
        app = _build_app()
        payload = _make_sa_payload(sub="sa-456", token_version=1, credential_id="cred-001")

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_sa_async_session(sa_status="active", token_version=1)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
            patch("syntara.auth.middleware._check_cred_status", side_effect=OSError("connection refused")),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer sa-jwt"})

        assert response.status_code == 200

    def test_expired_credential_returns_401(self) -> None:
        """Active SA with expired credential returns 401 SA_CREDENTIAL_EXPIRED."""
        app = _build_app()
        payload = _make_sa_payload(sub="sa-456", token_version=1, credential_id="cred-001")
        past = datetime.now(UTC) - timedelta(minutes=5)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_sa_async_session(sa_status="active", token_version=1)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
            patch("syntara.auth.middleware._check_cred_status", return_value=("active", past)),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer sa-jwt"})

        assert response.status_code == 401
        assert response.json()["code"] == "SA_CREDENTIAL_EXPIRED"
        assert response.json()["detail"] == "Service account credential has expired"

    def test_expired_credential_dispatches_audit_event(self) -> None:
        """Expired credential rejection dispatches ExpiredSACredentialRejectionEvent."""
        app = _build_app()
        payload = _make_sa_payload(sub="sa-456", token_version=1, credential_id="cred-001")
        past = datetime.now(UTC) - timedelta(minutes=5)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_sa_async_session(sa_status="active", token_version=1)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
            patch("syntara.auth.middleware._check_cred_status", return_value=("active", past)),
            patch("syntara.audit.dispatcher.AuditEventDispatcher.dispatch") as mock_dispatch,
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer sa-jwt"})

        assert response.status_code == 401
        mock_dispatch.assert_called_once()
        dispatched = mock_dispatch.call_args[0][0]
        from syntara.auth.audit.sa_rejection import ExpiredSACredentialRejectionEvent

        assert isinstance(dispatched, ExpiredSACredentialRejectionEvent)
        assert dispatched.service_account_id == "sa-456"
        assert dispatched.credential_id == "cred-001"
        assert dispatched.expires_at == past

    def test_non_expired_credential_passes(self) -> None:
        """Active SA with non-expired credential (future expires_at) passes through."""
        app = _build_app()
        payload = _make_sa_payload(sub="sa-456", token_version=1, credential_id="cred-001")
        future = datetime.now(UTC) + timedelta(hours=1)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_sa_async_session(sa_status="active", token_version=1)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
            patch("syntara.auth.middleware._check_cred_status", return_value=("active", future)),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer sa-jwt"})

        assert response.status_code == 200

    def test_null_expires_at_passes(self) -> None:
        """Active SA with no expiration (expires_at=None) passes through."""
        app = _build_app()
        payload = _make_sa_payload(sub="sa-456", token_version=1, credential_id="cred-001")

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_sa_async_session(sa_status="active", token_version=1)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
            patch("syntara.auth.middleware._check_cred_status", return_value=("active", None)),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer sa-jwt"})

        assert response.status_code == 200

    def test_disabled_sa_takes_priority_over_credential(self) -> None:
        """Disabled SA rejection takes priority over credential check."""
        app = _build_app()
        payload = _make_sa_payload(sub="sa-456", token_version=1, credential_id="cred-001")

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_sa_async_session(sa_status="disabled", token_version=1)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer sa-jwt"})

        assert response.status_code == 401
        assert response.json()["code"] == "SA_DISABLED"

    def test_disabled_credential_takes_priority_over_expired(self) -> None:
        """Disabled credential rejection takes priority over expiration check."""
        app = _build_app()
        payload = _make_sa_payload(sub="sa-456", token_version=1, credential_id="cred-001")
        past = datetime.now(UTC) - timedelta(minutes=5)

        mock_ts = _mock_token_service(payload=payload)
        mock_ctx = _mock_sa_async_session(sa_status="active", token_version=1)

        with (
            patch("syntara.auth.middleware.AsyncSessionLocal", return_value=mock_ctx),
            patch("syntara.auth.middleware.TokenService", return_value=mock_ts),
            patch("syntara.auth.middleware._check_cred_status", return_value=("disabled", past)),
        ):
            client = TestClient(app)
            response = client.get("/", headers={"Authorization": "Bearer sa-jwt"})

        assert response.status_code == 401
        assert response.json()["code"] == "SA_CREDENTIAL_DISABLED"
