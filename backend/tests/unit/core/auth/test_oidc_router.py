# ruff: noqa: S105, S106, S107
"""Unit tests for OIDC authentication router endpoints."""

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.models.audit_event import EventCategory
from syntara.auth.exceptions import OIDCCallbackError, OIDCErrorCode, SessionStoreUnavailableError
from syntara.auth.router import (
    _auto_create_user,
    _build_callback_error_redirect,
    _build_link_redirect,
    _build_test_signin_response,
    _create_identity_with_race_handling,
    _exchange_and_validate_tokens,
    _get_oidc_endpoints,
    _handle_link_flow,
    _load_active_user,
    _load_enabled_provider,
    _resolve_oidc_user,
    _revalidate_origin,
    _safe_redirect_url,
    list_auth_providers,
    oidc_authorize,
    oidc_callback,
)
from syntara.auth.services.oidc_service import OIDCError, OIDCService
from syntara.authz.audit.group_membership import GroupMembershipEvent, GroupMembershipHandler
from syntara.authz.resolver import AUTHENTICATED_GROUP_NAME
from syntara.core.constants import FieldLimits
from syntara.core.models import User, UserIdentity
from syntara.core.models.group import Group
from syntara.core.models.user_identity import SUBJECT_MAX_LENGTH
from syntara.identity_providers.models.identity_provider import IdentityProvider
from syntara.identity_providers.models.identity_provider_configuration import OIDCConfiguration


def _add_begin_nested(db: AsyncMock) -> None:
    """Configure begin_nested() to return an async context manager on a mock session."""
    mock_nested = AsyncMock()
    db.begin_nested = MagicMock(return_value=mock_nested)


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


def _make_user(
    *,
    user_id: str | None = None,
    email: str = "test@example.com",
    username: str = "testuser",
    is_enabled: bool = True,
    password_hash: str | None = None,
    auth_type: str = "federated",
) -> User:
    from syntara.core.models.user import AuthType

    return User(
        id=UUID(user_id) if user_id else uuid4(),
        username=username,
        email=email,
        first_name="Test",
        last_name="User",
        is_enabled=is_enabled,
        password_hash=password_hash,
        auth_type=AuthType(auth_type),
    )


def _make_identity(
    *,
    identity_id: str | None = None,
    user_id: UUID | None = None,
    provider_id: UUID | None = None,
    issuer: str = "https://idp.example.com",
    subject: str = "test-subject-123",
) -> UserIdentity:
    """Build a mock UserIdentity for testing."""
    return UserIdentity(
        id=UUID(identity_id) if identity_id else uuid4(),
        user_id=user_id or uuid4(),
        identity_provider_id=provider_id or uuid4(),
        issuer=issuer,
        subject=subject,
    )


def _make_oidc_config(
    *,
    auto_discovery: bool = True,
    issuer_url: str = "https://idp.example.com",
    client_id: str = "test-client-id",
    client_secret: str = "test-client-secret",
    redirect_uri: str = "http://localhost:8000/auth/oidc/callback",
    scopes: str = "openid profile email",
    authorization_endpoint: str | None = None,
    token_endpoint: str | None = None,
    jwks_uri: str | None = None,
    userinfo_endpoint: str | None = None,
) -> OIDCConfiguration:
    return OIDCConfiguration(
        provider_type="oidc",
        auto_discovery=auto_discovery,
        issuer_url=issuer_url,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scopes=scopes,
        authorization_endpoint=authorization_endpoint,
        token_endpoint=token_endpoint,
        jwks_uri=jwks_uri,
        userinfo_endpoint=userinfo_endpoint,
    )


def _make_provider(
    *,
    provider_id: str | None = None,
    name: str = "Test Provider",
    enabled: bool = True,
    config: OIDCConfiguration | None = None,
) -> IdentityProvider:
    return IdentityProvider(
        id=UUID(provider_id) if provider_id else uuid4(),
        name=name,
        description="Test OIDC Provider",
        enabled=enabled,
        configuration=config or _make_oidc_config(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_discovery_response() -> dict[str, str]:
    """Make a mock OIDC discovery response."""
    return {
        "issuer": "https://idp.example.com",
        "authorization_endpoint": "https://idp.example.com/oauth/authorize",
        "token_endpoint": "https://idp.example.com/oauth/token",
        "jwks_uri": "https://idp.example.com/.well-known/jwks.json",
        "userinfo_endpoint": "https://idp.example.com/oauth/userinfo",
    }


def _make_user_claims(
    *,
    email: str = "user@example.com",
    name: str = "Test User",
    preferred_username: str = "testuser",
    given_name: str | None = None,
    family_name: str | None = None,
) -> dict[str, str | None]:
    """Make a mock user claims dict from ID token."""
    claims: dict[str, str | None] = {
        "sub": "oidc-sub-12345",
        "email": email,
        "name": name,
        "preferred_username": preferred_username,
    }
    if given_name is not None:
        claims["given_name"] = given_name
    if family_name is not None:
        claims["family_name"] = family_name
    return claims


def _patch_session_store(mock_store: AsyncMock) -> MagicMock:
    """Create a patched SessionStore class that returns *mock_store*."""
    return MagicMock(return_value=mock_store)


def _make_oidc_service_mock(
    *,
    state_data: dict[str, str] | None = None,
    user_claims: dict[str, str | None] | None = None,
) -> MagicMock:
    """Build a mock OIDCService (plain class, no context manager)."""
    mock = MagicMock(spec=OIDCService)
    mock.fetch_discovery_config = AsyncMock(return_value=_make_discovery_response())
    mock.generate_nonce.return_value = "nonce-xyz"
    mock.generate_pkce.return_value = ("verifier-123", "challenge-456")
    mock.store_oidc_state.return_value = "state-abc"
    mock.build_authorization_url.return_value = "https://idp.example.com/oauth/authorize?..."
    if state_data is not None:
        mock.retrieve_oidc_state.return_value = state_data
    if user_claims is not None:
        mock.exchange_code_for_tokens = AsyncMock(return_value={"id_token": "fake-id-token"})
        mock.validate_id_token.return_value = {"sub": "oidc-sub"}
        mock.extract_user_claims.return_value = user_claims
    return mock


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


# =============================================================================
# List Auth Providers
# =============================================================================


@pytest.mark.usefixtures("_mock_audit_dispatcher", "_mock_audit_emission")
class TestListAuthProviders:
    """Tests for the /auth/providers endpoint."""

    @pytest.mark.asyncio
    async def test_returns_enabled_providers(self) -> None:
        """Should return a list of enabled, non-deleted providers."""
        provider1 = _make_provider(name="Provider 1", enabled=True)
        provider2 = _make_provider(name="Provider 2", enabled=True)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [provider1, provider2]
        db.exec.return_value = mock_result

        result = await list_auth_providers(db)

        assert len(result.resources) == 2
        assert result.resources[0].id == str(provider1.id)
        assert result.resources[0].name == "Provider 1"
        assert result.resources[0].provider_type == "oidc"
        assert result.resources[1].id == str(provider2.id)
        assert result.resources[1].name == "Provider 2"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_enabled_providers(self) -> None:
        """Should return empty list when no providers are enabled."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.exec.return_value = mock_result

        result = await list_auth_providers(db)

        assert result.resources == []

    @pytest.mark.asyncio
    async def test_filters_out_deleted_providers(self) -> None:
        """Should not return deleted providers (hard-deleted providers simply don't exist)."""
        provider1 = _make_provider(name="Active Provider", enabled=True)
        # Deleted provider should not be in the query results at all due to WHERE clause

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [provider1]  # Only non-deleted
        db.exec.return_value = mock_result

        result = await list_auth_providers(db)

        assert len(result.resources) == 1
        assert result.resources[0].name == "Active Provider"


# =============================================================================
# OIDC Authorize
# =============================================================================


@pytest.mark.usefixtures("_mock_audit_dispatcher", "_mock_audit_emission")
class TestOidcAuthorize:
    """Tests for the /auth/oidc/authorize endpoint."""

    @pytest.mark.asyncio
    async def test_redirects_to_provider_authorization_url(self) -> None:
        """Should generate authorization URL and redirect with 302."""
        provider = _make_provider()
        provider_id = provider.id

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = provider
        db.exec.return_value = mock_result

        mock_svc = _make_oidc_service_mock()

        with patch("syntara.auth.router.OIDCService", return_value=mock_svc):
            response = await oidc_authorize(provider_id, _make_request(), db)

        assert response.status_code == 302
        assert response.headers["location"] == "https://idp.example.com/oauth/authorize?..."
        mock_svc.store_oidc_state.assert_called_once_with(
            provider_id=provider.id,
            nonce="nonce-xyz",
            code_verifier="verifier-123",
            redirect_to=None,
            origin=None,
            flow_type=None,
            user_id=None,
            session_jti=None,
        )

    @pytest.mark.asyncio
    async def test_redirects_to_login_when_provider_not_found(self) -> None:
        """Should redirect to frontend with auth_error when provider not found."""
        provider_id = uuid4()

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://localhost:3000"]

        with patch("syntara.auth.router.get_settings", return_value=mock_settings):
            response = await oidc_authorize(provider_id, _make_request(), db)

        assert response.status_code == 302
        assert "auth_error=" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_redirects_to_login_when_provider_disabled(self) -> None:
        """Should redirect to frontend with auth_error when provider is disabled."""
        provider = _make_provider(enabled=False)
        provider_id = provider.id

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None  # Query filters out disabled providers
        db.exec.return_value = mock_result

        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://localhost:3000"]

        with patch("syntara.auth.router.get_settings", return_value=mock_settings):
            response = await oidc_authorize(provider_id, _make_request(), db)

        assert response.status_code == 302
        assert "auth_error=" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_generates_pkce_and_stores_state(self) -> None:
        """Should generate PKCE values and store state as signed JWT."""
        provider = _make_provider()
        provider_id = provider.id

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = provider
        db.exec.return_value = mock_result

        mock_svc = _make_oidc_service_mock()

        with patch("syntara.auth.router.OIDCService", return_value=mock_svc):
            await oidc_authorize(provider_id, _make_request(), db)

        mock_svc.generate_pkce.assert_called_once()
        mock_svc.store_oidc_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_provider_redirect_uri(self) -> None:
        """Should use the redirect_uri from provider configuration."""
        config = _make_oidc_config(redirect_uri="https://app.example.com/auth/callback")
        provider = _make_provider(config=config)
        provider_id = provider.id

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = provider
        db.exec.return_value = mock_result

        mock_svc = _make_oidc_service_mock()

        with patch("syntara.auth.router.OIDCService", return_value=mock_svc):
            await oidc_authorize(provider_id, _make_request(), db)

        call_kwargs = mock_svc.build_authorization_url.call_args.kwargs
        assert call_kwargs["redirect_uri"] == "https://app.example.com/auth/callback"


# =============================================================================
# Get OIDC Endpoints
# =============================================================================


class TestGetOidcEndpoints:
    """Tests for the _get_oidc_endpoints helper function."""

    @pytest.mark.asyncio
    async def test_uses_auto_discovery_when_enabled(self) -> None:
        """Should call fetch_discovery_config when auto_discovery is True."""
        config = _make_oidc_config(auto_discovery=True)
        mock_svc = _make_oidc_service_mock()

        result = await _get_oidc_endpoints(mock_svc, config)

        mock_svc.fetch_discovery_config.assert_called_once_with(
            str(config.issuer_url), disable_tls_verify=config.disable_tls_verify
        )
        assert result["issuer"] == "https://idp.example.com"
        assert result["authorization_endpoint"] == "https://idp.example.com/oauth/authorize"

    @pytest.mark.asyncio
    async def test_uses_manual_endpoints_when_auto_discovery_false(self) -> None:
        """Should use manual configuration when auto_discovery is False."""
        config = _make_oidc_config(
            auto_discovery=False,
            authorization_endpoint="https://manual.example.com/auth",
            token_endpoint="https://manual.example.com/token",
            jwks_uri="https://manual.example.com/jwks",
            userinfo_endpoint="https://manual.example.com/userinfo",
        )
        mock_svc = _make_oidc_service_mock()

        result = await _get_oidc_endpoints(mock_svc, config)

        mock_svc.fetch_discovery_config.assert_not_called()
        assert result["authorization_endpoint"] == "https://manual.example.com/auth"
        assert result["token_endpoint"] == "https://manual.example.com/token"
        assert result["jwks_uri"] == "https://manual.example.com/jwks"
        assert result["userinfo_endpoint"] == "https://manual.example.com/userinfo"


# =============================================================================
# OIDC Callback
# =============================================================================


@pytest.mark.usefixtures("_mock_audit_dispatcher", "_mock_audit_emission")
class TestOidcCallback:
    """Tests for the /auth/oidc/callback endpoint."""

    @pytest.mark.asyncio
    async def test_handles_error_parameter_from_idp(self) -> None:
        """Should redirect to login with error when IDP returns error."""
        request = _make_request()
        db = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://localhost:3000"]

        with (
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router.OIDCService") as mock_oidc_cls,
        ):
            mock_oidc_cls.return_value.retrieve_oidc_state.return_value = {
                "provider_id": str(uuid4()),
                "nonce": "n",
                "code_verifier": "cv",
                "origin": "http://localhost:3000",
            }
            response = await oidc_callback(
                state="some-state",
                request=request,
                db=db,
                code=None,
                error="invalid_scope",
                error_description="Requested scope is invalid",
            )

        assert response.status_code == 302
        assert "auth_error=auth_failed" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_handles_missing_code_parameter(self) -> None:
        """Should redirect to login with error when code is missing."""
        request = _make_request()
        db = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://localhost:3000"]

        with (
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router.OIDCService") as mock_oidc_cls,
        ):
            mock_oidc_cls.return_value.retrieve_oidc_state.return_value = {
                "provider_id": str(uuid4()),
                "nonce": "n",
                "code_verifier": "cv",
                "origin": "http://localhost:3000",
            }
            response = await oidc_callback(
                state="some-state",
                request=request,
                db=db,
                code=None,
                error=None,
            )

        assert response.status_code == 302
        assert "auth_error=" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_handles_invalid_expired_state(self) -> None:
        """Should redirect to login with error when state is invalid/expired."""
        request = _make_request()

        db = AsyncMock()

        mock_svc = _make_oidc_service_mock()
        mock_svc.retrieve_oidc_state.return_value = None  # State not found

        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://localhost:3000"]

        with (
            patch("syntara.auth.router.OIDCService", return_value=mock_svc),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
        ):
            response = await oidc_callback(
                state="invalid-state",
                request=request,
                db=db,
                code="auth-code-123",
            )

        assert response.status_code == 302
        assert "auth_error=" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_successfully_creates_new_user_from_oidc_claims(self) -> None:
        """Should create new user when email doesn't exist."""
        provider = _make_provider(name="Google")
        new_user = _make_user(email="newuser@example.com", username="newuser")
        new_identity = _make_identity(user_id=new_user.id, provider_id=provider.id)
        request = _make_request()

        state_data = {
            "provider_id": str(provider.id),
            "nonce": "test-nonce",
            "code_verifier": "test-verifier",
        }

        user_claims = _make_user_claims(email="newuser@example.com", preferred_username="newuser")

        db = AsyncMock()
        # Provider query
        provider_result = MagicMock()
        provider_result.one_or_none.return_value = provider
        db.exec.return_value = provider_result

        mock_oidc_service = _make_oidc_service_mock(state_data=state_data, user_claims=user_claims)

        mock_token_service = MagicMock()
        mock_token_service.create_refresh_token.return_value = ("refresh-jwt", "jti-123", datetime.now(UTC))

        mock_store = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://localhost:3000"]
        mock_settings.jwt_refresh_token_lifetime_hours = 8

        with (
            patch("syntara.auth.router.OIDCService", return_value=mock_oidc_service),
            patch("syntara.auth.router._get_token_service", return_value=mock_token_service),
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router.set_refresh_cookie") as mock_set_cookie,
            patch("syntara.auth.router._resolve_oidc_user", AsyncMock(return_value=(new_user, new_identity))),
            patch("syntara.auth.router.sync_idp_groups", AsyncMock()),
            patch("syntara.auth.router.generate_csrf_seed", return_value="test-seed"),
            patch("syntara.auth.router.set_csrf_cookie"),
        ):
            response = await oidc_callback(
                state="valid-state",
                request=request,
                db=db,
                code="auth-code-123",
            )

        assert response.status_code == 302
        assert response.headers["location"] == "http://localhost:3000"
        mock_set_cookie.assert_called_once()

    @pytest.mark.asyncio
    async def test_matches_existing_user_by_email(self) -> None:
        """Should find and use existing user when email matches."""
        provider = _make_provider(name="Azure")
        existing_user = _make_user(email="existing@example.com", username="existinguser")
        existing_identity = _make_identity(user_id=existing_user.id, provider_id=provider.id)
        request = _make_request()

        state_data = {
            "provider_id": str(provider.id),
            "nonce": "test-nonce",
            "code_verifier": "test-verifier",
        }

        user_claims = _make_user_claims(email="existing@example.com")

        db = AsyncMock()
        # Provider query
        provider_result = MagicMock()
        provider_result.one_or_none.return_value = provider
        db.exec.return_value = provider_result

        mock_oidc_service = _make_oidc_service_mock(state_data=state_data, user_claims=user_claims)

        mock_token_service = MagicMock()
        mock_token_service.create_refresh_token.return_value = ("refresh-jwt", "jti-123", datetime.now(UTC))

        mock_store = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://localhost:3000"]
        mock_settings.jwt_refresh_token_lifetime_hours = 8

        with (
            patch("syntara.auth.router.OIDCService", return_value=mock_oidc_service),
            patch("syntara.auth.router._get_token_service", return_value=mock_token_service),
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router.set_refresh_cookie"),
            patch("syntara.auth.router._resolve_oidc_user", AsyncMock(return_value=(existing_user, existing_identity))),
            patch("syntara.auth.router.sync_idp_groups", AsyncMock()),
            patch("syntara.auth.router.generate_csrf_seed", return_value="test-seed"),
            patch("syntara.auth.router.set_csrf_cookie"),
        ):
            response = await oidc_callback(
                state="valid-state",
                request=request,
                db=db,
                code="auth-code-123",
            )

        assert response.status_code == 302

    @pytest.mark.asyncio
    async def test_rejects_inactive_user(self) -> None:
        """Should redirect to login with error for inactive user."""
        provider = _make_provider()
        request = _make_request()

        state_data = {
            "provider_id": str(provider.id),
            "nonce": "test-nonce",
            "code_verifier": "test-verifier",
        }

        user_claims = _make_user_claims(email="inactive@example.com")

        db = AsyncMock()
        # Provider query
        provider_result = MagicMock()
        provider_result.one_or_none.return_value = provider
        db.exec.return_value = provider_result

        mock_oidc_service = _make_oidc_service_mock(state_data=state_data, user_claims=user_claims)

        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://localhost:3000"]

        with (
            patch("syntara.auth.router.OIDCService", return_value=mock_oidc_service),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch(
                "syntara.auth.router._resolve_oidc_user",
                AsyncMock(side_effect=OIDCError("User account is deactivated")),
            ),
        ):
            response = await oidc_callback(
                state="valid-state",
                request=request,
                db=db,
                code="auth-code-123",
            )

        assert response.status_code == 302
        assert "auth_error=" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_handles_username_collision(self) -> None:
        """Should redirect with error when _resolve_oidc_user fails."""
        provider = _make_provider()
        request = _make_request()

        state_data = {
            "provider_id": str(provider.id),
            "nonce": "test-nonce",
            "code_verifier": "test-verifier",
        }

        user_claims = _make_user_claims(email="newuser@example.com", preferred_username="alice")

        db = AsyncMock()
        # Provider query
        provider_result = MagicMock()
        provider_result.one_or_none.return_value = provider
        db.exec.return_value = provider_result

        mock_oidc_service = _make_oidc_service_mock(state_data=state_data, user_claims=user_claims)

        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://localhost:3000"]

        with (
            patch("syntara.auth.router.OIDCService", return_value=mock_oidc_service),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router._resolve_oidc_user", AsyncMock(side_effect=OIDCError("Username already taken"))),
        ):
            response = await oidc_callback(
                state="valid-state",
                request=request,
                db=db,
                code="auth-code-123",
            )

        assert response.status_code == 302
        assert "auth_error=" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_sets_refresh_cookie_and_redirects_to_base_url(self) -> None:
        """Should set refresh cookie and redirect to base URL."""
        provider = _make_provider()
        test_user = _make_user(email="user@example.com")
        test_identity = _make_identity(user_id=test_user.id, provider_id=provider.id)
        request = _make_request()

        state_data = {
            "provider_id": str(provider.id),
            "nonce": "test-nonce",
            "code_verifier": "test-verifier",
        }

        user_claims = _make_user_claims()

        db = AsyncMock()
        provider_result = MagicMock()
        provider_result.one_or_none.return_value = provider
        db.exec.return_value = provider_result

        mock_oidc_service = _make_oidc_service_mock(state_data=state_data, user_claims=user_claims)

        mock_token_service = MagicMock()
        mock_token_service.create_refresh_token.return_value = ("refresh-jwt-token", "jti-999", datetime.now(UTC))

        mock_store = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "https://app.example.com"
        mock_settings.cors_allow_origins = ["https://app.example.com"]
        mock_settings.jwt_refresh_token_lifetime_hours = 24

        with (
            patch("syntara.auth.router.OIDCService", return_value=mock_oidc_service),
            patch("syntara.auth.router._get_token_service", return_value=mock_token_service),
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router.set_refresh_cookie") as mock_set_cookie,
            patch("syntara.auth.router._resolve_oidc_user", AsyncMock(return_value=(test_user, test_identity))),
            patch("syntara.auth.router.sync_idp_groups", AsyncMock()),
            patch("syntara.auth.router.generate_csrf_seed", return_value="test-seed"),
            patch("syntara.auth.router.set_csrf_cookie"),
        ):
            response = await oidc_callback(
                state="valid-state",
                request=request,
                db=db,
                code="auth-code-123",
            )

        assert response.status_code == 302
        assert response.headers["location"] == "https://app.example.com"
        mock_set_cookie.assert_called_once()
        call_args = mock_set_cookie.call_args
        assert call_args[0][1] == "refresh-jwt-token"
        assert call_args[1]["max_age"] == 24 * 3600

    @pytest.mark.asyncio
    async def test_stores_amr_fed_and_idp_in_session(self) -> None:
        """Should store amr=['fed'] and idp in session."""
        provider = _make_provider(name="Okta")
        test_user = _make_user(email="user@example.com")
        test_identity = _make_identity(user_id=test_user.id, provider_id=provider.id)
        request = _make_request()

        state_data = {
            "provider_id": str(provider.id),
            "nonce": "test-nonce",
            "code_verifier": "test-verifier",
        }

        user_claims = _make_user_claims()

        db = AsyncMock()
        provider_result = MagicMock()
        provider_result.one_or_none.return_value = provider
        db.exec.return_value = provider_result

        mock_oidc_service = _make_oidc_service_mock(state_data=state_data, user_claims=user_claims)

        mock_token_service = MagicMock()
        mock_token_service.create_refresh_token.return_value = ("refresh-jwt", "jti-555", datetime.now(UTC))

        mock_store = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://localhost:3000"]
        mock_settings.jwt_refresh_token_lifetime_hours = 8

        with (
            patch("syntara.auth.router.OIDCService", return_value=mock_oidc_service),
            patch("syntara.auth.router._get_token_service", return_value=mock_token_service),
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router.set_refresh_cookie"),
            patch("syntara.auth.router._resolve_oidc_user", AsyncMock(return_value=(test_user, test_identity))),
            patch("syntara.auth.router.sync_idp_groups", AsyncMock()),
            patch("syntara.auth.router.generate_csrf_seed", return_value="test-seed"),
            patch("syntara.auth.router.set_csrf_cookie"),
        ):
            await oidc_callback(
                state="valid-state",
                request=request,
                db=db,
                code="auth-code-123",
            )

        # Verify session was created with correct amr and idp
        mock_store.create.assert_called_once()
        call_kwargs = mock_store.create.call_args.kwargs
        assert call_kwargs["amr"] == ["fed"]
        assert call_kwargs["idp"] == "Okta"

    @pytest.mark.asyncio
    async def test_raises_503_when_session_store_unavailable(self) -> None:
        """OIDC callback should raise SessionStoreUnavailableError when DB is down."""
        provider = _make_provider()
        request = _make_request()

        state_data = {
            "provider_id": str(provider.id),
            "nonce": "test-nonce",
            "code_verifier": "test-verifier",
        }

        user_claims = _make_user_claims()

        db = AsyncMock()
        _add_begin_nested(db)
        provider_result = MagicMock()
        provider_result.one_or_none.return_value = provider
        identity_result = MagicMock()
        identity_result.one_or_none.return_value = None
        email_check_result = MagicMock()
        email_check_result.one_or_none.return_value = None
        username_result = MagicMock()
        username_result.one_or_none.return_value = None
        # create_identity checks is_builtin and auth_type on the auto-created user
        from syntara.core.models.user import AuthType

        auto_created_user = MagicMock()
        auto_created_user.auth_type = AuthType.FEDERATED
        auto_created_user.is_builtin = False
        auth_type_result = MagicMock()
        auth_type_result.one_or_none.return_value = auto_created_user
        auth_group_result = MagicMock()
        auth_group_result.first.return_value = MagicMock(id=uuid4())
        auth_group_insert_result = MagicMock()
        db.exec.side_effect = [
            provider_result,
            identity_result,
            email_check_result,
            username_result,
            auth_group_result,
            auth_group_insert_result,
            auth_type_result,
        ]

        mock_oidc_service = _make_oidc_service_mock(state_data=state_data, user_claims=user_claims)

        mock_token_service = MagicMock()
        mock_token_service.create_refresh_token.return_value = ("refresh-jwt", "jti-1", datetime.now(UTC))

        mock_store = AsyncMock()
        mock_store.create.side_effect = SQLAlchemyError("DB connection failed")

        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://localhost:3000"]

        with (
            patch("syntara.auth.router.OIDCService", return_value=mock_oidc_service),
            patch("syntara.auth.router._get_token_service", return_value=mock_token_service),
            patch("syntara.auth.router.create_session_store", _patch_session_store(mock_store)),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router.sync_idp_groups", new_callable=AsyncMock, return_value=True),
            pytest.raises(SessionStoreUnavailableError),
        ):
            await oidc_callback(
                state="valid-state",
                request=request,
                db=db,
                code="auth-code-123",
            )

        db.commit.assert_not_called()


# =============================================================================
# Load Enabled Provider
# =============================================================================


class TestLoadEnabledProvider:
    """Tests for the _load_enabled_provider helper function."""

    @pytest.mark.asyncio
    async def test_returns_provider_when_enabled_and_not_deleted(self) -> None:
        """Should return provider when it is enabled."""
        provider = _make_provider(enabled=True)
        provider_id = provider.id

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = provider
        db.exec.return_value = mock_result

        result = await _load_enabled_provider(db, provider_id)

        assert result == provider
        assert result.enabled is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario", ["not_found", "disabled", "deleted"])
    async def test_raises_when_provider_unavailable(self, scenario: str) -> None:
        """Should raise OIDCError when provider is not found, disabled, or deleted."""
        provider_id = uuid4()

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None  # Query filters out unavailable providers
        db.exec.return_value = mock_result

        with pytest.raises(OIDCError):
            await _load_enabled_provider(db, provider_id)


# =============================================================================
# Exchange and Validate Tokens
# =============================================================================


class TestExchangeAndValidateTokens:
    """Tests for the _exchange_and_validate_tokens helper function."""

    @pytest.mark.asyncio
    async def test_returns_user_claims_on_success(self) -> None:
        """Should return user claims when token exchange and validation succeed."""
        discovery = _make_discovery_response()
        config = _make_oidc_config()
        mock_oidc_service = _make_oidc_service_mock(user_claims=_make_user_claims())

        user_claims, _raw_merged, id_token_raw = await _exchange_and_validate_tokens(
            oidc_service=mock_oidc_service,
            discovery=discovery,
            config=config,
            redirect_uri="http://localhost:8000/callback",
            code="auth-code",
            code_verifier="verifier-abc",
            nonce="nonce-xyz",
        )

        assert user_claims["email"] == "user@example.com"
        assert isinstance(_raw_merged, dict)
        assert isinstance(id_token_raw, str)
        mock_oidc_service.exchange_code_for_tokens.assert_called_once()
        mock_oidc_service.validate_id_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_token_exchange_failure(self) -> None:
        """Should raise OIDCError when token exchange fails."""
        discovery = _make_discovery_response()
        config = _make_oidc_config()
        mock_oidc_service = _make_oidc_service_mock()
        mock_oidc_service.exchange_code_for_tokens = AsyncMock(side_effect=OIDCError("Exchange failed"))

        with pytest.raises(OIDCError):
            await _exchange_and_validate_tokens(
                oidc_service=mock_oidc_service,
                discovery=discovery,
                config=config,
                redirect_uri="http://localhost:8000/callback",
                code="bad-code",
                code_verifier="verifier",
                nonce="nonce",
            )

    @pytest.mark.asyncio
    async def test_raises_when_no_id_token_in_response(self) -> None:
        """Should raise OIDCError when id_token is missing."""
        discovery = _make_discovery_response()
        config = _make_oidc_config()
        mock_oidc_service = _make_oidc_service_mock()
        mock_oidc_service.exchange_code_for_tokens = AsyncMock(
            return_value={"access_token": "access-token-123"}  # id_token missing!
        )

        with pytest.raises(OIDCError):
            await _exchange_and_validate_tokens(
                oidc_service=mock_oidc_service,
                discovery=discovery,
                config=config,
                redirect_uri="http://localhost:8000/callback",
                code="auth-code",
                code_verifier="verifier",
                nonce="nonce",
            )

    @pytest.mark.asyncio
    async def test_raises_on_id_token_validation_failure(self) -> None:
        """Should raise OIDCError when ID token validation fails."""
        discovery = _make_discovery_response()
        config = _make_oidc_config()
        mock_oidc_service = _make_oidc_service_mock()
        mock_oidc_service.exchange_code_for_tokens = AsyncMock(
            return_value={"access_token": "access-token-123", "id_token": "invalid-id-token-jwt"}
        )
        mock_oidc_service.validate_id_token.side_effect = OIDCError("Invalid signature")

        with pytest.raises(OIDCError):
            await _exchange_and_validate_tokens(
                oidc_service=mock_oidc_service,
                discovery=discovery,
                config=config,
                redirect_uri="http://localhost:8000/callback",
                code="auth-code",
                code_verifier="verifier",
                nonce="nonce",
            )

    @pytest.mark.asyncio
    async def test_supplements_claims_from_userinfo_when_email_missing(self) -> None:
        """Should fetch userinfo and merge claims when ID token is missing email."""
        discovery = _make_discovery_response()
        config = _make_oidc_config()
        mock_oidc_service = _make_oidc_service_mock()
        mock_oidc_service.exchange_code_for_tokens = AsyncMock(
            return_value={"access_token": "access-token-123", "id_token": "id-token-jwt"}
        )
        mock_oidc_service.validate_id_token.return_value = {"sub": "oidc-sub"}
        # ID token has no email/name
        mock_oidc_service.extract_user_claims.side_effect = [
            {"sub": "oidc-sub", "email": None, "name": None, "preferred_username": None},
            {"sub": "oidc-sub", "email": "user@example.com", "name": "Test User", "preferred_username": "testuser"},
        ]
        mock_oidc_service.fetch_userinfo = AsyncMock(
            return_value={
                "sub": "oidc-sub",
                "email": "user@example.com",
                "name": "Test User",
                "preferred_username": "testuser",
            }
        )

        user_claims, _raw_merged, _id_token_raw = await _exchange_and_validate_tokens(
            oidc_service=mock_oidc_service,
            discovery=discovery,
            config=config,
            redirect_uri="http://localhost:8000/callback",
            code="auth-code",
            code_verifier="verifier",
            nonce="nonce",
        )

        assert user_claims["email"] == "user@example.com"
        assert user_claims["name"] == "Test User"
        mock_oidc_service.fetch_userinfo.assert_called_once_with(
            "https://idp.example.com/oauth/userinfo",
            "access-token-123",
            disable_tls_verify=config.disable_tls_verify,
        )

    @pytest.mark.asyncio
    async def test_id_token_claims_take_precedence_over_userinfo(self) -> None:
        """ID token claims should not be overwritten by userinfo (OIDC Core §5.3.2)."""
        discovery = _make_discovery_response()
        config = _make_oidc_config()
        mock_oidc_service = _make_oidc_service_mock()
        mock_oidc_service.exchange_code_for_tokens = AsyncMock(
            return_value={"access_token": "access-token-123", "id_token": "id-token-jwt"}
        )
        mock_oidc_service.validate_id_token.return_value = {"sub": "oidc-sub", "email": "idtoken@example.com"}
        # ID token has email but no name — should fetch userinfo for name but keep email from ID token
        mock_oidc_service.extract_user_claims.side_effect = [
            {"sub": "oidc-sub", "email": "idtoken@example.com", "name": None, "preferred_username": None},
            {
                "sub": "oidc-sub",
                "email": "userinfo@example.com",
                "name": "Userinfo Name",
                "preferred_username": "uiuser",
            },
        ]
        mock_oidc_service.fetch_userinfo = AsyncMock(
            return_value={
                "sub": "oidc-sub",
                "email": "userinfo@example.com",
                "name": "Userinfo Name",
                "preferred_username": "uiuser",
            }
        )

        user_claims, _raw_merged, _id_token_raw = await _exchange_and_validate_tokens(
            oidc_service=mock_oidc_service,
            discovery=discovery,
            config=config,
            redirect_uri="http://localhost:8000/callback",
            code="auth-code",
            code_verifier="verifier",
            nonce="nonce",
        )

        # email from ID token must not be overwritten
        assert user_claims["email"] == "idtoken@example.com"
        # name should come from userinfo since it was missing
        assert user_claims["name"] == "Userinfo Name"

    @pytest.mark.asyncio
    async def test_skips_userinfo_when_claims_complete(self) -> None:
        """Should not call userinfo when ID token has all needed claims."""
        discovery = _make_discovery_response()
        config = _make_oidc_config()
        mock_oidc_service = _make_oidc_service_mock()
        mock_oidc_service.exchange_code_for_tokens = AsyncMock(
            return_value={"access_token": "access-token-123", "id_token": "id-token-jwt"}
        )
        mock_oidc_service.validate_id_token.return_value = {"sub": "oidc-sub"}
        mock_oidc_service.extract_user_claims.return_value = _make_user_claims()
        mock_oidc_service.fetch_userinfo = AsyncMock()

        await _exchange_and_validate_tokens(
            oidc_service=mock_oidc_service,
            discovery=discovery,
            config=config,
            redirect_uri="http://localhost:8000/callback",
            code="auth-code",
            code_verifier="verifier",
            nonce="nonce",
        )

        mock_oidc_service.fetch_userinfo.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_userinfo_when_no_endpoint(self) -> None:
        """Should not call userinfo when no userinfo_endpoint in discovery."""
        discovery = _make_discovery_response()
        del discovery["userinfo_endpoint"]
        config = _make_oidc_config()
        mock_oidc_service = _make_oidc_service_mock()
        mock_oidc_service.exchange_code_for_tokens = AsyncMock(
            return_value={"access_token": "access-token-123", "id_token": "id-token-jwt"}
        )
        mock_oidc_service.validate_id_token.return_value = {"sub": "oidc-sub"}
        mock_oidc_service.extract_user_claims.return_value = {
            "sub": "oidc-sub",
            "email": None,
            "name": None,
            "preferred_username": None,
        }
        mock_oidc_service.fetch_userinfo = AsyncMock()

        await _exchange_and_validate_tokens(
            oidc_service=mock_oidc_service,
            discovery=discovery,
            config=config,
            redirect_uri="http://localhost:8000/callback",
            code="auth-code",
            code_verifier="verifier",
            nonce="nonce",
        )

        mock_oidc_service.fetch_userinfo.assert_not_called()

    @pytest.mark.asyncio
    async def test_continues_when_userinfo_fails(self) -> None:
        """Should proceed with ID token claims when userinfo fetch fails."""
        discovery = _make_discovery_response()
        config = _make_oidc_config()
        mock_oidc_service = _make_oidc_service_mock()
        mock_oidc_service.exchange_code_for_tokens = AsyncMock(
            return_value={"access_token": "access-token-123", "id_token": "id-token-jwt"}
        )
        mock_oidc_service.validate_id_token.return_value = {"sub": "oidc-sub"}
        mock_oidc_service.extract_user_claims.return_value = {
            "sub": "oidc-sub",
            "email": None,
            "name": None,
            "preferred_username": None,
        }
        mock_oidc_service.fetch_userinfo = AsyncMock(side_effect=OIDCError("Userinfo failed"))

        # Should NOT raise — userinfo failure is non-fatal
        user_claims, _raw_merged, _id_token_raw = await _exchange_and_validate_tokens(
            oidc_service=mock_oidc_service,
            discovery=discovery,
            config=config,
            redirect_uri="http://localhost:8000/callback",
            code="auth-code",
            code_verifier="verifier",
            nonce="nonce",
        )

        assert user_claims["email"] is None


# =============================================================================
# Find or Create OIDC User
# =============================================================================


class TestResolveOidcUser:
    """Tests for the _resolve_oidc_user helper function."""

    @pytest.mark.asyncio
    @patch("syntara.auth.router.UserIdentityService")
    async def test_returns_user_linked_by_identity(self, mock_svc_cls: MagicMock) -> None:
        """Should return user when identity (issuer, sub) is found."""
        existing_user = _make_user(email="existing@example.com")
        provider = _make_provider()
        user_claims = _make_user_claims(email="existing@example.com")

        mock_svc = mock_svc_cls.return_value
        mock_identity = MagicMock()
        mock_identity.user_id = existing_user.id
        mock_svc.find_by_issuer_and_subject = AsyncMock(return_value=mock_identity)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = existing_user
        db.exec.return_value = mock_result

        user, identity = await _resolve_oidc_user(db, user_claims, provider)
        assert user == existing_user
        assert identity == mock_identity

    @pytest.mark.asyncio
    @patch("syntara.auth.router.UserIdentityService")
    async def test_creates_new_user_when_identity_not_found(self, mock_svc_cls: MagicMock) -> None:
        """Should create a new user when no identity exists for (issuer, sub)."""
        provider = _make_provider()
        user_claims = _make_user_claims(email="new@example.com", preferred_username="newuser")

        mock_svc = mock_svc_cls.return_value
        mock_svc.find_by_issuer_and_subject = AsyncMock(return_value=None)
        mock_svc.create_identity = AsyncMock()

        db = AsyncMock()
        _add_begin_nested(db)
        # Username check (not taken)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        user, identity = await _resolve_oidc_user(db, user_claims, provider)
        assert user.username == "newuser"
        mock_svc.create_identity.assert_called_once()
        assert identity is not None

    @pytest.mark.asyncio
    @patch("syntara.auth.router.UserIdentityService")
    async def test_creates_new_user_with_mixed_case_email(self, mock_svc_cls: MagicMock) -> None:
        """Should create a new user when identity not found, preserving email from claim."""
        provider = _make_provider()
        user_claims = _make_user_claims(email="User@Example.COM")

        mock_svc = mock_svc_cls.return_value
        mock_svc.find_by_issuer_and_subject = AsyncMock(return_value=None)
        mock_svc.create_identity = AsyncMock()

        db = AsyncMock()
        _add_begin_nested(db)
        # Username check (not taken)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        result = await _resolve_oidc_user(db, user_claims, provider)

        assert result is not None
        mock_svc.create_identity.assert_called_once()

    @pytest.mark.asyncio
    @patch("syntara.auth.router.UserIdentityService")
    async def test_succeeds_when_no_email_claim(self, mock_svc_cls: MagicMock) -> None:
        """Should create user without email when email claim is missing."""
        provider = _make_provider()
        user_claims: dict[str, str | None] = {
            "sub": "user-sub",
            "email": None,
            "name": "Test User",
            "preferred_username": "testuser",
        }

        mock_svc = mock_svc_cls.return_value
        mock_svc.find_by_issuer_and_subject = AsyncMock(return_value=None)
        mock_svc.create_identity = AsyncMock()

        db = AsyncMock()
        _add_begin_nested(db)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        user, _identity = await _resolve_oidc_user(db, user_claims, provider)
        assert user.username == "testuser"
        assert user.email is None

    @pytest.mark.asyncio
    @patch("syntara.auth.router.UserIdentityService")
    async def test_blocks_login_when_email_already_exists(self, mock_svc_cls: MagicMock) -> None:
        """Should block login when email is already associated with another account."""
        existing_user = _make_user(email="taken@example.com", username="existing")
        provider = _make_provider()
        user_claims: dict[str, str | None] = {
            "sub": "new-sub",
            "email": "taken@example.com",
            "name": "New User",
            "preferred_username": "newuser",
        }

        mock_svc = mock_svc_cls.return_value
        mock_svc.find_by_issuer_and_subject = AsyncMock(return_value=None)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = existing_user
        db.exec.return_value = mock_result

        with pytest.raises(OIDCError, match="already associated with an existing account") as exc_info:
            await _resolve_oidc_user(db, user_claims, provider)
        assert exc_info.value.error_code == OIDCErrorCode.EMAIL_ALREADY_LINKED

    @pytest.mark.asyncio
    async def test_raises_when_no_sub_claim(self) -> None:
        """Should raise OIDCError when sub claim is missing."""
        provider = _make_provider()
        user_claims: dict[str, str | None] = {
            "sub": None,
            "email": "user@example.com",
            "name": "Test User",
            "preferred_username": "testuser",
        }

        db = AsyncMock()

        with pytest.raises(OIDCError):
            await _resolve_oidc_user(db, user_claims, provider)

    @pytest.mark.asyncio
    @patch("syntara.auth.router.UserIdentityService")
    async def test_raises_when_user_is_inactive(self, mock_svc_cls: MagicMock) -> None:
        """Should raise OIDCError when linked user is inactive."""
        inactive_user = _make_user(email="inactive@example.com", is_enabled=False)
        provider = _make_provider()
        user_claims = _make_user_claims(email="inactive@example.com")

        mock_svc = mock_svc_cls.return_value
        mock_identity = MagicMock()
        mock_identity.user_id = inactive_user.id
        mock_svc.find_by_issuer_and_subject = AsyncMock(return_value=mock_identity)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = inactive_user
        db.exec.return_value = mock_result

        with pytest.raises(OIDCError):
            await _resolve_oidc_user(db, user_claims, provider)

    @pytest.mark.asyncio
    @patch("syntara.auth.router.UserIdentityService")
    async def test_removes_stale_identity_for_deleted_user_and_creates_new(self, mock_svc_cls: MagicMock) -> None:
        """Should remove stale identity when linked user is soft-deleted and create a new user."""
        deleted_user_id = uuid4()
        provider = _make_provider()
        user_claims = _make_user_claims(email="relinked@example.com", preferred_username="relinked")

        mock_svc = mock_svc_cls.return_value
        mock_identity = MagicMock()
        mock_identity.id = uuid4()
        mock_identity.user_id = deleted_user_id
        mock_svc.find_by_issuer_and_subject = AsyncMock(return_value=mock_identity)
        mock_svc.delete_identity = AsyncMock()
        mock_svc.create_identity = AsyncMock()

        db = AsyncMock()
        _add_begin_nested(db)
        # First exec: look up linked user (returns None — soft-deleted)
        # Second exec: email check (no existing user with this email)
        # Third exec: username check (not taken) in _auto_create_user
        deleted_result = MagicMock()
        deleted_result.one_or_none.return_value = None
        email_check_result = MagicMock()
        email_check_result.one_or_none.return_value = None
        not_taken_result = MagicMock()
        not_taken_result.one_or_none.return_value = None
        auth_group_result = MagicMock()
        auth_group_result.first.return_value = MagicMock(id=uuid4())
        auth_group_insert_result = MagicMock()
        db.exec.side_effect = [
            deleted_result,
            email_check_result,
            not_taken_result,
            auth_group_result,
            auth_group_insert_result,
        ]

        user, identity = await _resolve_oidc_user(db, user_claims, provider)

        mock_svc.delete_identity.assert_called_once_with(mock_identity.id, force=True)
        assert user.username == "relinked"
        assert identity is not None

    @pytest.mark.asyncio
    @patch("syntara.auth.router.UserIdentityService")
    async def test_retries_user_resolution_on_toctou_race(self, mock_svc_cls: MagicMock) -> None:
        """Should retry once when concurrent user creation causes OIDCError."""
        provider = _make_provider()
        user_claims = _make_user_claims(email="race@example.com", preferred_username="racer")

        mock_svc = mock_svc_cls.return_value
        mock_svc.find_by_issuer_and_subject = AsyncMock(return_value=None)
        mock_svc.create_identity = AsyncMock()

        db = AsyncMock()
        _add_begin_nested(db)
        not_taken = MagicMock()
        not_taken.one_or_none.return_value = None
        db.exec.return_value = not_taken
        # Attempt 1: first flush (Principal) succeeds, second flush (User) fails with IntegrityError
        # Attempt 2: both flushes succeed
        db.flush.side_effect = [None, IntegrityError("race condition", params=None, orig=Exception()), None, None]

        user, identity = await _resolve_oidc_user(db, user_claims, provider)

        assert user.username == "racer"
        assert identity is not None

    @pytest.mark.asyncio
    @patch("syntara.auth.router.UserIdentityService")
    async def test_rejects_sub_exceeding_max_length(self, mock_svc_cls: MagicMock) -> None:
        """Should raise OIDCError when sub claim exceeds SUBJECT_MAX_LENGTH."""
        provider = _make_provider()
        user_claims: dict[str, str | None] = {
            "sub": "a" * (SUBJECT_MAX_LENGTH + 1),
            "email": "user@example.com",
            "name": "Test User",
            "preferred_username": "testuser",
        }

        db = AsyncMock()

        with pytest.raises(OIDCError, match="exceeds the maximum supported length"):
            await _resolve_oidc_user(db, user_claims, provider)

        mock_svc_cls.return_value.create_identity.assert_not_called()

    @pytest.mark.asyncio
    @patch("syntara.auth.router.UserIdentityService")
    async def test_accepts_sub_at_exact_max_length(self, mock_svc_cls: MagicMock) -> None:
        """Should accept sub claim that is exactly SUBJECT_MAX_LENGTH characters."""
        provider = _make_provider()
        user_claims: dict[str, str | None] = {
            "sub": "a" * SUBJECT_MAX_LENGTH,
            "email": "user@example.com",
            "name": "Test User",
            "preferred_username": "testuser",
        }

        mock_svc = mock_svc_cls.return_value
        mock_svc.find_by_issuer_and_subject = AsyncMock(return_value=None)
        mock_svc.create_identity = AsyncMock()

        db = AsyncMock()
        _add_begin_nested(db)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        _user, identity = await _resolve_oidc_user(db, user_claims, provider)
        assert identity is not None
        mock_svc.create_identity.assert_called_once()


# =============================================================================
# Auto Create User
# =============================================================================


class TestAutoCreateUser:
    """Tests for the _auto_create_user helper function."""

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_emits_group_member_added_for_authenticated_group(
        self,
        mock_do_emit: AsyncMock,
    ) -> None:
        """OIDC auto-create must audit the authenticated group grant (AAP-83643)."""
        AuditEventDispatcher.register({GroupMembershipEvent: GroupMembershipHandler()})
        email = "user@example.com"
        user_claims = _make_user_claims(email=email, preferred_username="alice", name="Alice Smith")
        auth_id = uuid4()
        auth_group = Group(
            id=auth_id,
            name=AUTHENTICATED_GROUP_NAME,
            description="auth",
            is_builtin=True,
            labels={},
        )

        db = AsyncMock()
        _add_begin_nested(db)
        username_result = MagicMock()
        username_result.one_or_none.return_value = None
        auth_group_result = MagicMock()
        auth_group_result.first.return_value = auth_group
        insert_result = MagicMock()
        db.exec.side_effect = [username_result, auth_group_result, insert_result]

        result = await _auto_create_user(db, user_claims, "Google", email=email)

        assert result.username == "alice"
        assert mock_do_emit.call_count == 1
        event = mock_do_emit.call_args.args[0]
        assert event.event_action == "group_member_added"
        assert event.event_category == EventCategory.SECURITY_EVENT
        assert event.structured_data.username == "alice"
        assert event.structured_data.group_name == AUTHENTICATED_GROUP_NAME
        assert event.structured_data.group_id == str(auth_id)
        assert event.structured_data.user_id == str(result.id)

    @pytest.mark.asyncio
    async def test_creates_user_with_preferred_username(self) -> None:
        """Should create user with preferred_username as username."""
        email = "user@example.com"
        user_claims = _make_user_claims(email=email, preferred_username="alice", name="Alice Smith")

        db = AsyncMock()
        _add_begin_nested(db)
        # Username collision check (no collision)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        result = await _auto_create_user(db, user_claims, "Google", email=email)

        assert result.username == "alice"
        assert result.email == email
        assert result.first_name == "Alice Smith"
        assert result.last_name is None
        assert result.is_enabled is True
        assert result.password_hash is None
        assert db.add.call_count == 1
        assert db.flush.call_count == 1

    @pytest.mark.asyncio
    async def test_creates_user_with_given_and_family_name(self) -> None:
        """Should split into first_name/last_name when given_name and family_name are present."""
        email = "user@example.com"
        user_claims = _make_user_claims(
            email=email, preferred_username="alice", given_name="Alice", family_name="Smith"
        )

        db = AsyncMock()
        _add_begin_nested(db)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        result = await _auto_create_user(db, user_claims, "Google", email=email)

        assert result.first_name == "Alice"
        assert result.last_name == "Smith"

    @pytest.mark.asyncio
    async def test_creates_user_with_given_name_only(self) -> None:
        """Should use given_name as first_name with last_name=None when family_name is absent."""
        email = "user@example.com"
        user_claims = _make_user_claims(email=email, preferred_username="alice", given_name="Alice")

        db = AsyncMock()
        _add_begin_nested(db)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        result = await _auto_create_user(db, user_claims, "Google", email=email)

        assert result.first_name == "Alice"
        assert result.last_name is None

    @pytest.mark.asyncio
    async def test_uses_email_prefix_when_no_preferred_username(self) -> None:
        """Should use email prefix when preferred_username is missing."""
        email = "bob@example.com"
        user_claims: dict[str, str | None] = {
            "sub": "user-sub",
            "email": email,
            "name": "Bob Jones",
            "preferred_username": None,
        }

        db = AsyncMock()
        _add_begin_nested(db)
        # Username collision check (no collision)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        result = await _auto_create_user(db, user_claims, "Azure", email=email)

        assert result.username == "bob"  # From email prefix

    @pytest.mark.asyncio
    async def test_raises_error_on_username_collision(self) -> None:
        """Should raise OIDCError when username collides."""
        email = "charlie@example.com"
        user_claims = _make_user_claims(email=email, preferred_username="admin")

        # Existing user with username "admin"
        existing_user = _make_user(username="admin", email="other@example.com")

        db = AsyncMock()
        # Username collision check (collision found)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = existing_user
        db.exec.return_value = mock_result

        with pytest.raises(OIDCError):
            await _auto_create_user(db, user_claims, "Okta", email=email)

    @pytest.mark.asyncio
    async def test_disambiguates_username_with_random_suffix(self) -> None:
        """Should append a random hex suffix when username collides."""
        email = "eve@example.com"
        sub = "oidc-sub-predictable"
        user_claims: dict[str, str | None] = {
            "sub": sub,
            "email": email,
            "name": "Eve",
            "preferred_username": "eve",
        }

        existing_user = _make_user(username="eve", email="other@example.com")

        db = AsyncMock()
        _add_begin_nested(db)
        # First check: "eve" is taken. Second check: "eve-<suffix>" is not taken.
        taken_result = MagicMock()
        taken_result.one_or_none.return_value = existing_user
        not_taken_result = MagicMock()
        not_taken_result.one_or_none.return_value = None
        auth_group_result = MagicMock()
        auth_group_result.first.return_value = MagicMock(id=uuid4())
        auth_group_insert_result = MagicMock()
        db.exec.side_effect = [taken_result, not_taken_result, auth_group_result, auth_group_insert_result]

        result = await _auto_create_user(db, user_claims, "Azure", email=email)

        assert result.username.startswith("eve-")
        suffix = result.username.removeprefix("eve-")
        # Random hex suffix should be 16 chars (token_hex(8))
        assert len(suffix) == 16
        # Verify it's hex
        int(suffix, 16)

    @pytest.mark.asyncio
    async def test_handles_concurrent_username_collision_on_flush(self) -> None:
        """Should raise OIDCError when flush hits IntegrityError (TOCTOU race)."""
        email = "race@example.com"
        user_claims: dict[str, str | None] = {
            "sub": "user-sub",
            "email": email,
            "name": "Racer",
            "preferred_username": "racer",
        }

        db = AsyncMock()
        _add_begin_nested(db)
        # Pre-checks pass (no collision found)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result
        # But flush fails due to concurrent insert
        db.flush.side_effect = IntegrityError("ix_users_username_unique", params=None, orig=Exception())

        with pytest.raises(OIDCError, match="Unable to create account"):
            await _auto_create_user(db, user_claims, "Azure", email=email)

        db.begin_nested.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_concurrent_email_collision_on_flush(self) -> None:
        """Should raise OIDCError when flush hits IntegrityError (TOCTOU race)."""
        email = "race@example.com"
        user_claims: dict[str, str | None] = {
            "sub": "user-sub",
            "email": email,
            "name": "Racer",
            "preferred_username": "racer",
        }

        db = AsyncMock()
        _add_begin_nested(db)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result
        db.flush.side_effect = IntegrityError("ix_users_email_unique", params=None, orig=Exception())

        with pytest.raises(OIDCError, match="Unable to create account"):
            await _auto_create_user(db, user_claims, "Azure", email=email)

    @pytest.mark.asyncio
    async def test_uses_preferred_username_as_first_name_fallback(self) -> None:
        """Should use preferred_username for first_name when name claim missing."""
        email = "dave@example.com"
        user_claims: dict[str, str | None] = {
            "sub": "user-sub",
            "email": email,
            "name": None,  # Missing name
            "preferred_username": "dave",
        }

        db = AsyncMock()
        _add_begin_nested(db)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        result = await _auto_create_user(db, user_claims, "Provider", email=email)

        assert result.first_name == "dave"
        assert result.last_name is None

    @pytest.mark.asyncio
    async def test_creates_user_without_email(self) -> None:
        """Should create user with email=None when no email provided."""
        user_claims: dict[str, str | None] = {
            "sub": "user-sub",
            "email": None,
            "name": "No Email User",
            "preferred_username": "noemail",
        }

        db = AsyncMock()
        _add_begin_nested(db)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        result = await _auto_create_user(db, user_claims, "Provider")

        assert result.email is None
        assert result.username == "noemail"
        assert result.first_name == "No Email User"
        assert result.last_name is None

    @pytest.mark.asyncio
    async def test_username_falls_back_to_sub_when_no_email_or_preferred_username(self) -> None:
        """Should use sub claim for username when both email and preferred_username are missing."""
        user_claims: dict[str, str | None] = {
            "sub": "unique-sub-id",
            "email": None,
            "name": None,
            "preferred_username": None,
        }

        db = AsyncMock()
        _add_begin_nested(db)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        result = await _auto_create_user(db, user_claims, "Provider")

        assert result.email is None
        assert result.username == "unique-sub-id"
        assert result.first_name == "unique-sub-id"
        assert result.last_name is None

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_email(self) -> None:
        """Should strip leading/trailing whitespace from email before storing."""
        padded_email = "  user@example.com  "
        user_claims = _make_user_claims(email=padded_email, preferred_username="alice", name="Alice")

        db = AsyncMock()
        _add_begin_nested(db)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        result = await _auto_create_user(db, user_claims, "Provider", email=padded_email)

        assert result.email == "user@example.com"

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_username(self) -> None:
        """Should strip leading/trailing whitespace from preferred_username."""
        user_claims = _make_user_claims(preferred_username="  alice  ", name="Alice")

        db = AsyncMock()
        _add_begin_nested(db)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        result = await _auto_create_user(db, user_claims, "Provider", email="alice@example.com")

        assert result.username == "alice"

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_name(self) -> None:
        """Should strip leading/trailing whitespace from name claim."""
        user_claims = _make_user_claims(name="  Bob Jones  ", preferred_username="bob")

        db = AsyncMock()
        _add_begin_nested(db)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        result = await _auto_create_user(db, user_claims, "Provider", email="bob@example.com")

        assert result.first_name == "Bob Jones"
        assert result.last_name is None

    @pytest.mark.asyncio
    async def test_truncates_long_first_name(self) -> None:
        """Should truncate first_name to 255 characters when name claim exceeds limit."""
        long_name = "A" * 500
        user_claims = _make_user_claims(name=long_name, preferred_username="user")

        db = AsyncMock()
        _add_begin_nested(db)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        result = await _auto_create_user(db, user_claims, "Provider", email="user@example.com")

        assert len(result.first_name) == FieldLimits.NAME_MAX_LENGTH

    @pytest.mark.asyncio
    async def test_rejects_email_exceeding_max_length(self) -> None:
        """Should raise OIDCError when email exceeds 255 characters."""
        long_email = "a" * 290 + "@b.com"
        user_claims = _make_user_claims(email=long_email, preferred_username="user")

        db = AsyncMock()

        with pytest.raises(OIDCError, match="Email address exceeds maximum length"):
            await _auto_create_user(db, user_claims, "Provider", email=long_email)

    @pytest.mark.asyncio
    async def test_truncates_long_username(self) -> None:
        """Should truncate preferred_username when it exceeds the max length."""
        long_username = "u" * 300
        user_claims = _make_user_claims(preferred_username=long_username, name="User")

        db = AsyncMock()
        _add_begin_nested(db)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        result = await _auto_create_user(db, user_claims, "Provider", email="user@example.com")

        assert len(result.username) == FieldLimits.NAME_MAX_LENGTH - 17

    @pytest.mark.asyncio
    async def test_accepts_email_at_exact_max_length(self) -> None:
        """Should accept email that is exactly 255 characters."""
        exact_email = "a" * (FieldLimits.NAME_MAX_LENGTH - len("@b.com")) + "@b.com"
        assert len(exact_email) == FieldLimits.NAME_MAX_LENGTH
        user_claims = _make_user_claims(email=exact_email, preferred_username="user", name="User")

        db = AsyncMock()
        _add_begin_nested(db)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        result = await _auto_create_user(db, user_claims, "Provider", email=exact_email)

        assert result.email == exact_email

    @pytest.mark.asyncio
    async def test_whitespace_only_username_falls_back_to_email(self) -> None:
        """Should treat whitespace-only preferred_username as empty and fall back to email prefix."""
        user_claims = _make_user_claims(preferred_username="   ", name="User")

        db = AsyncMock()
        _add_begin_nested(db)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        result = await _auto_create_user(db, user_claims, "Provider", email="fallback@example.com")

        assert result.username == "fallback"

    @pytest.mark.asyncio
    async def test_whitespace_only_name_falls_back_to_username(self) -> None:
        """Should treat whitespace-only name claim as empty and use preferred_username for first_name."""
        user_claims = _make_user_claims(name="   ", preferred_username="alice")

        db = AsyncMock()
        _add_begin_nested(db)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        result = await _auto_create_user(db, user_claims, "Provider", email="alice@example.com")

        assert result.first_name == "alice"
        assert result.last_name is None


# =============================================================================
# Safe Redirect URL
# =============================================================================


class TestRevalidateOrigin:
    """Tests for the _revalidate_origin CORS re-validation (AAP-71277)."""

    def test_returns_origin_when_still_allowed(self) -> None:
        """Should return the origin unchanged if it is still in CORS allowed origins."""
        mock_settings = MagicMock()
        mock_settings.cors_allow_origins = ["https://app.example.com", "https://other.example.com"]

        with patch("syntara.auth.router.get_settings", return_value=mock_settings):
            assert _revalidate_origin("https://app.example.com") == "https://app.example.com"

    def test_returns_none_when_origin_removed(self) -> None:
        """Should return None if the origin was removed from CORS allowed origins."""
        mock_settings = MagicMock()
        mock_settings.cors_allow_origins = ["https://other.example.com"]

        with patch("syntara.auth.router.get_settings", return_value=mock_settings):
            assert _revalidate_origin("https://app.example.com") is None

    def test_returns_none_when_cors_origins_empty(self) -> None:
        """Should return None if CORS allowed origins list is empty."""
        mock_settings = MagicMock()
        mock_settings.cors_allow_origins = []

        with patch("syntara.auth.router.get_settings", return_value=mock_settings):
            assert _revalidate_origin("https://app.example.com") is None

    def test_returns_none_for_none_input(self) -> None:
        """Should return None when origin is None (no origin was stored)."""
        assert _revalidate_origin(None) is None

    def test_returns_none_for_empty_string(self) -> None:
        """Should return None when origin is an empty string."""
        assert _revalidate_origin("") is None


class TestSafeRedirectUrl:
    """Tests for the _safe_redirect_url open-redirect protection."""

    def _mock_settings(self, cors_origins: list[str] | None = None) -> MagicMock:
        mock = MagicMock()
        mock.cors_allow_origins = cors_origins or ["https://app.example.com"]
        mock.jwt_issuer = "https://api.example.com"
        return mock

    def test_resolves_relative_path_against_origin(self) -> None:
        """Should resolve relative paths against the frontend origin."""
        assert _safe_redirect_url("/dashboard", origin="https://app.example.com") == "https://app.example.com/dashboard"

    def test_allows_url_in_cors_origins(self) -> None:
        """Should allow absolute URLs whose origin is in CORS_ALLOW_ORIGINS."""
        with patch("syntara.auth.router.get_settings", return_value=self._mock_settings()):
            assert (
                _safe_redirect_url("https://app.example.com/page", origin="https://app.example.com")
                == "https://app.example.com/page"
            )

    def test_rejects_url_not_in_cors_origins(self) -> None:
        """Should reject URLs whose origin is not in CORS_ALLOW_ORIGINS."""
        with patch("syntara.auth.router.get_settings", return_value=self._mock_settings()):
            assert (
                _safe_redirect_url("https://evil.com/steal", origin="https://app.example.com")
                == "https://app.example.com"
            )

    def test_rejects_protocol_relative_url(self) -> None:
        """Should reject protocol-relative URLs like //evil.com."""
        assert _safe_redirect_url("//evil.com/path", origin="https://app.example.com") == "https://app.example.com"

    def test_returns_base_url_for_none(self) -> None:
        """Should return base URL when input is None."""
        assert _safe_redirect_url(None, origin="https://app.example.com") == "https://app.example.com"

    def test_returns_base_url_for_empty_string(self) -> None:
        """Should return base URL when input is empty."""
        assert _safe_redirect_url("", origin="https://app.example.com") == "https://app.example.com"

    def test_falls_back_to_jwt_issuer_when_no_origin(self) -> None:
        """Should fall back to jwt_issuer when no stored origin is available."""
        with patch("syntara.auth.router.get_settings", return_value=self._mock_settings()):
            assert _safe_redirect_url(None) == "https://api.example.com"

    def test_rejects_different_scheme(self) -> None:
        """Should reject URLs with different scheme even if netloc matches."""
        with patch("syntara.auth.router.get_settings", return_value=self._mock_settings()):
            assert (
                _safe_redirect_url("http://app.example.com/page", origin="https://app.example.com")
                == "https://app.example.com"
            )

    def test_rejects_javascript_uri(self) -> None:
        """Should reject javascript: URIs."""
        with patch("syntara.auth.router.get_settings", return_value=self._mock_settings()):
            assert (
                _safe_redirect_url("javascript:alert(1)", origin="https://app.example.com") == "https://app.example.com"
            )

    def test_rejects_when_cors_origins_contains_wildcard(self) -> None:
        """Should reject absolute URLs when CORS origins contain a wildcard."""
        with patch("syntara.auth.router.get_settings", return_value=self._mock_settings(cors_origins=["*"])):
            assert (
                _safe_redirect_url("https://app.example.com/page", origin="https://app.example.com")
                == "https://app.example.com"
            )


# =============================================================================
# Handle Link Flow
# =============================================================================


class TestHandleLinkFlow:
    """Tests for the _handle_link_flow helper function."""

    @pytest.mark.asyncio
    @patch("syntara.auth.router.create_session_store")
    async def test_rejects_when_session_expired(self, mock_store_cls: MagicMock) -> None:
        """Should raise OIDCError when the session JTI is no longer valid."""
        provider = _make_provider()
        user_claims = _make_user_claims(email="user@example.com")
        state_data = {
            "user_id": str(uuid4()),
            "session_jti": "expired-jti",
        }

        mock_store = AsyncMock()
        mock_store.get = AsyncMock(return_value=None)
        mock_store_cls.return_value = mock_store

        db = AsyncMock()

        with pytest.raises(OIDCError, match="Session expired"):
            await _handle_link_flow(db, state_data, user_claims, provider)

    @pytest.mark.asyncio
    @patch("syntara.auth.router.UserIdentityService")
    @patch("syntara.auth.router.create_session_store")
    async def test_succeeds_when_session_is_valid(self, mock_store_cls: MagicMock, mock_svc_cls: MagicMock) -> None:
        """Should create identity when session is still active."""
        user = _make_user(email="user@example.com")
        provider = _make_provider()
        user_claims = _make_user_claims(email="user@example.com")
        state_data = {
            "user_id": str(user.id),
            "session_jti": "valid-jti",
        }

        # Session store returns valid session with matching user_id
        mock_session = MagicMock()
        mock_session.user_id = str(user.id)
        mock_store = AsyncMock()
        mock_store.get = AsyncMock(return_value=mock_session)
        mock_store_cls.return_value = mock_store

        # Identity service
        mock_svc = mock_svc_cls.return_value
        mock_svc.find_by_issuer_and_subject = AsyncMock(return_value=None)
        mock_svc.create_identity = AsyncMock()

        # DB: _load_active_user returns user
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        result_user, result_identity = await _handle_link_flow(db, state_data, user_claims, provider)

        assert result_user == user
        assert result_identity is None
        mock_svc.create_identity.assert_called_once()

    @pytest.mark.asyncio
    @patch("syntara.auth.router.UserIdentityService")
    async def test_proceeds_without_session_jti(self, mock_svc_cls: MagicMock) -> None:
        """Should skip session verification when no session_jti in state (backwards compat)."""
        user = _make_user(email="user@example.com")
        provider = _make_provider()
        user_claims = _make_user_claims(email="user@example.com")
        state_data = {
            "user_id": str(user.id),
            # no session_jti
        }

        mock_svc = mock_svc_cls.return_value
        mock_svc.find_by_issuer_and_subject = AsyncMock(return_value=None)
        mock_svc.create_identity = AsyncMock()

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        result_user, result_identity = await _handle_link_flow(db, state_data, user_claims, provider)

        assert result_user == user
        assert result_identity is None

    @pytest.mark.asyncio
    async def test_rejects_link_for_builtin_user(self) -> None:
        """Should raise OIDCError when the user is a built-in user."""
        user = _make_user(email="builtin@example.com", password_hash="$argon2id$hash", auth_type="local")
        # Mark the user as builtin
        user.is_builtin = True
        provider = _make_provider()
        user_claims = _make_user_claims(email="builtin@example.com")
        state_data = {"user_id": str(user.id)}

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        with pytest.raises(OIDCError, match="Cannot link federated identity to a built-in user"):
            await _handle_link_flow(db, state_data, user_claims, provider)

    @pytest.mark.asyncio
    @patch("syntara.auth.router.UserIdentityService")
    async def test_rejects_identity_already_linked_to_same_user(self, mock_svc_cls: MagicMock) -> None:
        """Should raise when identity is already linked to the requesting user."""
        user = _make_user(email="user@example.com")
        provider = _make_provider()
        user_claims = _make_user_claims(email="user@example.com")
        state_data = {"user_id": str(user.id)}

        mock_svc = mock_svc_cls.return_value
        existing_identity = MagicMock()
        existing_identity.user_id = user.id
        mock_svc.find_by_issuer_and_subject = AsyncMock(return_value=existing_identity)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        with pytest.raises(OIDCError, match="already linked to your account"):
            await _handle_link_flow(db, state_data, user_claims, provider)

    @pytest.mark.asyncio
    @patch("syntara.auth.router.UserIdentityService")
    async def test_rejects_identity_linked_to_another_user(self, mock_svc_cls: MagicMock) -> None:
        """Should raise when identity is already linked to a different user."""
        user = _make_user(email="user@example.com")
        other_user = _make_user(email="other@example.com")
        provider = _make_provider()
        user_claims = _make_user_claims(email="user@example.com")
        state_data = {"user_id": str(user.id)}

        mock_svc = mock_svc_cls.return_value
        existing_identity = MagicMock()
        existing_identity.user_id = other_user.id
        mock_svc.find_by_issuer_and_subject = AsyncMock(return_value=existing_identity)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = other_user
        db.exec.return_value = mock_result

        with pytest.raises(OIDCError, match="already linked to another account"):
            await _handle_link_flow(db, state_data, user_claims, provider)

    @pytest.mark.asyncio
    async def test_rejects_sub_exceeding_max_length_in_link_flow(self) -> None:
        """Should raise OIDCError when sub claim exceeds SUBJECT_MAX_LENGTH during linking."""
        user = _make_user(email="user@example.com")
        provider = _make_provider()
        user_claims: dict[str, str | None] = {
            "sub": "a" * (SUBJECT_MAX_LENGTH + 1),
            "email": "user@example.com",
            "name": "Test User",
            "preferred_username": "testuser",
        }
        state_data = {"user_id": str(user.id)}

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        with pytest.raises(OIDCError, match="exceeds the maximum supported length"):
            await _handle_link_flow(db, state_data, user_claims, provider)

    @pytest.mark.asyncio
    async def test_rejects_missing_sub_in_link_flow(self) -> None:
        """Should raise OIDCError when sub claim is missing during linking."""
        user = _make_user(email="user@example.com")
        provider = _make_provider()
        user_claims: dict[str, str | None] = {
            "sub": None,
            "email": "user@example.com",
            "name": "Test User",
            "preferred_username": "testuser",
        }
        state_data = {"user_id": str(user.id)}

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        with pytest.raises(OIDCError, match="did not return a subject identifier"):
            await _handle_link_flow(db, state_data, user_claims, provider)

    @pytest.mark.asyncio
    @patch("syntara.auth.router.UserIdentityService")
    async def test_raises_oidc_error_on_data_error_in_link_flow(self, mock_svc_cls: MagicMock) -> None:
        """Should catch DataError (e.g. truncation) during linking and raise OIDCError."""
        user = _make_user(email="user@example.com")
        provider = _make_provider()
        user_claims = _make_user_claims(email="user@example.com")
        state_data = {"user_id": str(user.id)}

        mock_svc = mock_svc_cls.return_value
        mock_svc.find_by_issuer_and_subject = AsyncMock(return_value=None)
        mock_svc.create_identity = AsyncMock(side_effect=DataError("truncation", params=None, orig=Exception()))

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        with pytest.raises(OIDCError, match="Unable to link identity"):
            await _handle_link_flow(db, state_data, user_claims, provider)

        db.rollback.assert_called_once()


# =============================================================================
# Auto Create User (from resolve flow)
# =============================================================================


class TestAutoCreateUserFromResolveFlow:
    """Tests for _auto_create_user when called from the identity resolve flow."""

    @pytest.mark.asyncio
    async def test_always_creates_new_user(self) -> None:
        """Should always create a new user."""
        user_claims = _make_user_claims(email="user@example.com", preferred_username="newuser")

        db = AsyncMock()
        _add_begin_nested(db)
        # Username check (not taken)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        result = await _auto_create_user(db, user_claims, "test-provider", email="user@example.com")

        assert result.username == "newuser"
        assert db.add.call_count == 1
        assert db.flush.call_count == 1


# =============================================================================
# Create Identity with Race Handling
# =============================================================================


class TestCreateIdentityWithRaceHandling:
    """Tests for the _create_identity_with_race_handling helper function."""

    @pytest.mark.asyncio
    async def test_creates_identity_on_success(self) -> None:
        """Should create identity and return refreshed user on success."""
        user = _make_user(email="user@example.com")
        provider = _make_provider()

        identity_service = AsyncMock()
        identity_service.create_identity = AsyncMock()

        db = AsyncMock()
        _add_begin_nested(db)

        result_user, result_identity = await _create_identity_with_race_handling(
            db, identity_service, user, provider.id, "https://idp.example.com", "sub-123"
        )

        identity_service.create_identity.assert_called_once_with(
            user_id=user.id,
            identity_provider_id=provider.id,
            issuer="https://idp.example.com",
            subject="sub-123",
        )
        db.refresh.assert_called_once_with(user)
        assert result_user == user
        assert result_identity is not None

    @pytest.mark.asyncio
    async def test_handles_integrity_error_by_resolving_existing(self) -> None:
        """Should handle IntegrityError by looking up the winning identity."""
        user = _make_user(email="user@example.com")
        winner_user = _make_user(email="winner@example.com")
        provider = _make_provider()

        identity_service = AsyncMock()
        identity_service.create_identity = AsyncMock(
            side_effect=IntegrityError("duplicate", params=None, orig=Exception())
        )
        mock_identity = MagicMock()
        mock_identity.user_id = winner_user.id
        identity_service.find_by_issuer_and_subject = AsyncMock(return_value=mock_identity)

        db = AsyncMock()
        _add_begin_nested(db)
        # After savepoint rollback, _load_active_user query
        user_result = MagicMock()
        user_result.one_or_none.return_value = winner_user
        db.exec.return_value = user_result

        result_user, result_identity = await _create_identity_with_race_handling(
            db, identity_service, user, provider.id, "https://idp.example.com", "sub-123"
        )

        db.begin_nested.assert_called_once()
        identity_service.find_by_issuer_and_subject.assert_called_once_with("https://idp.example.com", "sub-123")
        assert result_user == winner_user
        assert result_identity == mock_identity

    @pytest.mark.asyncio
    async def test_raises_oidc_error_when_race_identity_not_found(self) -> None:
        """Should raise OIDCError when IntegrityError occurs but identity can't be found."""
        user = _make_user(email="user@example.com")
        provider = _make_provider()

        identity_service = AsyncMock()
        identity_service.create_identity = AsyncMock(
            side_effect=IntegrityError("duplicate", params=None, orig=Exception())
        )
        identity_service.find_by_issuer_and_subject = AsyncMock(return_value=None)

        db = AsyncMock()
        _add_begin_nested(db)

        with pytest.raises(OIDCError, match="Unable to sign in"):
            await _create_identity_with_race_handling(
                db, identity_service, user, provider.id, "https://idp.example.com", "sub-123"
            )

    @pytest.mark.asyncio
    async def test_raises_oidc_error_on_data_error(self) -> None:
        """Should catch DataError (e.g. truncation) and raise OIDCError."""
        user = _make_user(email="user@example.com")
        provider = _make_provider()

        identity_service = AsyncMock()
        identity_service.create_identity = AsyncMock(side_effect=DataError("truncation", params=None, orig=Exception()))

        db = AsyncMock()
        _add_begin_nested(db)

        with pytest.raises(OIDCError, match="Unable to sign in"):
            await _create_identity_with_race_handling(
                db, identity_service, user, provider.id, "https://idp.example.com", "sub-123"
            )

        identity_service.find_by_issuer_and_subject.assert_not_called()


# =============================================================================
# Load Active User
# =============================================================================


class TestLoadActiveUser:
    """Tests for the _load_active_user helper function."""

    @pytest.mark.asyncio
    async def test_returns_active_user(self) -> None:
        """Should return the user when they exist and are active."""
        user = _make_user(email="active@example.com")
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        result = await _load_active_user(db, user.id)
        assert result == user

    @pytest.mark.asyncio
    async def test_raises_when_user_deleted(self) -> None:
        """Should raise OIDCError when user is soft-deleted."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        db.exec.return_value = mock_result

        with pytest.raises(OIDCError, match="deleted"):
            await _load_active_user(db, uuid4())

    @pytest.mark.asyncio
    async def test_raises_when_user_inactive(self) -> None:
        """Should raise OIDCError when user is deactivated."""
        user = _make_user(email="inactive@example.com", is_enabled=False)
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = user
        db.exec.return_value = mock_result

        with pytest.raises(OIDCError, match="Authentication failed"):
            await _load_active_user(db, user.id)


# =============================================================================
# OIDC Callback — link flow and safety net
# =============================================================================


class TestOidcCallbackLinkFlow:
    """Tests for link flow and safety-net paths in oidc_callback."""

    @pytest.mark.asyncio
    async def test_link_flow_redirects_without_creating_session(self) -> None:
        """Should redirect to redirect_to on successful link flow without creating a session."""
        user = _make_user(email="user@example.com")
        provider = _make_provider(name="Azure")
        request = _make_request()

        state_data = {
            "provider_id": str(provider.id),
            "nonce": "nonce-xyz",
            "code_verifier": "verifier-123",
            "flow_type": "link",
            "origin": "https://app.example.com",
            "redirect_to": "/settings/identities",
        }

        db = AsyncMock()
        provider_result = MagicMock()
        provider_result.one_or_none.return_value = provider
        db.exec.return_value = provider_result

        mock_oidc_service = _make_oidc_service_mock(state_data=state_data, user_claims=_make_user_claims())
        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "https://app.example.com"
        mock_settings.cors_allow_origins = ["https://app.example.com"]

        with (
            patch("syntara.auth.router.OIDCService", return_value=mock_oidc_service),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router._process_link_callback", AsyncMock(return_value=(user, None))),
        ):
            response = await oidc_callback(
                state="valid-state",
                request=request,
                db=db,
                code="auth-code",
            )

        assert response.status_code == 302
        assert "/settings/identities" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_link_flow_error_redirects_with_link_error(self) -> None:
        """Should redirect to redirect_to with link_error param on link flow failure."""
        request = _make_request()
        db = AsyncMock()

        error = OIDCCallbackError(
            "This identity is already linked",
            error_code=OIDCErrorCode.LINK_FAILED,
            origin="https://app.example.com",
            redirect_to="https://app.example.com/settings/identities",
        )

        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "https://app.example.com"
        mock_settings.cors_allow_origins = ["https://app.example.com"]

        with (
            patch("syntara.auth.router._process_oidc_callback", AsyncMock(side_effect=error)),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
        ):
            response = await oidc_callback(
                state="valid-state",
                request=request,
                db=db,
                code="auth-code",
            )

        assert response.status_code == 302
        location = response.headers["location"]
        assert "link_error=" in location
        assert "settings/identities" in location

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_generic_error(self) -> None:
        """Should catch unexpected exceptions and redirect with generic auth_error."""
        request = _make_request()
        db = AsyncMock()
        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://localhost:3000"]

        with (
            patch("syntara.auth.router._process_oidc_callback", AsyncMock(side_effect=RuntimeError("unexpected"))),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
        ):
            response = await oidc_callback(
                state="valid-state",
                request=request,
                db=db,
                code="auth-code",
            )

        assert response.status_code == 302
        assert "auth_error=" in response.headers["location"]


class TestResolveOidcUserRetryExhausted:
    """Tests for _resolve_oidc_user when retry is exhausted."""

    @pytest.mark.asyncio
    @patch("syntara.auth.router.UserIdentityService")
    async def test_raises_after_two_failures(self, mock_svc_cls: MagicMock) -> None:
        """Should raise OIDCError when both creation attempts fail."""
        provider = _make_provider()
        user_claims = _make_user_claims(email="retry@example.com", preferred_username="retry")

        mock_svc = mock_svc_cls.return_value
        mock_svc.find_by_issuer_and_subject = AsyncMock(return_value=None)

        db = AsyncMock()
        _add_begin_nested(db)
        not_taken = MagicMock()
        not_taken.one_or_none.return_value = None
        db.exec.return_value = not_taken
        # Both flush attempts fail
        db.flush.side_effect = [
            IntegrityError("race", params=None, orig=Exception()),
            IntegrityError("race again", params=None, orig=Exception()),
        ]

        with pytest.raises(OIDCError):
            await _resolve_oidc_user(db, user_claims, provider)


# =============================================================================
# Test Sign-In Flow
# =============================================================================


class TestBuildTestSigninResponse:
    """Tests for the _build_test_signin_response helper."""

    def test_encodes_claims_as_base64_in_fragment(self) -> None:
        """Should redirect with base64-encoded claims in the URL fragment."""
        import base64
        import json

        claims = {"sub": "user-123", "email": "test@example.com", "groups": ["admin"]}

        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://localhost:3000"]

        with patch("syntara.auth.router.get_settings", return_value=mock_settings):
            response = _build_test_signin_response(claims, "http://localhost:3000")

        assert response.status_code == 302
        location = response.headers["location"]
        assert "/auth/test-signin-callback#" in location

        # Extract and decode the fragment
        fragment = location.split("#", 1)[1]
        decoded = json.loads(base64.urlsafe_b64decode(fragment))
        assert decoded["sub"] == "user-123"
        assert decoded["email"] == "test@example.com"
        assert decoded["groups"] == ["admin"]

    def test_uses_origin_for_redirect_url(self) -> None:
        """Should use the provided origin as the base URL."""
        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://app.example.com"]

        with patch("syntara.auth.router.get_settings", return_value=mock_settings):
            response = _build_test_signin_response({"sub": "x"}, "http://app.example.com")

        assert response.headers["location"].startswith("http://app.example.com/auth/test-signin-callback#")

    def test_handles_non_serializable_values(self) -> None:
        """Should handle non-JSON-serializable values via default=str."""
        claims = {"sub": "user-123", "id": uuid4()}

        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://localhost:3000"]

        with patch("syntara.auth.router.get_settings", return_value=mock_settings):
            response = _build_test_signin_response(claims, "http://localhost:3000")

        assert response.status_code == 302


class TestBuildCallbackErrorRedirect:
    """Tests for the _build_callback_error_redirect helper."""

    def test_auth_error_redirect(self) -> None:
        """Should redirect with auth_error error code for non-link errors."""
        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://localhost:3000"]

        error = OIDCCallbackError(
            "Something went wrong", error_code=OIDCErrorCode.AUTH_FAILED, origin="http://localhost:3000"
        )

        with patch("syntara.auth.router.get_settings", return_value=mock_settings):
            response = _build_callback_error_redirect(error)

        assert response.status_code == 302
        assert "auth_error=auth_failed" in response.headers["location"]

    def test_link_error_redirect(self) -> None:
        """Should redirect with link_error error code for link flow errors."""
        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://localhost:3000"]

        error = OIDCCallbackError(
            "Identity already linked",
            error_code=OIDCErrorCode.LINK_FAILED,
            origin="http://localhost:3000",
            redirect_to="http://localhost:3000/settings",
        )

        with patch("syntara.auth.router.get_settings", return_value=mock_settings):
            response = _build_callback_error_redirect(error)

        assert response.status_code == 302
        location = response.headers["location"]
        assert "link_error=link_failed" in location
        assert location.startswith("http://localhost:3000/settings")


class TestBuildLinkRedirect:
    """Tests for the _build_link_redirect helper."""

    @pytest.mark.asyncio
    async def test_redirects_to_stored_redirect_to(self) -> None:
        """Should redirect to the stored redirect_to URL when no conversion (identity=None)."""
        user = _make_user()
        provider = _make_provider(name="TestIdP")
        state_data = {
            "origin": "http://localhost:3000",
            "redirect_to": "http://localhost:3000/settings/identity",
        }

        mock_settings = MagicMock()
        mock_settings.cors_allow_origins = ["http://localhost:3000"]

        with patch("syntara.auth.router.get_settings", return_value=mock_settings):
            response = await _build_link_redirect(user, provider, None, state_data, MagicMock(), AsyncMock(), "")

        assert response.status_code == 302
        assert response.headers["location"] == "http://localhost:3000/settings/identity"

    @pytest.mark.asyncio
    async def test_handles_none_user(self) -> None:
        """Should not crash when user is None."""
        provider = _make_provider(name="TestIdP")
        state_data = {"origin": "http://localhost:3000"}

        mock_settings = MagicMock()
        mock_settings.cors_allow_origins = ["http://localhost:3000"]

        with patch("syntara.auth.router.get_settings", return_value=mock_settings):
            response = await _build_link_redirect(None, provider, None, state_data, MagicMock(), AsyncMock(), "")

        assert response.status_code == 302


class TestOIDCCallbackTestSigninFlow:
    """Tests for test-signin flow through the oidc_callback endpoint."""

    @pytest.mark.asyncio
    async def test_test_signin_returns_claims_redirect(self) -> None:
        """Should redirect with claims in fragment for test_signin flow."""
        provider = _make_provider(name="TestIdP")
        request = _make_request()
        raw_claims = {"sub": "user-123", "email": "test@example.com"}

        state_data = {
            "provider_id": str(provider.id),
            "nonce": "test-nonce",
            "code_verifier": "test-verifier",
            "flow_type": "test_signin",
            "origin": "http://localhost:3000",
        }

        mock_oidc_service = _make_oidc_service_mock(state_data=state_data, user_claims=_make_user_claims())

        db = AsyncMock()
        provider_result = MagicMock()
        provider_result.one_or_none.return_value = provider
        db.exec.return_value = provider_result

        mock_settings = MagicMock()
        mock_settings.jwt_issuer = "http://localhost:3000"
        mock_settings.cors_allow_origins = ["http://localhost:3000"]

        with (
            patch("syntara.auth.router.OIDCService", return_value=mock_oidc_service),
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch(
                "syntara.auth.router._exchange_and_validate_tokens",
                AsyncMock(return_value=(_make_user_claims(), raw_claims, "fake-id-token")),
            ),
        ):
            response = await oidc_callback(
                state="valid-state",
                request=request,
                db=db,
                code="auth-code-123",
            )

        assert response.status_code == 302
        assert "/auth/test-signin-callback#" in response.headers["location"]
