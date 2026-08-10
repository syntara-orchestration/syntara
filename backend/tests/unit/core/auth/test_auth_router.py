"""Unit tests for auth router endpoints: login, refresh, and logout."""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.events.function_execution import FunctionExecutionEvent, FunctionExecutionHandler
from syntara.auth.dependencies import get_refresh_token
from syntara.auth.exceptions import (
    AuthenticationRequiredError,
    CSRFErrorCode,
    CSRFValidationError,
    InvalidTokenError,
    OIDCCallbackError,
    OIDCErrorCode,
    RefreshTokenRevokedError,
    SessionStoreUnavailableError,
)
from syntara.auth.router import (
    get_csrf_token,
    login,
    logout,
    oidc_authorize,
    oidc_callback,
    refresh_token,
)
from syntara.auth.schemas import CsrfTokenResponse, LoginRequest
from syntara.auth.services.oidc_service import OIDCError
from syntara.auth.services.token_service import TokenPayload
from syntara.auth.session.session_store import SessionInfo
from syntara.core.models import User
from syntara.identity_providers.models.identity_provider_configuration import OIDCConfiguration


@pytest.fixture
def _mock_audit_dispatcher() -> Generator[MagicMock, None, None]:
    """Prevent AuditEventDispatcher.dispatch from having side effects during tests."""
    with patch("syntara.auth.router.AuditEventDispatcher.dispatch") as mock_dispatch:
        yield mock_dispatch


@pytest.fixture
def _mock_audit_emission() -> Generator[None, None, None]:
    """Prevent @audit emission side effects in unit tests."""
    with patch("syntara.audit.emitter.emit_audit_event"):
        yield


def _make_request(*, cookie_value: str | None = None) -> MagicMock:
    """Build a mock Request with optional refresh-token cookie."""
    request = MagicMock()
    cookies: dict[str, str] = {}
    if cookie_value is not None:
        cookies["ao_refresh_token"] = cookie_value
    request.cookies = cookies
    request.headers = MagicMock()
    request.headers.get = MagicMock(return_value="test-agent")
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    return request


def _make_response() -> MagicMock:
    """Build a mock Response."""
    return MagicMock()


def _make_payload(
    *,
    sub: str | None = None,
    jti: str = "jti-abc",
    preferred_username: str = "testuser",
    iat: datetime | None = None,
) -> TokenPayload:
    return TokenPayload(
        sub=sub or str(uuid4()),
        iss="http://localhost:8000",
        iat=iat or datetime.now(UTC),
        exp=datetime.now(UTC) + timedelta(hours=8),
        token_type="refresh",  # noqa: S106
        jti=jti,
        preferred_username=preferred_username,
        email=None,
        groups=None,
        amr=["pwd"],
        idp="local",
    )


def _make_user(
    *,
    user_id: str | None = None,
    is_enabled: bool = True,
    is_builtin: bool = False,
    password_hash: str | None = "$argon2id$v=19$m=65536,t=3,p=4$fakehash",  # noqa: S107
) -> User:
    return User(
        id=UUID(user_id) if user_id else uuid4(),
        username="testuser",
        email="test@example.com",
        first_name="Test",
        last_name="User",
        is_enabled=is_enabled,
        is_builtin=is_builtin,
        password_hash=password_hash,
    )


def _mock_runtime_settings(*, local_login_enabled: bool = True) -> MagicMock:
    """Build a mock for get_runtime_settings that returns a cache with get_bool configured."""
    mock_cache = AsyncMock()
    mock_cache.get_bool.return_value = local_login_enabled
    return MagicMock(return_value=mock_cache)


def _make_session(jti: str = "jti-abc") -> SessionInfo:
    return SessionInfo(
        jti=jti,
        user_id=str(uuid4()),
        issued_at=datetime.now(UTC),
        device=None,
        ip_address=None,
        ttl=3600,
    )


def _patch_session_store(mock_store: AsyncMock) -> MagicMock:
    """Create a patched SessionStore class that returns *mock_store*."""
    return MagicMock(return_value=mock_store)


# =============================================================================
# Login endpoint
# =============================================================================


@pytest.mark.usefixtures("_mock_audit_dispatcher", "_mock_audit_emission")
class TestLoginEndpoint:
    """Tests for the /auth/login endpoint."""

    @pytest.mark.asyncio
    async def test_login_success(self) -> None:
        """Login with valid credentials returns access token and sets cookies."""
        user = _make_user()
        request = _make_request()
        response = _make_response()
        body = LoginRequest(username="testuser", password="correct-password")  # noqa: S106

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        mock_token_service = MagicMock()
        mock_token_service.create_access_token.return_value = "access-token-123"
        mock_token_service.create_refresh_token.return_value = ("refresh-jwt", "jti-1", datetime.now(UTC))

        mock_store = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.jwt_refresh_token_lifetime_hours = 8
        mock_settings.jwt_access_token_lifetime_minutes = 15

        with (
            patch("syntara.auth.router._get_token_service", return_value=mock_token_service),
            patch("syntara.auth.router.verify_password", return_value=True),
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router.set_refresh_cookie") as mock_set_cookie,
            patch("syntara.auth.router.set_csrf_cookie") as mock_set_csrf,
            patch("syntara.auth.router.get_runtime_settings", _mock_runtime_settings()),
        ):
            result = await login(body, request, response, db)

        assert result.access_token == "access-token-123"  # noqa: S105
        assert result.expires_in == 900
        mock_set_cookie.assert_called_once()
        mock_set_csrf.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_sets_actor_context_for_last_login_audit(self) -> None:
        """Password login must attribute last_login CRUD to the user (AAP-83651)."""
        from syntara.audit.emitter import actor_context_var

        user = _make_user()
        request = _make_request()
        response = _make_response()
        body = LoginRequest(username="testuser", password="correct-password")  # noqa: S106

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        seen_actor_id = None

        async def _capture_commit() -> None:
            nonlocal seen_actor_id
            actor = actor_context_var.get()
            assert actor is not None
            seen_actor_id = actor.actor_id

        db.commit.side_effect = _capture_commit

        mock_token_service = MagicMock()
        mock_token_service.create_access_token.return_value = "access-token-123"
        mock_token_service.create_refresh_token.return_value = ("refresh-jwt", "jti-1", datetime.now(UTC))

        mock_settings = MagicMock()
        mock_settings.jwt_refresh_token_lifetime_hours = 8
        mock_settings.jwt_access_token_lifetime_minutes = 15

        with (
            patch("syntara.auth.router._get_token_service", return_value=mock_token_service),
            patch("syntara.auth.router.verify_password", return_value=True),
            patch("syntara.auth.router.create_session_store", _patch_session_store(AsyncMock())),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router.set_refresh_cookie"),
            patch("syntara.auth.router.set_csrf_cookie"),
            patch("syntara.auth.router.get_runtime_settings", _mock_runtime_settings()),
        ):
            await login(body, request, response, db)

        assert seen_actor_id == user.id

    @pytest.mark.asyncio
    async def test_login_normalizes_username_to_lowercase(self) -> None:
        """Login should normalize username to lowercase before DB lookup."""
        user = _make_user()
        request = _make_request()
        response = _make_response()
        body = LoginRequest(username="TestUser", password="correct-password")  # noqa: S106

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        mock_token_service = MagicMock()
        mock_token_service.create_access_token.return_value = "access-token-123"
        mock_token_service.create_refresh_token.return_value = ("refresh-jwt", "jti-1", datetime.now(UTC))

        mock_store = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.jwt_refresh_token_lifetime_hours = 8
        mock_settings.jwt_access_token_lifetime_minutes = 15

        with (
            patch("syntara.auth.router._get_token_service", return_value=mock_token_service),
            patch("syntara.auth.router.verify_password", return_value=True),
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router.set_refresh_cookie"),
            patch("syntara.auth.router.get_runtime_settings", _mock_runtime_settings()),
        ):
            result = await login(body, request, response, db)

        assert result.access_token == "access-token-123"  # noqa: S105

        # Verify the first DB query (user lookup) used the lowercased username
        stmt = db.exec.call_args_list[0][0][0]
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        assert "testuser" in str(compiled).lower()
        assert "TestUser" not in str(compiled)

    @pytest.mark.asyncio
    async def test_login_rejects_wrong_password(self) -> None:
        """Login with wrong password raises AuthenticationRequiredError."""
        user = _make_user()
        request = _make_request()
        response = _make_response()
        body = LoginRequest(username="testuser", password="wrong-password")  # noqa: S106

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        with (
            patch("syntara.auth.router.get_runtime_settings", _mock_runtime_settings()),
            patch("syntara.auth.router.verify_password", return_value=False),
            pytest.raises(AuthenticationRequiredError),
        ):
            await login(body, request, response, db)

    @pytest.mark.asyncio
    async def test_login_rejects_unknown_user(self) -> None:
        """Login with unknown username raises AuthenticationRequiredError."""
        request = _make_request()
        response = _make_response()
        body = LoginRequest(username="nobody", password="any")  # noqa: S106

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        with pytest.raises(AuthenticationRequiredError):
            await login(body, request, response, db)

    @pytest.mark.asyncio
    async def test_login_rejects_inactive_user(self) -> None:
        """Login for inactive user raises AuthenticationRequiredError."""
        user = _make_user(is_enabled=False)
        request = _make_request()
        response = _make_response()
        body = LoginRequest(username="testuser", password="correct")  # noqa: S106

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        with (
            patch("syntara.auth.router.get_runtime_settings", _mock_runtime_settings()),
            patch("syntara.auth.router.verify_password", return_value=True),
            pytest.raises(AuthenticationRequiredError),
        ):
            await login(body, request, response, db)

    @pytest.mark.asyncio
    async def test_login_rejects_user_without_password(self) -> None:
        """Login for federated-only user (no password_hash) raises AuthenticationRequiredError."""
        user = _make_user(password_hash=None)
        request = _make_request()
        response = _make_response()
        body = LoginRequest(username="testuser", password="any")  # noqa: S106

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        with pytest.raises(AuthenticationRequiredError):
            await login(body, request, response, db)

    @pytest.mark.asyncio
    async def test_login_rejects_non_builtin_user_when_local_login_disabled(self) -> None:
        """Non-builtin user is rejected before password verification when local login is disabled."""
        user = _make_user()
        request = _make_request()
        response = _make_response()
        body = LoginRequest(username="testuser", password="any")  # noqa: S106

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        with (
            patch("syntara.auth.router.verify_password") as mock_verify,
            patch("syntara.auth.router.get_runtime_settings", _mock_runtime_settings(local_login_enabled=False)),
            pytest.raises(AuthenticationRequiredError),
        ):
            await login(body, request, response, db)

        mock_verify.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("local_login_enabled", [True, False], ids=["setting_enabled", "setting_disabled"])
    async def test_login_allows_builtin_user_regardless_of_setting(self, *, local_login_enabled: bool) -> None:
        """Built-in user can login regardless of authentication.local_login_enabled value."""
        user = _make_user(is_builtin=True)
        request = _make_request()
        response = _make_response()
        body = LoginRequest(username="testuser", password="correct-password")  # noqa: S106

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        mock_token_service = MagicMock()
        mock_token_service.create_access_token.return_value = "access-token-123"
        mock_token_service.create_refresh_token.return_value = ("refresh-jwt", "jti-1", datetime.now(UTC))

        mock_store = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.jwt_refresh_token_lifetime_hours = 8
        mock_settings.jwt_access_token_lifetime_minutes = 15

        with (
            patch("syntara.auth.router._get_token_service", return_value=mock_token_service),
            patch("syntara.auth.router.verify_password", return_value=True),
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router.set_refresh_cookie"),
            patch(
                "syntara.auth.router.get_runtime_settings",
                _mock_runtime_settings(local_login_enabled=local_login_enabled),
            ),
        ):
            result = await login(body, request, response, db)

        assert result.access_token == "access-token-123"  # noqa: S105

    @pytest.mark.asyncio
    async def test_login_dispatches_local_login_disabled_audit_event(self) -> None:
        """Audit event with LOCAL_LOGIN_DISABLED reason is dispatched when setting denies login."""
        from syntara.auth.audit.login_attempt import LoginAttemptEvent, LoginErrorReason

        user = _make_user()
        request = _make_request()
        response = _make_response()
        body = LoginRequest(username="testuser", password="any")  # noqa: S106

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        with (
            patch("syntara.auth.router.get_runtime_settings", _mock_runtime_settings(local_login_enabled=False)),
            patch("syntara.auth.router.AuditEventDispatcher.dispatch") as mock_dispatch,
            pytest.raises(AuthenticationRequiredError),
        ):
            await login(body, request, response, db)

        dispatched_events = [call.args[0] for call in mock_dispatch.call_args_list]
        local_login_events = [
            e
            for e in dispatched_events
            if isinstance(e, LoginAttemptEvent) and e.error_type == LoginErrorReason.LOCAL_LOGIN_DISABLED
        ]
        assert len(local_login_events) == 1
        assert local_login_events[0].user_id == user.id

    @pytest.mark.asyncio
    async def test_login_raises_503_when_session_store_unavailable(self) -> None:
        """Login should raise SessionStoreUnavailableError when DB is down."""
        user = _make_user()
        request = _make_request()
        response = _make_response()
        body = LoginRequest(username="testuser", password="correct-password")  # noqa: S106

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        mock_token_service = MagicMock()
        mock_token_service.create_access_token.return_value = "access-token-123"
        mock_token_service.create_refresh_token.return_value = ("refresh-jwt", "jti-1", datetime.now(UTC))

        # SessionStore is now a plain class; create raises SQLAlchemyError.
        from sqlalchemy.exc import SQLAlchemyError

        mock_store = AsyncMock()
        mock_store.get_token_version = AsyncMock(return_value=1)
        mock_store.create = AsyncMock(side_effect=SQLAlchemyError("DB connection failed"))

        with (
            patch("syntara.auth.router._get_token_service", return_value=mock_token_service),
            patch("syntara.auth.router.verify_password", return_value=True),
            patch("syntara.auth.router._get_user_group_names", return_value=["authenticated"]),
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            patch("syntara.auth.router.get_runtime_settings", _mock_runtime_settings()),
            pytest.raises(SessionStoreUnavailableError),
        ):
            await login(body, request, response, db)

        db.rollback.assert_not_called()


# =============================================================================
# get_refresh_token dependency
# =============================================================================


@pytest.mark.usefixtures("_mock_audit_dispatcher", "_mock_audit_emission")
class TestGetRefreshTokenDependency:
    """Tests for the get_refresh_token dependency."""

    @pytest.mark.asyncio
    async def test_raises_when_no_cookie(self) -> None:
        """Should raise AuthenticationRequiredError when cookie is missing."""
        request = _make_request(cookie_value=None)

        with patch("syntara.auth.csrf.validate_csrf"), pytest.raises(AuthenticationRequiredError):
            await get_refresh_token(request, db=AsyncMock())

    @pytest.mark.asyncio
    async def test_returns_payload_when_cookie_present(self) -> None:
        """Should return the decoded TokenPayload when cookie exists."""
        request = _make_request(cookie_value="the-refresh-jwt")
        payload = _make_payload()

        mock_token_service = MagicMock()
        mock_token_service.decode_token.return_value = payload

        with (
            patch("syntara.auth.csrf.validate_csrf"),
            patch("syntara.auth.dependencies._get_token_service", return_value=mock_token_service),
            patch("syntara.auth.services.global_revocation.is_token_globally_revoked", return_value=None),
        ):
            result = await get_refresh_token(request, db=AsyncMock())

        assert result is payload
        mock_token_service.decode_token.assert_called_once_with("the-refresh-jwt", token_type="refresh")  # noqa: S106

    @pytest.mark.asyncio
    async def test_raises_on_invalid_token(self) -> None:
        """Should re-raise InvalidTokenError from decode_token."""
        request = _make_request(cookie_value="bad-token")

        mock_token_service = MagicMock()
        mock_token_service.decode_token.side_effect = InvalidTokenError

        with (
            patch("syntara.auth.csrf.validate_csrf"),
            patch("syntara.auth.dependencies._get_token_service", return_value=mock_token_service),
            pytest.raises(InvalidTokenError),
        ):
            await get_refresh_token(request, db=AsyncMock())

    @pytest.mark.asyncio
    async def test_raises_auth_required_on_unexpected_decode_error(self) -> None:
        """Should raise AuthenticationRequiredError on unexpected decode errors."""
        request = _make_request(cookie_value="bad-token")

        mock_token_service = MagicMock()
        mock_token_service.decode_token.side_effect = RuntimeError("unexpected")

        with (
            patch("syntara.auth.csrf.validate_csrf"),
            patch("syntara.auth.dependencies._get_token_service", return_value=mock_token_service),
            pytest.raises(AuthenticationRequiredError),
        ):
            await get_refresh_token(request, db=AsyncMock())

    @pytest.mark.asyncio
    async def test_raises_on_globally_revoked_token(self) -> None:
        """Should raise TokenGloballyRevokedError when token was issued before revocation timestamp."""
        from syntara.auth.exceptions import TokenGloballyRevokedError

        request = _make_request(cookie_value="the-refresh-jwt")
        payload = _make_payload()

        mock_token_service = MagicMock()
        mock_token_service.decode_token.return_value = payload

        with (
            patch("syntara.auth.csrf.validate_csrf"),
            patch("syntara.auth.dependencies._get_token_service", return_value=mock_token_service),
            patch(
                "syntara.auth.services.global_revocation.is_token_globally_revoked",
                return_value=datetime.now(UTC),
            ),
            pytest.raises(TokenGloballyRevokedError),
        ):
            await get_refresh_token(request, db=AsyncMock())


# =============================================================================
# CSRF token endpoint
# =============================================================================


class TestGetCsrfTokenEndpoint:
    """Tests for the POST /auth/csrf_token endpoint."""

    @pytest.mark.asyncio
    async def test_returns_csrf_form_token(self) -> None:
        """Should derive and return the CSRF form token from the cookie seed."""
        request = _make_request()
        request.cookies = {"ao_csrf_token": "the-seed"}

        with patch("syntara.auth.router.derive_csrf_form_token", return_value="derived-token"):
            result = await get_csrf_token(request)

        assert result == CsrfTokenResponse(csrf_token="derived-token")  # noqa: S106

    @pytest.mark.asyncio
    async def test_raises_when_cookie_missing(self) -> None:
        """Should raise CSRFValidationError when the CSRF cookie is absent."""
        request = _make_request()
        request.cookies = {}

        with pytest.raises(CSRFValidationError, match="CSRF cookie missing") as exc_info:
            await get_csrf_token(request)
        assert exc_info.value.error_code == CSRFErrorCode.COOKIE_MISSING


# =============================================================================
# Refresh endpoint
# =============================================================================


@pytest.mark.usefixtures("_mock_audit_dispatcher", "_mock_audit_emission")
class TestRefreshEndpoint:
    """Tests for the /auth/refresh endpoint.

    The ``get_refresh_token`` dependency now handles cookie extraction,
    token decoding, and global revocation checking.  These tests pass
    a pre-built ``TokenPayload`` directly to the endpoint function.
    """

    @pytest.mark.asyncio
    async def test_raises_when_session_not_in_store(self) -> None:
        """Refresh should raise RefreshTokenRevokedError when JTI not in session store."""
        db = AsyncMock()
        payload = _make_payload()

        mock_store = AsyncMock()
        mock_store.get_with_token_version.return_value = None

        with (
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            pytest.raises(RefreshTokenRevokedError),
        ):
            await refresh_token(MagicMock(), MagicMock(), payload, db)

    @pytest.mark.asyncio
    async def test_raises_when_user_not_found(self) -> None:
        """Refresh should raise AuthenticationRequiredError if user is not in DB."""
        payload = _make_payload()

        mock_store = AsyncMock()
        mock_store.get_with_token_version.return_value = (_make_session(), 0)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        with (
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            pytest.raises(AuthenticationRequiredError),
        ):
            await refresh_token(MagicMock(), MagicMock(), payload, db)

    @pytest.mark.asyncio
    async def test_raises_when_user_inactive(self) -> None:
        """Refresh should raise AuthenticationRequiredError if user is inactive."""
        user = _make_user(is_enabled=False)
        payload = _make_payload(sub=str(user.id))

        mock_store = AsyncMock()
        mock_store.get_with_token_version.return_value = (_make_session(), 0)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        with (
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            pytest.raises(AuthenticationRequiredError),
        ):
            await refresh_token(MagicMock(), MagicMock(), payload, db)

    @pytest.mark.asyncio
    async def test_success_returns_access_token(self) -> None:
        """Successful refresh returns AccessTokenResponse."""
        user = _make_user()
        payload = _make_payload(sub=str(user.id))

        mock_token_service = MagicMock()
        mock_token_service.create_access_token.return_value = "new-access-token"

        mock_store = AsyncMock()
        mock_store.get_with_token_version.return_value = (_make_session(), 0)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        mock_settings = MagicMock()
        mock_settings.jwt_refresh_token_lifetime_hours = 8
        mock_settings.jwt_access_token_lifetime_minutes = 15

        with (
            patch("syntara.auth.router._get_token_service", return_value=mock_token_service),
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
        ):
            result = await refresh_token(MagicMock(), MagicMock(), payload, db)

        assert result.access_token == "new-access-token"  # noqa: S105
        assert result.expires_in == 900  # 15 * 60
        assert result.token_type == "Bearer"  # noqa: S105

    @pytest.mark.asyncio
    async def test_raises_503_when_session_store_unavailable(self) -> None:
        """Refresh should raise SessionStoreUnavailableError when DB is down."""
        from sqlalchemy.exc import SQLAlchemyError

        db = AsyncMock()
        payload = _make_payload()

        mock_store = AsyncMock()
        mock_store.get_with_token_version.side_effect = SQLAlchemyError("DB connection failed")

        with (
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            pytest.raises(SessionStoreUnavailableError),
        ):
            await refresh_token(MagicMock(), MagicMock(), payload, db)

    @pytest.mark.asyncio
    async def test_refresh_preserves_amr_and_idp(self) -> None:
        """Refresh should carry forward the amr and idp claims from the original token."""
        user = _make_user()
        payload = _make_payload(sub=str(user.id))
        payload.amr = ["fed", "mfa"]
        payload.idp = "azure-ad-prod"

        mock_token_service = MagicMock()
        mock_token_service.create_access_token.return_value = "new-access-token"

        mock_store = AsyncMock()
        mock_store.get_with_token_version.return_value = (_make_session(), 0)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        mock_settings = MagicMock()
        mock_settings.jwt_refresh_token_lifetime_hours = 8
        mock_settings.jwt_access_token_lifetime_minutes = 15

        with (
            patch("syntara.auth.router._get_token_service", return_value=mock_token_service),
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
        ):
            await refresh_token(MagicMock(), MagicMock(), payload, db)

        # Verify amr and idp were passed through to create_access_token
        call_kwargs = mock_token_service.create_access_token.call_args
        assert call_kwargs.kwargs["amr"] == ["fed", "mfa"]
        assert call_kwargs.kwargs["idp"] == "azure-ad-prod"


# =============================================================================
# Logout endpoint
# =============================================================================


@pytest.mark.usefixtures("_mock_audit_dispatcher", "_mock_audit_emission")
class TestLogoutEndpoint:
    """Tests for the /auth/logout endpoint.

    The ``get_refresh_token`` dependency now handles cookie extraction,
    token decoding, and global revocation checking.  These tests pass
    a pre-built ``TokenPayload`` directly to the endpoint function.
    """

    @pytest.mark.asyncio
    async def test_clears_cookie_when_jti_missing(self) -> None:
        """Logout should clear cookie and raise when payload has no JTI."""
        request = _make_request()
        response = _make_response()
        db = AsyncMock()

        payload = _make_payload(jti="")
        payload.jti = None

        with (
            patch("syntara.auth.router.clear_refresh_cookie") as mock_clear,
            pytest.raises(AuthenticationRequiredError),
        ):
            await logout(payload, request, response, db)

        mock_clear.assert_called_once_with(response)

    @pytest.mark.asyncio
    async def test_success_revokes_session_and_clears_cookies(self) -> None:
        """Successful logout revokes session, increments token version, and clears refresh + CSRF cookies."""
        request = _make_request()
        response = _make_response()
        db = AsyncMock()

        payload = _make_payload(jti="jti-123")

        mock_store = AsyncMock()
        mock_store.get.return_value = None  # No session metadata (local logout)
        mock_store.revoke.return_value = True

        with (
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            patch("syntara.auth.router.clear_refresh_cookie") as mock_clear,
            patch("syntara.auth.router.clear_csrf_cookie") as mock_clear_csrf,
        ):
            result = await logout(payload, request, response, db)

        assert result == {"detail": "Successfully logged out"}
        mock_store.revoke.assert_called_once_with("jti-123")
        mock_store.increment_token_version.assert_called_once_with(UUID(payload.sub))
        mock_clear.assert_called_once_with(response)
        mock_clear_csrf.assert_called_once_with(response)

    @pytest.mark.asyncio
    async def test_raises_503_when_session_store_unavailable(self) -> None:
        """Logout should raise SessionStoreUnavailableError when DB is down."""
        from sqlalchemy.exc import SQLAlchemyError

        response = _make_response()
        payload = _make_payload(jti="jti-123")

        mock_store = AsyncMock()
        mock_store.get.side_effect = SQLAlchemyError("DB connection failed")

        with (
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            pytest.raises(SessionStoreUnavailableError),
        ):
            await logout(payload, _make_request(), response, AsyncMock())

    @pytest.mark.asyncio
    async def test_success_when_session_already_expired(self) -> None:
        """Logout succeeds even when session was already expired in session store."""
        request = _make_request()
        response = _make_response()
        db = AsyncMock()

        payload = _make_payload(jti="jti-456")

        mock_store = AsyncMock()
        mock_store.get.return_value = None  # No session metadata
        mock_store.revoke.return_value = False  # already expired

        with (
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            patch("syntara.auth.router.clear_refresh_cookie") as mock_clear,
        ):
            result = await logout(payload, request, response, db)

        assert result == {"detail": "Successfully logged out"}
        mock_store.increment_token_version.assert_called_once_with(UUID(payload.sub))
        mock_clear.assert_called_once_with(response)

    @pytest.mark.asyncio
    async def test_logout_increments_token_version(self) -> None:
        """Logout must increment token_version to invalidate outstanding access tokens."""
        request = _make_request()
        response = _make_response()
        db = AsyncMock()

        user_id = str(uuid4())
        payload = _make_payload(jti="jti-ver", sub=user_id)

        mock_store = AsyncMock()
        mock_store.get.return_value = None
        mock_store.revoke.return_value = True
        mock_store.increment_token_version.return_value = 1

        with (
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            patch("syntara.auth.router.clear_refresh_cookie"),
        ):
            await logout(payload, request, response, db)

        mock_store.increment_token_version.assert_called_once_with(UUID(user_id))

    @pytest.mark.asyncio
    async def test_logout_sets_actor_context_for_token_version_audit(self) -> None:
        """Logout must establish actor ContextVars before token_version bump (AAP-83651).

        Refresh-cookie logout has no Bearer JWT for audit middleware; without an
        explicit actor_context, CRUD audit for token_version stays null-actor.
        """
        from syntara.audit.emitter import actor_context_var

        request = _make_request()
        response = _make_response()
        db = AsyncMock()
        user_id = str(uuid4())
        payload = _make_payload(jti="jti-actor", sub=user_id, preferred_username="logout-user")

        seen_actor_id: UUID | None = None
        seen_username: str | None = None

        async def _capture_increment(uid: UUID) -> int:
            nonlocal seen_actor_id, seen_username
            actor = actor_context_var.get()
            assert actor is not None
            seen_actor_id = actor.actor_id
            seen_username = actor.actor_username
            return 1

        mock_store = AsyncMock()
        mock_store.get.return_value = None
        mock_store.revoke.return_value = True
        mock_store.increment_token_version.side_effect = _capture_increment

        with (
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            patch("syntara.auth.router.clear_refresh_cookie"),
        ):
            await logout(payload, request, response, db)

        assert seen_actor_id == UUID(user_id)
        assert seen_username == "logout-user"

    @pytest.mark.asyncio
    async def test_rp_logout_returns_auth_error_when_endpoint_unresolvable(self) -> None:
        """When RP-initiated logout is enabled but end_session_endpoint can't be resolved, return auth_error in JSON."""
        request = _make_request()
        response = _make_response()
        db = AsyncMock()

        payload = _make_payload(jti="jti-rp")

        mock_store = AsyncMock()
        mock_store.get.return_value = SessionInfo(
            jti="jti-rp",
            user_id=str(uuid4()),
            issued_at=datetime.now(UTC),
            device=None,
            ip_address=None,
            ttl=3600,
            idp_id=str(uuid4()),
            idp="oidc",
        )
        mock_store.revoke.return_value = True

        rp_info = {"auth_error": "Logged out of Syntara, but could not log out of Test IdP."}

        with (
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            patch("syntara.auth.router.clear_refresh_cookie"),
            patch("syntara.auth.router._maybe_rp_logout", return_value=rp_info),
        ):
            result = await logout(payload, request, response, db)

        assert result["detail"] == "Successfully logged out"
        assert "could not log out" in result["auth_error"]

    @pytest.mark.asyncio
    async def test_rp_logout_returns_redirect_url_on_success(self) -> None:
        """When RP-initiated logout succeeds, return redirect_url in JSON response."""
        request = _make_request()
        response = _make_response()
        db = AsyncMock()

        payload = _make_payload(jti="jti-rp")

        mock_store = AsyncMock()
        mock_store.get.return_value = SessionInfo(
            jti="jti-rp",
            user_id=str(uuid4()),
            issued_at=datetime.now(UTC),
            device=None,
            ip_address=None,
            ttl=3600,
            idp_id=str(uuid4()),
            idp="oidc",
        )
        mock_store.revoke.return_value = True

        rp_info = {
            "redirect_url": "https://idp.example.com/logout?id_token_hint=abc&post_logout_redirect_uri=https://app.example.com"
        }

        with (
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            patch("syntara.auth.router.clear_refresh_cookie"),
            patch("syntara.auth.router._maybe_rp_logout", return_value=rp_info),
        ):
            result = await logout(payload, request, response, db)

        assert result["detail"] == "Successfully logged out"
        assert (
            result["redirect_url"]
            == "https://idp.example.com/logout?id_token_hint=abc&post_logout_redirect_uri=https://app.example.com"
        )
        assert "auth_error" not in result


# =============================================================================
# RP-initiated logout helper
# =============================================================================


class TestMaybeRpLogout:
    """Tests for _maybe_rp_logout helper."""

    @pytest.mark.asyncio
    async def test_returns_none_for_local_session(self) -> None:
        """Should return None when session has no idp_id (local session)."""
        from syntara.auth.router import _maybe_rp_logout

        session_info = SessionInfo(
            jti="jti-local",
            user_id=str(uuid4()),
            issued_at=datetime.now(UTC),
            device=None,
            ip_address=None,
            ttl=3600,
        )

        db = AsyncMock()
        result = await _maybe_rp_logout(db, session_info, "https://app.example.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_session(self) -> None:
        """Should return None when session_info is None."""
        from syntara.auth.router import _maybe_rp_logout

        db = AsyncMock()
        result = await _maybe_rp_logout(db, None, "https://app.example.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_auth_error_when_endpoint_unresolvable(self) -> None:
        """Should return dict with auth_error error code when end_session_endpoint can't be resolved."""
        from syntara.auth.router import _maybe_rp_logout
        from syntara.identity_providers.models.identity_provider import IdentityProvider
        from syntara.identity_providers.models.identity_provider_configuration import OIDCConfiguration

        idp_id = uuid4()
        config = OIDCConfiguration(
            issuer_url="https://idp.example.com",
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
            redirect_uri="https://app.example.com/callback",
            enable_rp_initiated_logout=True,
            auto_discovery=False,
            authorization_endpoint="https://idp.example.com/auth",
            token_endpoint="https://idp.example.com/token",  # noqa: S106
            jwks_uri="https://idp.example.com/jwks",
            end_session_endpoint=None,
        )
        provider = IdentityProvider(
            id=idp_id,
            name="Test IdP",
            slug="test-idp",
            configuration=config,
        )

        session_info = SessionInfo(
            jti="jti-rp",
            user_id=str(uuid4()),
            issued_at=datetime.now(UTC),
            device=None,
            ip_address=None,
            ttl=3600,
            idp_id=str(idp_id),
            idp="oidc",
        )

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = provider

        db = AsyncMock()
        db.exec.return_value = mock_result

        result = await _maybe_rp_logout(db, session_info, "https://app.example.com")

        assert result == {"auth_error": "idp_logout_failed"}

    @pytest.mark.asyncio
    async def test_returns_redirect_url_when_endpoint_available(self) -> None:
        """Should return dict with redirect_url when end_session_endpoint is available."""
        from syntara.auth.router import _maybe_rp_logout
        from syntara.identity_providers.models.identity_provider import IdentityProvider
        from syntara.identity_providers.models.identity_provider_configuration import OIDCConfiguration

        idp_id = uuid4()
        config = OIDCConfiguration(
            issuer_url="https://idp.example.com",
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
            redirect_uri="https://app.example.com/callback",
            enable_rp_initiated_logout=True,
            auto_discovery=False,
            authorization_endpoint="https://idp.example.com/auth",
            token_endpoint="https://idp.example.com/token",  # noqa: S106
            jwks_uri="https://idp.example.com/jwks",
            end_session_endpoint="https://idp.example.com/logout",
        )
        provider = IdentityProvider(
            id=idp_id,
            name="Test IdP",
            slug="test-idp",
            configuration=config,
        )

        session_info = SessionInfo(
            jti="jti-rp",
            user_id=str(uuid4()),
            issued_at=datetime.now(UTC),
            device=None,
            ip_address=None,
            ttl=3600,
            idp_id=str(idp_id),
            idp="oidc",
        )

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = provider

        db = AsyncMock()
        db.exec.return_value = mock_result

        result = await _maybe_rp_logout(db, session_info, "https://app.example.com")

        assert result is not None
        assert "redirect_url" in result
        assert "https://idp.example.com/logout" in result["redirect_url"]
        assert "post_logout_redirect_uri=https%3A%2F%2Fapp.example.com" in result["redirect_url"]


# =============================================================================
# Get Me endpoint
# =============================================================================


@pytest.mark.usefixtures("_mock_audit_dispatcher", "_mock_audit_emission")
class TestGetMeEndpoint:
    """Tests for the /auth/me endpoint."""

    @pytest.mark.asyncio
    async def test_returns_user_info_from_payload(self) -> None:
        """get_me should return UserInfo populated from token claims."""
        from syntara.auth.router import get_me

        user_id = str(uuid4())
        payload = _make_payload(sub=user_id, preferred_username="alice")
        payload.email = "alice@example.com"
        payload.groups = ["engineering", "admins"]
        payload.token_type = "access"  # noqa: S105

        request = _make_request()  # No refresh token in cookie

        result = await get_me(request, payload, AsyncMock())

        assert result.id == user_id
        assert result.username == "alice"
        assert result.email == "alice@example.com"
        assert result.groups == ["engineering", "admins"]
        assert result.rp_logout_enabled is False  # No refresh token, so RP logout disabled

    @pytest.mark.asyncio
    async def test_handles_none_optional_fields(self) -> None:
        """get_me should handle None optional claims gracefully."""
        from syntara.auth.router import get_me

        payload = _make_payload()
        payload.preferred_username = None
        payload.email = None
        payload.groups = None

        request = _make_request()  # No refresh token in cookie

        result = await get_me(request, payload, AsyncMock())

        assert result.username == ""
        assert result.email is None
        assert result.groups == []
        assert result.rp_logout_enabled is False  # No refresh token

    @pytest.mark.asyncio
    @patch("syntara.auth.router.create_session_store")
    @patch("syntara.auth.router._get_token_service")
    async def test_rp_logout_enabled_true(
        self,
        mock_token_svc: MagicMock,
        mock_session_store_cls: MagicMock,
    ) -> None:
        """get_me should return rp_logout_enabled=True when session has it set."""
        from syntara.auth.router import get_me
        from syntara.auth.session.session_store import SessionInfo

        user_id = str(uuid4())
        payload = _make_payload(sub=user_id, preferred_username="alice")
        payload.email = "alice@example.com"
        payload.groups = ["engineering"]
        payload.token_type = "access"  # noqa: S105

        # Mock refresh token in cookie
        request = _make_request(cookie_value="fake-refresh-token")

        # Mock token decode
        refresh_payload = _make_payload(sub=user_id, jti="session-jti")
        mock_token_svc.return_value.decode_token.return_value = refresh_payload

        # Mock session store returning session with rp_logout_enabled=True
        session = SessionInfo(
            jti="session-jti",
            user_id=user_id,
            issued_at=datetime.now(UTC),
            device="test-agent",
            ip_address="127.0.0.1",
            rp_logout_enabled=True,
        )
        mock_store = AsyncMock()
        mock_store.get.return_value = session
        mock_session_store_cls.return_value = mock_store

        result = await get_me(request, payload, AsyncMock())

        assert result.rp_logout_enabled is True


@pytest.mark.usefixtures("_mock_audit_dispatcher", "_mock_audit_emission")
class TestVerifyIdpTestPermission:
    """Tests for _verify_idp_test_permission session revocation check."""

    @pytest.mark.asyncio
    @patch("syntara.auth.router.create_session_store")
    @patch("syntara.auth.router._get_token_service")
    @patch("syntara.auth.router.get_refresh_token_from_cookie")
    async def test_raises_when_session_revoked(
        self,
        mock_cookie: MagicMock,
        mock_token_svc: MagicMock,
        mock_session_store_cls: MagicMock,
    ) -> None:
        """Should raise OIDCError when the refresh token session has been revoked."""
        from syntara.auth.router import _verify_idp_test_permission

        mock_cookie.return_value = "fake-refresh-token"
        payload = _make_payload(jti="revoked-jti")
        mock_token_svc.return_value.decode_token.return_value = payload

        mock_store = AsyncMock()
        mock_store.get.return_value = None  # Session revoked
        mock_session_store_cls.return_value = mock_store

        request = _make_request(cookie_value="fake-refresh-token")
        db = AsyncMock()

        with pytest.raises(OIDCError, match="Session expired or revoked"):
            await _verify_idp_test_permission(request, db)

    @pytest.mark.asyncio
    @patch("syntara.auth.router.get_authz_evaluator")
    @patch("syntara.auth.router.authorize", new_callable=AsyncMock)
    @patch("syntara.auth.router._find_non_deleted_user", new_callable=AsyncMock)
    @patch("syntara.auth.router.create_session_store")
    @patch("syntara.auth.router._get_token_service")
    @patch("syntara.auth.router.get_refresh_token_from_cookie")
    async def test_proceeds_when_session_active(
        self,
        mock_cookie: MagicMock,
        mock_token_svc: MagicMock,
        mock_session_store_cls: MagicMock,
        mock_find_user: AsyncMock,
        mock_authorize: AsyncMock,
        mock_evaluator: MagicMock,
    ) -> None:
        """Should not raise when session is active and user has permission."""
        from syntara.auth.router import _verify_idp_test_permission

        mock_cookie.return_value = "fake-refresh-token"
        user_id = str(uuid4())
        payload = _make_payload(sub=user_id, jti="active-jti")
        mock_token_svc.return_value.decode_token.return_value = payload

        session = SessionInfo(
            jti="active-jti",
            user_id=user_id,
            issued_at=datetime.now(UTC),
            device="test",
            ip_address="127.0.0.1",
        )
        mock_store = AsyncMock()
        mock_store.get.return_value = session
        mock_session_store_cls.return_value = mock_store

        mock_user = MagicMock()
        mock_user.id = UUID(user_id)
        mock_user.labels = {}
        mock_user.authz_metadata = {}
        mock_find_user.return_value = mock_user

        mock_authz_result = MagicMock()
        mock_authz_result.allowed = True
        mock_authorize.return_value = mock_authz_result

        request = _make_request(cookie_value="fake-refresh-token")
        db = AsyncMock()

        # Should not raise
        await _verify_idp_test_permission(request, db)


@pytest.mark.usefixtures("_mock_audit_dispatcher", "_mock_audit_emission")
class TestResolveAndLoginUserRollback:
    """Tests for rollback behavior when group matching denies login."""

    @pytest.mark.asyncio
    @patch("syntara.auth.router.sync_idp_groups", new_callable=AsyncMock)
    @patch("syntara.auth.router._resolve_oidc_user", new_callable=AsyncMock)
    async def test_rollback_on_no_group_match(
        self,
        mock_resolve: AsyncMock,
        mock_sync: AsyncMock,
    ) -> None:
        """Should call db.rollback() when no groups matched and user has no other groups."""
        from syntara.auth.router import _resolve_and_login_user
        from syntara.identity_providers.models.identity_provider import IdentityProvider

        user = User(id=uuid4(), username="testuser", email="t@t.com", first_name="Test", is_enabled=True)
        identity = MagicMock()
        mock_resolve.return_value = (user, identity)
        mock_sync.return_value = False  # No groups matched

        db = AsyncMock()
        # The flush succeeds, but the subsequent group check returns no rows
        other_groups_result = MagicMock()
        other_groups_result.first.return_value = None
        db.exec.return_value = other_groups_result

        provider = MagicMock(spec=IdentityProvider)
        provider.name = "TestIdP"
        provider.configuration = OIDCConfiguration(
            provider_type="oidc",
            issuer_url="https://idp.example.com",
            client_id="client-id",
            client_secret="secret",  # noqa: S106
            redirect_uri="http://localhost:8000/callback",
        )

        with pytest.raises(OIDCCallbackError):
            await _resolve_and_login_user(db, {"email": "t@t.com", "sub": "sub-1"}, {}, provider, None)

        db.rollback.assert_called_once()


class TestLoginAuditEvents:
    """Tests for audit event emission during login.

    These tests use a real AuditEventDispatcher with real handlers (no mock
    fixtures) so the full event pipeline runs end-to-end. Events are captured
    at the lowest level (_do_emit_audit_event) to verify ordering.
    """

    def setup_method(self) -> None:
        from syntara.auth.audit.login_attempt import (
            LoginAttemptEvent,
            LoginAttemptHandler,
        )
        from syntara.auth.audit.session_lifecycle import (
            SessionLifecycleEvent,
            SessionLifecycleHandler,
        )

        AuditEventDispatcher.register(
            {
                LoginAttemptEvent: LoginAttemptHandler(),
                SessionLifecycleEvent: SessionLifecycleHandler(),
                FunctionExecutionEvent: FunctionExecutionHandler(),
            }
        )

    @pytest.mark.asyncio
    @patch("syntara.auth.router.get_runtime_settings", _mock_runtime_settings())
    @patch("syntara.auth.router._get_token_service")
    @patch("syntara.auth.router.create_session_store")
    @patch("syntara.auth.router._get_user_group_names", new_callable=AsyncMock)
    @patch("syntara.auth.router.verify_password", return_value=True)
    async def test_successful_login_emits_all_events_in_order(
        self,
        mock_verify: MagicMock,
        mock_groups: AsyncMock,
        mock_session_store: MagicMock,
        mock_token_svc: MagicMock,
    ) -> None:
        """Happy login flow emits all audit events in correct chronological order.

        Expected order:
        1. SessionLifecycleEvent -> "session_created" (USER_ACTION, SUCCESS)
        2. LoginAttemptEvent -> "login" (USER_ACTION, SUCCESS, error_type=None)
        3. @audit "login" (SECURITY_EVENT, SUCCESS)

        Note: UserLoginEvent is also dispatched but its handler may not be
        registered in all test contexts, so it is not counted here.
        """
        from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventStatus
        from syntara.audit.models.structured_data import AuditContextData

        user = _make_user()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        mock_db.exec = AsyncMock(return_value=mock_result)

        mock_groups.return_value = ["authenticated"]

        mock_store_instance = AsyncMock()
        mock_store_instance.get_token_version = AsyncMock(return_value=1)
        mock_store_instance.create = AsyncMock()
        mock_session_store.return_value = mock_store_instance

        mock_token_svc.return_value.create_access_token.return_value = "access-token"
        mock_token_svc.return_value.create_refresh_token.return_value = ("refresh-token", "jti-123", 3600)

        request = _make_request()
        response = _make_response()

        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch("syntara.auth.router.set_csrf_cookie"),
            patch("syntara.auth.router.generate_csrf_seed", return_value="seed"),
        ):
            await login(
                body=LoginRequest(username="testuser", password="password123"),  # noqa: S106
                request=request,
                response=response,
                db=mock_db,
            )

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        events_by_action: dict[str, list[AuditEvent]] = {}
        for e in events:
            events_by_action.setdefault(e.event_action, []).append(e)

        # SessionLifecycleEvent -> "session_created"
        session_events = events_by_action.get("session_created", [])
        assert len(session_events) == 1
        assert session_events[0].event_category == EventCategory.USER_ACTION
        assert session_events[0].event_status == EventStatus.SUCCESS
        assert session_events[0].actor_username == "testuser"
        assert isinstance(session_events[0].structured_data, AuditContextData)
        assert session_events[0].structured_data.lifecycle_action == "create"  # type: ignore[attr-defined]
        assert session_events[0].structured_data.jti == "jti-123"  # type: ignore[attr-defined]

        # LoginAttemptEvent + @audit both emit action="login"
        login_events = events_by_action.get("login", [])
        assert len(login_events) == 2

        attempt_event = next(e for e in login_events if e.event_category == EventCategory.USER_ACTION)
        assert attempt_event.event_status == EventStatus.SUCCESS
        assert isinstance(attempt_event.structured_data, AuditContextData)
        assert attempt_event.structured_data.method == "password"  # type: ignore[attr-defined]
        assert attempt_event.actor_username == "testuser"
        assert attempt_event.actor_id == user.id

        audit_event = next(e for e in login_events if e.event_category == EventCategory.SECURITY_EVENT)
        assert audit_event.event_status == EventStatus.SUCCESS


def _setup_oidc_callback_mocks() -> tuple[MagicMock, MagicMock, MagicMock, MagicMock, AsyncMock]:
    """Set up common mocks for oidc_callback tests."""
    mock_token_service = MagicMock()
    mock_token_service.create_refresh_token.return_value = ("refresh-jwt", "jti-123", 3600)

    mock_store_instance = AsyncMock()
    mock_store_instance.create = AsyncMock()
    mock_session_store = MagicMock()
    mock_session_store.return_value = mock_store_instance

    mock_settings = MagicMock()
    mock_settings.jwt_issuer = "http://localhost:3000"
    mock_settings.cors_allow_origins = ["http://localhost:3000"]
    mock_settings.jwt_refresh_token_lifetime_hours = 8

    db = AsyncMock()

    request = MagicMock()
    request.headers.get.return_value = "TestUserAgent"
    request.client = MagicMock()
    request.client.host = "127.0.0.1"

    return mock_token_service, mock_session_store, mock_settings, request, db


class TestOIDCAuditEvents:
    """Tests for audit event emission during OIDC flows.

    These tests verify that OIDC error paths emit audit events with correct
    error_type, provider_id, and event metadata. Uses real dispatcher and
    handlers to test the full pipeline.
    """

    def setup_method(self) -> None:
        from syntara.auth.audit.login_attempt import LoginAttemptEvent, LoginAttemptHandler
        from syntara.auth.audit.oidc_flow import OIDCFlowEvent, OIDCFlowHandler
        from syntara.auth.audit.session_lifecycle import SessionLifecycleEvent, SessionLifecycleHandler
        from syntara.auth.audit.user_login import UserLoginEvent, UserLoginHandler

        AuditEventDispatcher.register(
            {
                OIDCFlowEvent: OIDCFlowHandler(),
                SessionLifecycleEvent: SessionLifecycleHandler(),
                LoginAttemptEvent: LoginAttemptHandler(),
                UserLoginEvent: UserLoginHandler(),
                FunctionExecutionEvent: FunctionExecutionHandler(),
            }
        )

    @pytest.mark.asyncio
    async def test_authorize_oidc_error_emits_event_with_error_type(self) -> None:
        """oidc_authorize with OIDCError emits audit event with error_type and provider_id."""
        from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
        from syntara.audit.models.structured_data import AuditContextData

        provider_id = uuid4()

        # Mock the underlying function to raise OIDCError
        with patch("syntara.auth.router._build_oidc_authorize_redirect") as mock_build:
            mock_build.side_effect = OIDCError("Provider not available")

            # Mock request and db
            request = MagicMock()
            request.headers.get.return_value = None
            db = AsyncMock()

            # Capture emitted events
            with patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit:
                # Call oidc_authorize - should redirect to login with error
                response = await oidc_authorize(provider_id=provider_id, request=request, db=db)
                assert response.status_code == 302
                assert "auth_error=" in response.headers["location"]

            # Verify audit events were emitted
            # @audit emits 1 event + OIDCFlowEvent dispatch = 2 total
            assert mock_do_emit.call_count == 2
            events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]

            # Find the OIDCFlowEvent-generated event
            oidc_event = next(e for e in events if e.event_action == "oidc_authorize")

            assert oidc_event.event_category == EventCategory.SECURITY_EVENT
            assert oidc_event.event_severity == EventSeverity.ERROR
            assert oidc_event.event_status == EventStatus.ERROR
            assert isinstance(oidc_event.structured_data, AuditContextData)
            assert oidc_event.structured_data.error_type == "OIDCError"
            assert oidc_event.structured_data.provider_id == str(provider_id)  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_authorize_callback_error_emits_event_with_error_type(self) -> None:
        """oidc_authorize with OIDCCallbackError emits audit event with error_type and provider_id."""
        from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
        from syntara.audit.models.structured_data import AuditContextData

        provider_id = uuid4()

        # Mock the underlying function to raise OIDCCallbackError
        with patch("syntara.auth.router._build_oidc_authorize_redirect") as mock_build:
            mock_build.side_effect = OIDCCallbackError(
                "Invalid state", error_code=OIDCErrorCode.AUTH_FAILED, origin="http://localhost:3000"
            )

            # Mock request and db
            request = MagicMock()
            request.headers.get.return_value = None
            db = AsyncMock()

            # Capture emitted events
            with patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit:
                # Call oidc_authorize - should redirect to login with error
                response = await oidc_authorize(provider_id=provider_id, request=request, db=db)
                assert response.status_code == 302

            # Verify audit events were emitted
            # @audit emits 1 event + OIDCFlowEvent dispatch = 2 total
            assert mock_do_emit.call_count == 2
            events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]

            # Find the OIDCFlowEvent-generated event
            oidc_event = next(e for e in events if e.event_action == "oidc_authorize")

            assert oidc_event.event_category == EventCategory.SECURITY_EVENT
            assert oidc_event.event_severity == EventSeverity.ERROR
            assert oidc_event.event_status == EventStatus.ERROR
            assert isinstance(oidc_event.structured_data, AuditContextData)
            assert oidc_event.structured_data.error_type == "OIDCCallbackError"
            assert oidc_event.structured_data.provider_id == str(provider_id)  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_authorize_generic_exception_emits_event_with_error_type(self) -> None:
        """oidc_authorize with generic Exception emits audit event with error_type and provider_id."""
        from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
        from syntara.audit.models.structured_data import AuditContextData

        provider_id = uuid4()

        # Mock the underlying function to raise RuntimeError
        with patch("syntara.auth.router._build_oidc_authorize_redirect") as mock_build:
            mock_build.side_effect = RuntimeError("Unexpected error")

            # Mock request and db
            request = MagicMock()
            request.headers.get.return_value = None
            db = AsyncMock()

            # Capture emitted events
            with patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit:
                # Call oidc_authorize - should redirect to login with error
                response = await oidc_authorize(provider_id=provider_id, request=request, db=db)
                assert response.status_code == 302

            # Verify audit events were emitted
            # @audit emits 1 event + OIDCFlowEvent dispatch = 2 total
            assert mock_do_emit.call_count == 2
            events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]

            # Find the OIDCFlowEvent-generated event
            oidc_event = next(e for e in events if e.event_action == "oidc_authorize")

            assert oidc_event.event_category == EventCategory.SECURITY_EVENT
            assert oidc_event.event_severity == EventSeverity.ERROR
            assert oidc_event.event_status == EventStatus.ERROR
            assert isinstance(oidc_event.structured_data, AuditContextData)
            assert oidc_event.structured_data.error_type == "RuntimeError"
            assert oidc_event.structured_data.provider_id == str(provider_id)  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_callback_error_emits_event_with_none_provider_id(self) -> None:
        """oidc_callback with OIDCCallbackError emits audit event with provider_id=None."""
        from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
        from syntara.audit.models.structured_data import AuditContextData

        # Mock the underlying function to raise OIDCCallbackError
        with patch("syntara.auth.router._process_oidc_callback") as mock_process:
            mock_process.side_effect = OIDCCallbackError(
                "Invalid code", error_code=OIDCErrorCode.AUTH_FAILED, origin="http://localhost:3000"
            )

            # Mock request and db
            request = MagicMock()
            request.headers.get.return_value = None
            request.client = MagicMock()
            request.client.host = "127.0.0.1"
            db = AsyncMock()

            # Capture emitted events
            with patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit:
                # Call oidc_callback - should redirect to login with error
                response = await oidc_callback(state="test-state", request=request, db=db, code="test-code")
                assert response.status_code == 302

            # Verify audit events were emitted
            # @audit emits 1 event + OIDCFlowEvent dispatch = 2 total
            assert mock_do_emit.call_count == 2
            events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]

            # Find the OIDCFlowEvent-generated event
            oidc_event = next(e for e in events if e.event_action == "oidc_callback")

            assert oidc_event.event_category == EventCategory.SECURITY_EVENT
            assert oidc_event.event_severity == EventSeverity.ERROR
            assert oidc_event.event_status == EventStatus.ERROR
            assert isinstance(oidc_event.structured_data, AuditContextData)
            assert oidc_event.structured_data.error_type == "OIDCCallbackError"
            # Critical: callback errors have provider_id=None
            assert oidc_event.structured_data.provider_id is None  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_successful_oidc_callback_emits_all_events_in_order(self) -> None:
        """Happy OIDC callback flow emits all audit events in correct chronological order.

        Expected order:
        1. OIDCFlowEvent -> "oidc_callback" (USER_ACTION, SUCCESS)
        2. SessionLifecycleEvent -> "session_created" (USER_ACTION, SUCCESS)
        3. UserLoginEvent -> "user_login" (USER_ACTION, SUCCESS)
        4. LoginAttemptEvent -> "login" (USER_ACTION, SUCCESS, method=OIDC)
        5. @audit "oidc_callback" (SECURITY_EVENT, SUCCESS)
        """
        from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventStatus
        from syntara.audit.models.structured_data import AuditContextData

        provider = MagicMock()
        provider.id, provider.name = uuid4(), "TestProvider"
        user = _make_user()
        state_data = {"origin": "http://localhost:3000", "redirect_to": "/dashboard"}
        mock_token_service, mock_session_store, mock_settings, request, db = _setup_oidc_callback_mocks()

        identity = MagicMock()
        identity.id = uuid4()
        identity.issuer = "https://idp.example.com"
        identity.subject = "sub-123"

        with (
            patch("syntara.auth.router._process_oidc_callback") as mock_process,
            patch("syntara.auth.router._get_token_service", return_value=mock_token_service),
            patch("syntara.auth.router.create_session_store", mock_session_store),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router.set_refresh_cookie"),
            patch("syntara.auth.router.set_csrf_cookie"),
            patch("syntara.auth.router.generate_csrf_seed", return_value="seed"),
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
        ):
            mock_process.return_value = (user, provider, state_data, identity, {}, "id-token-raw", False)

            response = await oidc_callback(
                state="valid-state",
                request=request,
                db=db,
                code="auth-code-123",
            )

            assert response.status_code == 302

        # Verify all 5 events were emitted in the correct order
        assert mock_do_emit.call_count == 5
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]

        # Event 1: OIDCFlowEvent -> "oidc_callback" (USER_ACTION, SUCCESS)
        e0 = events[0]
        assert (e0.event_action, e0.event_category, e0.event_status, e0.actor_id) == (
            "oidc_callback",
            EventCategory.USER_ACTION,
            EventStatus.SUCCESS,
            user.id,
        )
        assert e0.actor_username == "testuser"
        assert isinstance(e0.structured_data, AuditContextData)
        assert e0.structured_data.provider_id == str(provider.id)  # type: ignore[attr-defined]
        assert e0.structured_data.stage == "callback"  # type: ignore[attr-defined]

        # Event 2: SessionLifecycleEvent -> "session_created" (USER_ACTION, SUCCESS)
        e1 = events[1]
        assert (e1.event_action, e1.event_category, e1.event_status, e1.actor_id) == (
            "session_created",
            EventCategory.USER_ACTION,
            EventStatus.SUCCESS,
            user.id,
        )
        assert isinstance(e1.structured_data, AuditContextData)
        assert (
            e1.structured_data.lifecycle_action,  # type: ignore[attr-defined]
            e1.structured_data.jti,  # type: ignore[attr-defined]
            e1.structured_data.idp,  # type: ignore[attr-defined]
        ) == ("create", "jti-123", "TestProvider")

        # Event 3: UserLoginEvent -> "user_login" (USER_ACTION, SUCCESS)
        e2 = events[2]
        assert (e2.event_action, e2.event_category, e2.event_status, e2.actor_id) == (
            "user_login",
            EventCategory.USER_ACTION,
            EventStatus.SUCCESS,
            user.id,
        )

        # Event 4: LoginAttemptEvent -> "login" (USER_ACTION, SUCCESS, method=OIDC)
        e3 = events[3]
        assert (e3.event_action, e3.event_category, e3.event_status, e3.actor_id) == (
            "login",
            EventCategory.USER_ACTION,
            EventStatus.SUCCESS,
            user.id,
        )
        assert isinstance(e3.structured_data, AuditContextData)
        assert (
            e3.structured_data.method,  # type: ignore[attr-defined]
            e3.actor_username,
        ) == ("oidc", "testuser")

        # Event 5: @audit "oidc_callback" (SECURITY_EVENT, SUCCESS)
        e4 = events[4]
        assert (e4.event_action, e4.event_category, e4.event_status) == (
            "oidc_callback",
            EventCategory.SECURITY_EVENT,
            EventStatus.SUCCESS,
        )


# =============================================================================
# _get_user_group_names helper
# =============================================================================


class TestGetUserGroupNames:
    """Tests for _get_user_group_names helper."""

    @pytest.mark.asyncio
    async def test_returns_groups_sorted(self) -> None:
        """Should return groups from the DB query sorted by name."""
        from syntara.auth.router import _get_user_group_names

        user_id = uuid4()
        mock_result = MagicMock()
        mock_result.all.return_value = ["authenticated", "engineering", "ops"]
        db = AsyncMock()
        db.exec.return_value = mock_result

        names = await _get_user_group_names(db, user_id)

        assert names == ["authenticated", "engineering", "ops"]

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_groups(self) -> None:
        """Should return empty list when user has no group memberships."""
        from syntara.auth.router import _get_user_group_names

        user_id = uuid4()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db = AsyncMock()
        db.exec.return_value = mock_result

        names = await _get_user_group_names(db, user_id)

        assert names == []


# =============================================================================
# _build_rp_logout_url helper
# =============================================================================


class TestBuildRpLogoutUrl:
    """Tests for _build_rp_logout_url helper."""

    def test_all_params(self) -> None:
        """Should build URL with both id_token_hint and post_logout_redirect_uri."""
        from syntara.auth.router import _build_rp_logout_url

        url = _build_rp_logout_url(
            end_session_endpoint="https://idp.example.com/logout",
            id_token_hint="my-id-token",  # noqa: S106
            post_logout_redirect_uri="https://app.example.com",
        )

        assert url.startswith("https://idp.example.com/logout?")
        assert "id_token_hint=my-id-token" in url
        assert "post_logout_redirect_uri=https%3A%2F%2Fapp.example.com" in url

    def test_only_post_logout_redirect_uri(self) -> None:
        """Should build URL with only post_logout_redirect_uri when no id_token_hint."""
        from syntara.auth.router import _build_rp_logout_url

        url = _build_rp_logout_url(
            end_session_endpoint="https://idp.example.com/logout",
            id_token_hint=None,
            post_logout_redirect_uri="https://app.example.com",
        )

        assert "post_logout_redirect_uri=https%3A%2F%2Fapp.example.com" in url
        assert "id_token_hint" not in url

    def test_no_params_returns_bare_endpoint(self) -> None:
        """Should return bare endpoint when both optional params are empty."""
        from syntara.auth.router import _build_rp_logout_url

        url = _build_rp_logout_url(
            end_session_endpoint="https://idp.example.com/logout",
            id_token_hint=None,
            post_logout_redirect_uri="",
        )

        assert url == "https://idp.example.com/logout"

    def test_only_id_token_hint(self) -> None:
        """Should build URL with only id_token_hint when post_logout_redirect_uri is empty."""
        from syntara.auth.router import _build_rp_logout_url

        url = _build_rp_logout_url(
            end_session_endpoint="https://idp.example.com/logout",
            id_token_hint="my-id-token",  # noqa: S106
            post_logout_redirect_uri="",
        )

        assert "id_token_hint=my-id-token" in url
        assert "post_logout_redirect_uri" not in url


# =============================================================================
# _resolve_end_session_endpoint helper
# =============================================================================


class TestResolveEndSessionEndpoint:
    """Tests for _resolve_end_session_endpoint helper."""

    @pytest.mark.asyncio
    async def test_returns_static_endpoint(self) -> None:
        """Should prefer static end_session_endpoint from config."""
        from syntara.auth.router import _resolve_end_session_endpoint
        from syntara.identity_providers.models.identity_provider_configuration import OIDCConfiguration

        config = OIDCConfiguration(
            issuer_url="https://idp.example.com",
            client_id="c",
            client_secret="s",  # noqa: S106
            redirect_uri="http://localhost/callback",
            end_session_endpoint="https://idp.example.com/logout",
        )

        result = await _resolve_end_session_endpoint(config)

        assert result == "https://idp.example.com/logout"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_static_and_no_auto_discovery(self) -> None:
        """Should return None when no static endpoint and auto_discovery is False."""
        from syntara.auth.router import _resolve_end_session_endpoint
        from syntara.identity_providers.models.identity_provider_configuration import OIDCConfiguration

        config = OIDCConfiguration(
            issuer_url="https://idp.example.com",
            client_id="c",
            client_secret="s",  # noqa: S106
            redirect_uri="http://localhost/callback",
            auto_discovery=False,
            authorization_endpoint="https://idp.example.com/auth",
            token_endpoint="https://idp.example.com/token",  # noqa: S106
            jwks_uri="https://idp.example.com/jwks",
            end_session_endpoint=None,
        )

        result = await _resolve_end_session_endpoint(config)

        assert result is None

    @pytest.mark.asyncio
    async def test_discovers_endpoint_via_oidc_service(self) -> None:
        """Should fall back to OIDC discovery when auto_discovery is True."""
        from syntara.auth.router import _resolve_end_session_endpoint
        from syntara.identity_providers.models.identity_provider_configuration import OIDCConfiguration

        config = OIDCConfiguration(
            issuer_url="https://idp.example.com",
            client_id="c",
            client_secret="s",  # noqa: S106
            redirect_uri="http://localhost/callback",
            auto_discovery=True,
            end_session_endpoint=None,
        )

        mock_service = AsyncMock()
        mock_service.fetch_discovery_config = AsyncMock(
            return_value={"end_session_endpoint": "https://idp.example.com/discovered-logout"}
        )

        with patch("syntara.auth.router.OIDCService", return_value=mock_service):
            result = await _resolve_end_session_endpoint(config)

        assert result == "https://idp.example.com/discovered-logout"

    @pytest.mark.asyncio
    async def test_returns_none_on_discovery_failure(self) -> None:
        """Should return None when OIDC discovery fails."""
        from syntara.auth.router import _resolve_end_session_endpoint
        from syntara.identity_providers.models.identity_provider_configuration import OIDCConfiguration

        config = OIDCConfiguration(
            issuer_url="https://idp.example.com",
            client_id="c",
            client_secret="s",  # noqa: S106
            redirect_uri="http://localhost/callback",
            auto_discovery=True,
            end_session_endpoint=None,
        )

        mock_service = AsyncMock()
        mock_service.fetch_discovery_config = AsyncMock(side_effect=OIDCError("Discovery failed"))

        with patch("syntara.auth.router.OIDCService", return_value=mock_service):
            result = await _resolve_end_session_endpoint(config)

        assert result is None


# =============================================================================
# _maybe_rp_logout: additional edge cases
# =============================================================================


class TestMaybeRpLogoutEdgeCases:
    """Additional edge-case tests for _maybe_rp_logout helper."""

    @pytest.mark.asyncio
    async def test_returns_redirect_url_when_decryption_fails(self) -> None:
        """Should still return redirect_url (without hint) when decrypt fails."""
        from syntara.auth.router import _maybe_rp_logout
        from syntara.identity_providers.models.identity_provider import IdentityProvider
        from syntara.identity_providers.models.identity_provider_configuration import OIDCConfiguration

        idp_id = uuid4()
        config = OIDCConfiguration(
            issuer_url="https://idp.example.com",
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
            redirect_uri="https://app.example.com/callback",
            enable_rp_initiated_logout=True,
            auto_discovery=False,
            authorization_endpoint="https://idp.example.com/auth",
            token_endpoint="https://idp.example.com/token",  # noqa: S106
            jwks_uri="https://idp.example.com/jwks",
            end_session_endpoint="https://idp.example.com/logout",
        )
        provider = IdentityProvider(
            id=idp_id,
            name="Test IdP",
            slug="test-idp",
            configuration=config,
        )

        session_info = SessionInfo(
            jti="jti-rp",
            user_id=str(uuid4()),
            issued_at=datetime.now(UTC),
            device=None,
            ip_address=None,
            ttl=3600,
            idp_id=str(idp_id),
            idp="oidc",
            id_token_hint="encrypted-hint",  # noqa: S106
        )

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = provider

        db = AsyncMock()
        db.exec.return_value = mock_result

        with patch("syntara.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.secret_encryption_key.get_secret_value.return_value = "bad-key"
            with patch("syntara.auth.router.key_from_string", side_effect=ValueError("bad key")):
                result = await _maybe_rp_logout(db, session_info, "https://app.example.com")

        assert result is not None
        assert "redirect_url" in result
        assert "https://idp.example.com/logout" in result["redirect_url"]
        # No id_token_hint in the URL because decryption failed
        assert "id_token_hint" not in result["redirect_url"]

    @pytest.mark.asyncio
    async def test_returns_none_when_provider_not_found(self) -> None:
        """Should return None when IdP does not exist in DB."""
        from syntara.auth.router import _maybe_rp_logout

        session_info = SessionInfo(
            jti="jti-rp",
            user_id=str(uuid4()),
            issued_at=datetime.now(UTC),
            device=None,
            ip_address=None,
            ttl=3600,
            idp_id=str(uuid4()),
            idp="oidc",
        )

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None

        db = AsyncMock()
        db.exec.return_value = mock_result

        result = await _maybe_rp_logout(db, session_info, "https://app.example.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_rp_logout_disabled(self) -> None:
        """Should return None when enable_rp_initiated_logout is False."""
        from syntara.auth.router import _maybe_rp_logout
        from syntara.identity_providers.models.identity_provider import IdentityProvider
        from syntara.identity_providers.models.identity_provider_configuration import OIDCConfiguration

        idp_id = uuid4()
        config = OIDCConfiguration(
            issuer_url="https://idp.example.com",
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
            redirect_uri="https://app.example.com/callback",
            enable_rp_initiated_logout=False,
        )
        provider = IdentityProvider(
            id=idp_id,
            name="Test IdP",
            slug="test-idp",
            configuration=config,
        )

        session_info = SessionInfo(
            jti="jti-rp",
            user_id=str(uuid4()),
            issued_at=datetime.now(UTC),
            device=None,
            ip_address=None,
            ttl=3600,
            idp_id=str(idp_id),
            idp="oidc",
        )

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = provider

        db = AsyncMock()
        db.exec.return_value = mock_result

        result = await _maybe_rp_logout(db, session_info, "https://app.example.com")

        assert result is None


# =============================================================================
# _build_callback_error_redirect helper
# =============================================================================


class TestBuildCallbackErrorRedirect:
    """Tests for _build_callback_error_redirect helper."""

    def test_redirect_to_uses_link_error_param(self) -> None:
        """Should redirect to redirect_to URL with link_error param when redirect_to is set."""
        from syntara.auth.router import _build_callback_error_redirect

        err = OIDCCallbackError(
            "Link failed",
            error_code=OIDCErrorCode.LINK_FAILED,
            origin="http://localhost:3000",
            redirect_to="/settings/identities",
        )

        with patch("syntara.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.cors_allow_origins = ["http://localhost:3000"]
            mock_settings.return_value.jwt_issuer = "http://localhost:8000"
            response = _build_callback_error_redirect(err)

        assert response.status_code == 302
        location = response.headers["location"]
        assert "link_error=link_failed" in location

    def test_no_redirect_to_uses_auth_error_param(self) -> None:
        """Should redirect to base URL with auth_error param when no redirect_to."""
        from syntara.auth.router import _build_callback_error_redirect

        err = OIDCCallbackError(
            "Auth failed",
            error_code=OIDCErrorCode.AUTH_FAILED,
            origin="http://localhost:3000",
        )

        with patch("syntara.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.cors_allow_origins = ["http://localhost:3000"]
            mock_settings.return_value.jwt_issuer = "http://localhost:8000"
            response = _build_callback_error_redirect(err)

        assert response.status_code == 302
        location = response.headers["location"]
        assert "auth_error=auth_failed" in location


# =============================================================================
# _build_authorize_error_redirect helper
# =============================================================================


class TestBuildAuthorizeErrorRedirect:
    """Tests for _build_authorize_error_redirect helper."""

    def test_link_flow_redirects_with_link_error(self) -> None:
        """Should redirect to redirect_to with link_error for link flow errors."""
        from syntara.auth.router import _build_authorize_error_redirect

        with patch("syntara.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.cors_allow_origins = ["http://localhost:3000"]
            mock_settings.return_value.jwt_issuer = "http://localhost:8000"
            response = _build_authorize_error_redirect(
                origin="http://localhost:3000",
                redirect_to="/settings/identities",
                flow="link",
                error_code="auth_failed",
            )

        assert response.status_code == 302
        location = response.headers["location"]
        assert "link_error=auth_failed" in location

    def test_non_link_flow_redirects_with_auth_error(self) -> None:
        """Should redirect to base URL with auth_error for non-link flows."""
        from syntara.auth.router import _build_authorize_error_redirect

        with patch("syntara.auth.router.get_settings") as mock_settings:
            mock_settings.return_value.cors_allow_origins = ["http://localhost:3000"]
            mock_settings.return_value.jwt_issuer = "http://localhost:8000"
            response = _build_authorize_error_redirect(
                origin="http://localhost:3000",
                redirect_to=None,
                flow=None,
                error_code="discovery_failed",
            )

        assert response.status_code == 302
        location = response.headers["location"]
        assert "auth_error=discovery_failed" in location


# =============================================================================
# _process_oidc_callback error paths
# =============================================================================


class TestProcessOidcCallbackErrors:
    """Tests for error paths in _process_oidc_callback."""

    @pytest.mark.asyncio
    async def test_raises_on_idp_error_response(self) -> None:
        """Should raise OIDCCallbackError with auth_failed and origin when IdP returns error."""
        from syntara.auth.router import _process_oidc_callback

        with (
            patch("syntara.auth.router.OIDCService") as mock_oidc_cls,
            patch("syntara.auth.router._revalidate_origin", return_value="http://localhost:3000"),
        ):
            mock_oidc_cls.return_value.retrieve_oidc_state.return_value = {
                "provider_id": str(uuid4()),
                "nonce": "n",
                "code_verifier": "cv",
                "origin": "http://localhost:3000",
            }

            with pytest.raises(OIDCCallbackError) as exc_info:
                await _process_oidc_callback(
                    state="test-state",
                    db=AsyncMock(),
                    code=None,
                    error="access_denied",
                    error_description="User denied access",
                )

        assert exc_info.value.error_code == "auth_failed"
        assert exc_info.value.origin == "http://localhost:3000"

    @pytest.mark.asyncio
    async def test_raises_on_missing_code(self) -> None:
        """Should raise OIDCCallbackError with missing_code and origin when no code is provided."""
        from syntara.auth.router import _process_oidc_callback

        with (
            patch("syntara.auth.router.OIDCService") as mock_oidc_cls,
            patch("syntara.auth.router._revalidate_origin", return_value="http://localhost:3000"),
        ):
            mock_oidc_cls.return_value.retrieve_oidc_state.return_value = {
                "provider_id": str(uuid4()),
                "nonce": "n",
                "code_verifier": "cv",
                "origin": "http://localhost:3000",
            }

            with pytest.raises(OIDCCallbackError) as exc_info:
                await _process_oidc_callback(
                    state="test-state",
                    db=AsyncMock(),
                    code=None,
                    error=None,
                    error_description=None,
                )

        assert exc_info.value.error_code == "missing_code"
        assert exc_info.value.origin == "http://localhost:3000"

    @pytest.mark.asyncio
    async def test_raises_on_invalid_state(self) -> None:
        """Should raise OIDCCallbackError with state_expired when state is invalid."""
        from syntara.auth.router import _process_oidc_callback

        with patch("syntara.auth.router.OIDCService") as mock_oidc_cls:
            mock_oidc_cls.return_value.retrieve_oidc_state.return_value = None

            with pytest.raises(OIDCCallbackError) as exc_info:
                await _process_oidc_callback(
                    state="expired-state",
                    db=AsyncMock(),
                    code="auth-code",
                    error=None,
                    error_description=None,
                )

        assert exc_info.value.error_code == "state_expired"

    @pytest.mark.asyncio
    async def test_raises_state_expired_when_idp_error_and_state_invalid(self) -> None:
        """When IdP returns error but state is also invalid, state_expired takes precedence."""
        from syntara.auth.router import _process_oidc_callback

        with patch("syntara.auth.router.OIDCService") as mock_oidc_cls:
            mock_oidc_cls.return_value.retrieve_oidc_state.return_value = None

            with pytest.raises(OIDCCallbackError) as exc_info:
                await _process_oidc_callback(
                    state="expired-state",
                    db=AsyncMock(),
                    code=None,
                    error="access_denied",
                    error_description="User denied access",
                )

        assert exc_info.value.error_code == "state_expired"
        assert exc_info.value.origin is None

    @pytest.mark.asyncio
    async def test_raises_on_provider_unavailable(self) -> None:
        """Should raise OIDCCallbackError with provider_unavailable when provider not found."""
        from syntara.auth.router import _process_oidc_callback

        with (
            patch("syntara.auth.router.OIDCService") as mock_oidc_cls,
            patch("syntara.auth.router._load_enabled_provider", side_effect=OIDCError("Not found")),
            patch("syntara.auth.router._revalidate_origin", return_value=None),
        ):
            mock_oidc_cls.return_value.retrieve_oidc_state.return_value = {
                "provider_id": str(uuid4()),
                "nonce": "n",
                "code_verifier": "cv",
                "origin": None,
            }

            with pytest.raises(OIDCCallbackError) as exc_info:
                await _process_oidc_callback(
                    state="valid-state",
                    db=AsyncMock(),
                    code="auth-code",
                    error=None,
                    error_description=None,
                )

        assert exc_info.value.error_code == "provider_unavailable"

    @pytest.mark.asyncio
    async def test_raises_on_discovery_failure(self) -> None:
        """Should raise OIDCCallbackError with discovery_failed when endpoint resolution fails."""
        from syntara.auth.router import _process_oidc_callback

        provider = MagicMock()
        provider.id = uuid4()
        provider.name = "TestIdP"

        with (
            patch("syntara.auth.router.OIDCService") as mock_oidc_cls,
            patch("syntara.auth.router._load_enabled_provider", return_value=provider),
            patch("syntara.auth.router._load_provider_config", return_value=MagicMock()),
            patch("syntara.auth.router._get_oidc_endpoints", side_effect=OIDCError("Discovery failed")),
            patch("syntara.auth.router._revalidate_origin", return_value=None),
            patch("syntara.auth.router._is_ssl_verification_error", return_value=False),
        ):
            mock_oidc_cls.return_value.retrieve_oidc_state.return_value = {
                "provider_id": str(provider.id),
                "nonce": "n",
                "code_verifier": "cv",
                "origin": None,
            }

            with pytest.raises(OIDCCallbackError) as exc_info:
                await _process_oidc_callback(
                    state="valid-state",
                    db=AsyncMock(),
                    code="auth-code",
                    error=None,
                    error_description=None,
                )

        assert exc_info.value.error_code == "discovery_failed"

    @pytest.mark.asyncio
    async def test_raises_on_token_exchange_failure(self) -> None:
        """Should raise OIDCCallbackError with auth_failed when token exchange fails."""
        from syntara.auth.router import _process_oidc_callback

        provider = MagicMock()
        provider.id = uuid4()
        provider.name = "TestIdP"

        with (
            patch("syntara.auth.router.OIDCService") as mock_oidc_cls,
            patch("syntara.auth.router._load_enabled_provider", return_value=provider),
            patch("syntara.auth.router._load_provider_config", return_value=MagicMock()),
            patch("syntara.auth.router._get_oidc_endpoints", return_value={"token_endpoint": "https://idp/token"}),
            patch(
                "syntara.auth.router._exchange_and_validate_tokens",
                side_effect=OIDCError("Token exchange failed"),
            ),
            patch("syntara.auth.router._revalidate_origin", return_value=None),
            patch("syntara.auth.router._is_ssl_verification_error", return_value=False),
        ):
            mock_oidc_cls.return_value.retrieve_oidc_state.return_value = {
                "provider_id": str(provider.id),
                "nonce": "n",
                "code_verifier": "cv",
                "origin": None,
            }

            with pytest.raises(OIDCCallbackError) as exc_info:
                await _process_oidc_callback(
                    state="valid-state",
                    db=AsyncMock(),
                    code="auth-code",
                    error=None,
                    error_description=None,
                )

        assert exc_info.value.error_code == "auth_failed"

    @pytest.mark.asyncio
    async def test_raises_tls_error_code_on_ssl_failure(self) -> None:
        """Should raise OIDCCallbackError with tls_verify_failed on SSL verification error."""
        from syntara.auth.router import _process_oidc_callback

        provider = MagicMock()
        provider.id = uuid4()
        provider.name = "TestIdP"

        with (
            patch("syntara.auth.router.OIDCService") as mock_oidc_cls,
            patch("syntara.auth.router._load_enabled_provider", return_value=provider),
            patch("syntara.auth.router._load_provider_config", return_value=MagicMock()),
            patch("syntara.auth.router._get_oidc_endpoints", side_effect=OIDCError("SSL error")),
            patch("syntara.auth.router._revalidate_origin", return_value=None),
            patch("syntara.auth.router._is_ssl_verification_error", return_value=True),
        ):
            mock_oidc_cls.return_value.retrieve_oidc_state.return_value = {
                "provider_id": str(provider.id),
                "nonce": "n",
                "code_verifier": "cv",
                "origin": None,
            }

            with pytest.raises(OIDCCallbackError) as exc_info:
                await _process_oidc_callback(
                    state="valid-state",
                    db=AsyncMock(),
                    code="auth-code",
                    error=None,
                    error_description=None,
                )

        assert exc_info.value.error_code == "tls_verify_failed"


# =============================================================================
# _process_link_callback error paths
# =============================================================================


class TestProcessLinkCallback:
    """Tests for _process_link_callback error handling."""

    @pytest.mark.asyncio
    async def test_wraps_oidc_error_with_error_code(self) -> None:
        """Should wrap OIDCError with error_code from the original or fallback to link_failed."""
        from syntara.auth.router import _process_link_callback

        provider = MagicMock()
        provider.name = "TestIdP"

        state_data = {"user_id": str(uuid4()), "redirect_to": "/settings/identities"}

        with (
            patch(
                "syntara.auth.router._handle_link_flow",
                side_effect=OIDCError("Already linked", error_code=OIDCErrorCode.IDENTITY_ALREADY_LINKED),
            ),
            pytest.raises(OIDCCallbackError) as exc_info,
        ):
            await _process_link_callback(
                db=AsyncMock(),
                state_data=state_data,
                user_claims={"sub": "sub-1"},
                provider=provider,
                origin="http://localhost:3000",
            )

        assert exc_info.value.error_code == "identity_already_linked"
        assert exc_info.value.redirect_to == "/settings/identities"

    @pytest.mark.asyncio
    async def test_wraps_generic_exception_with_link_failed(self) -> None:
        """Should wrap unexpected Exception with link_failed error code."""
        from syntara.auth.router import _process_link_callback

        provider = MagicMock()
        provider.name = "TestIdP"

        state_data = {"user_id": str(uuid4()), "redirect_to": "/settings/identities"}

        with (
            patch(
                "syntara.auth.router._handle_link_flow",
                side_effect=RuntimeError("Unexpected"),
            ),
            pytest.raises(OIDCCallbackError) as exc_info,
        ):
            await _process_link_callback(
                db=AsyncMock(),
                state_data=state_data,
                user_claims={"sub": "sub-1"},
                provider=provider,
                origin="http://localhost:3000",
            )

        assert exc_info.value.error_code == "link_failed"
        assert exc_info.value.redirect_to == "/settings/identities"
