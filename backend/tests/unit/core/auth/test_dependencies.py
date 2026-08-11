"""Unit tests for auth dependencies (get_current_user, get_token_payload, get_refresh_token)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from syntara.auth.cookies import CSRF_COOKIE_NAME
from syntara.auth.dependencies import (
    _user_from_payload,
    get_current_user,
    get_refresh_token,
    get_token_payload,
)
from syntara.auth.exceptions import AuthenticationRequiredError, CSRFErrorCode, CSRFValidationError, InvalidTokenError
from syntara.auth.services.token_service import TokenPayload
from syntara.core.models.principal import service_principal_id


def _make_payload(
    *,
    sub: str | None = None,
    preferred_username: str = "testuser",
    email: str = "test@example.com",
) -> TokenPayload:
    return TokenPayload(
        sub=sub or str(uuid4()),
        iss="http://localhost:8000",
        iat=datetime.now(UTC),
        exp=datetime.now(UTC) + timedelta(minutes=15),
        token_type="access",  # noqa: S106
        preferred_username=preferred_username,
        email=email,
        groups=["eng"],
        amr=["pwd"],
        idp="local",
    )


class TestUserFromPayload:
    """Tests for _user_from_payload helper."""

    def test_constructs_user_from_valid_payload(self) -> None:
        """Should build a User with correct fields from token claims."""
        user_id = uuid4()
        payload = _make_payload(sub=str(user_id), preferred_username="alice", email="alice@x.com")

        user = _user_from_payload(payload)

        assert user.id == user_id
        assert user.username == "alice"
        assert user.email == "alice@x.com"
        assert user.is_enabled is True

    def test_raises_invalid_token_for_non_uuid_sub(self) -> None:
        """Should raise InvalidTokenError when sub is not a valid UUID."""
        payload = _make_payload(sub="not-a-uuid")

        with pytest.raises(InvalidTokenError):
            _user_from_payload(payload)

    def test_uses_given_name_and_family_name_when_present(self) -> None:
        """Should use given_name / family_name claims directly."""
        payload = _make_payload()
        payload.given_name = "Alice"
        payload.family_name = "Smith"

        user = _user_from_payload(payload)

        assert user.first_name == "Alice"
        assert user.last_name == "Smith"

    def test_uses_given_name_without_family_name(self) -> None:
        """Should set last_name to None when family_name claim is absent."""
        payload = _make_payload()
        payload.given_name = "Alice"
        payload.family_name = None

        user = _user_from_payload(payload)

        assert user.first_name == "Alice"
        assert user.last_name is None

    def test_strips_control_chars_from_names(self) -> None:
        """Should strip control characters from given_name and family_name."""
        payload = _make_payload()
        payload.given_name = "Al\x00ice"
        payload.family_name = "Smi\x0dth"

        user = _user_from_payload(payload)

        assert user.first_name == "Alice"
        assert user.last_name == "Smith"

    def test_uses_full_name_as_first_name_when_given_name_absent(self) -> None:
        """Should store the entire name as first_name without splitting."""
        payload = _make_payload()
        payload.given_name = None
        payload.name = "Jane Doe"

        user = _user_from_payload(payload)

        assert user.first_name == "Jane Doe"
        assert user.last_name is None

    def test_falls_back_when_optional_claims_are_none(self) -> None:
        """Missing preferred_username and email should fall back to sub-based values."""
        payload = _make_payload()
        payload.preferred_username = None
        payload.email = None
        payload.name = None

        user = _user_from_payload(payload)

        assert user.username == payload.sub
        assert user.email == f"{payload.sub}@unknown"
        assert user.first_name == payload.sub


class TestGetCurrentUser:
    """Tests for get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_raises_when_no_credentials(self) -> None:
        """Should raise AuthenticationRequiredError when credentials are None."""
        request = MagicMock()
        request.headers = {}
        request.state.is_cert_authenticated = False

        with pytest.raises(AuthenticationRequiredError):
            await get_current_user(request, db=AsyncMock(), credentials=None)

    @pytest.mark.asyncio
    async def test_cert_auth_with_on_behalf_of(self) -> None:
        """Cert-authenticated request with X-On-Behalf-Of returns that user's identity."""
        user_id = uuid4()
        request = MagicMock()
        request.state.is_cert_authenticated = True
        request.state.cert_cn = "worker.ao.svc"
        request.headers = {"x-on-behalf-of": str(user_id)}

        user = await get_current_user(request, db=AsyncMock(), credentials=None)

        assert user.id == user_id
        assert user.username == "worker.ao.svc"

    @pytest.mark.asyncio
    async def test_cert_auth_without_on_behalf_of(self) -> None:
        """Cert-authenticated request without X-On-Behalf-Of falls back to service principal."""
        request = MagicMock()
        request.state.is_cert_authenticated = True
        request.state.cert_cn = "backend.ao.svc"
        request.headers = {}

        user = await get_current_user(request, db=AsyncMock(), credentials=None)

        assert user.id == service_principal_id("backend.ao.svc")
        assert user.username == "backend.ao.svc"

    @pytest.mark.asyncio
    async def test_returns_user_for_valid_token(self) -> None:
        """Should return a User for a valid access token."""
        user_id = uuid4()
        payload = _make_payload(sub=str(user_id), preferred_username="bob")

        mock_token_service = MagicMock()
        mock_token_service.decode_token.return_value = payload

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-jwt")
        request = MagicMock()
        request.headers = {}

        with (
            patch("syntara.auth.dependencies._get_token_service", return_value=mock_token_service),
            patch("syntara.auth.services.global_revocation.is_token_globally_revoked", return_value=None),
        ):
            user = await get_current_user(request, db=AsyncMock(), credentials=credentials)

        assert user.id == user_id
        assert user.username == "bob"
        mock_token_service.decode_token.assert_called_once_with("valid-jwt", token_type="access")  # noqa: S106

    @pytest.mark.asyncio
    async def test_propagates_invalid_token_error(self) -> None:
        """Should propagate InvalidTokenError from token service."""
        mock_token_service = MagicMock()
        mock_token_service.decode_token.side_effect = InvalidTokenError

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad-jwt")
        request = MagicMock()
        request.headers = {}

        with (
            patch("syntara.auth.dependencies._get_token_service", return_value=mock_token_service),
            pytest.raises(InvalidTokenError),
        ):
            await get_current_user(request, db=AsyncMock(), credentials=credentials)


class TestGetTokenPayload:
    """Tests for get_token_payload dependency."""

    @pytest.mark.asyncio
    async def test_raises_when_no_credentials(self) -> None:
        """Should raise AuthenticationRequiredError when credentials are None."""
        request = MagicMock()

        with pytest.raises(AuthenticationRequiredError):
            await get_token_payload(request, db=AsyncMock(), credentials=None)

    @pytest.mark.asyncio
    async def test_returns_payload_for_valid_token(self) -> None:
        """Should return TokenPayload for a valid access token."""
        payload = _make_payload()

        mock_token_service = MagicMock()
        mock_token_service.decode_token.return_value = payload

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-jwt")
        request = MagicMock()

        with (
            patch("syntara.auth.dependencies._get_token_service", return_value=mock_token_service),
            patch("syntara.auth.dependencies._check_global_revocation", new_callable=AsyncMock),
        ):
            result = await get_token_payload(request, db=AsyncMock(), credentials=credentials)

        assert result is payload


# =============================================================================
# get_refresh_token (CSRF validation)
# =============================================================================


def _mock_csrf_encryption_key() -> MagicMock:
    """Return mock SecretStr for CSRF encryption key."""
    key = MagicMock()
    key.get_secret_value.return_value = "test-csrf-server-secret"
    return key


class TestGetRefreshTokenCSRF:
    """Tests for CSRF validation in the get_refresh_token dependency."""

    @pytest.mark.asyncio
    async def test_raises_csrf_error_when_csrf_cookie_missing(self) -> None:
        """Should raise CSRFValidationError when CSRF cookie is absent."""
        request = MagicMock()
        request.cookies = {"ao_refresh_token": "some-jwt"}
        request.headers = MagicMock()
        request.headers.get = MagicMock(return_value=None)

        with pytest.raises(CSRFValidationError, match="CSRF cookie missing") as exc_info:
            await get_refresh_token(request, db=AsyncMock())
        assert exc_info.value.error_code == CSRFErrorCode.COOKIE_MISSING

    @pytest.mark.asyncio
    async def test_raises_csrf_error_when_csrf_header_missing(self) -> None:
        """Should raise CSRFValidationError when X-CSRF-Token header is absent."""
        request = MagicMock()
        request.cookies = {
            "ao_refresh_token": "some-jwt",
            CSRF_COOKIE_NAME: "some-seed",
        }
        request.headers = MagicMock()
        request.headers.get = MagicMock(return_value=None)

        with (
            patch("syntara.auth.csrf.get_encryption_key", return_value=_mock_csrf_encryption_key()),
            pytest.raises(CSRFValidationError, match="CSRF token header missing") as exc_info,
        ):
            await get_refresh_token(request, db=AsyncMock())
        assert exc_info.value.error_code == CSRFErrorCode.HEADER_MISSING

    @pytest.mark.asyncio
    async def test_raises_csrf_error_on_token_mismatch(self) -> None:
        """Should raise CSRFValidationError when header token doesn't match derived token."""
        request = MagicMock()
        request.cookies = {
            "ao_refresh_token": "some-jwt",
            CSRF_COOKIE_NAME: "the-seed",
        }
        request.headers = MagicMock()
        request.headers.get = MagicMock(return_value="wrong-token")

        with (
            patch("syntara.auth.csrf.get_encryption_key", return_value=_mock_csrf_encryption_key()),
            pytest.raises(CSRFValidationError, match="CSRF token mismatch") as exc_info,
        ):
            await get_refresh_token(request, db=AsyncMock())
        assert exc_info.value.error_code == CSRFErrorCode.TOKEN_MISMATCH

    @pytest.mark.asyncio
    async def test_passes_csrf_and_returns_payload(self) -> None:
        """Should pass CSRF validation and return the decoded payload."""
        from syntara.auth.csrf import derive_csrf_form_token

        seed = "good-seed"
        settings = _mock_csrf_encryption_key()
        with patch("syntara.auth.csrf.get_encryption_key", return_value=settings):
            valid_token = derive_csrf_form_token(seed)

        payload = MagicMock()
        mock_token_service = MagicMock()
        mock_token_service.decode_token.return_value = payload

        request = MagicMock()
        request.cookies = {
            "ao_refresh_token": "the-refresh-jwt",
            CSRF_COOKIE_NAME: seed,
        }
        request.headers = MagicMock()
        request.headers.get = MagicMock(return_value=valid_token)

        with (
            patch("syntara.auth.csrf.get_encryption_key", return_value=settings),
            patch("syntara.auth.dependencies._get_token_service", return_value=mock_token_service),
            patch("syntara.auth.services.global_revocation.is_token_globally_revoked", return_value=None),
        ):
            result = await get_refresh_token(request, db=AsyncMock())

        assert result is payload

    @pytest.mark.asyncio
    async def test_raises_auth_error_when_refresh_cookie_missing_after_csrf_passes(self) -> None:
        """Should raise AuthenticationRequiredError when CSRF passes but refresh cookie is absent."""
        request = MagicMock()
        request.cookies = {CSRF_COOKIE_NAME: "seed"}
        request.headers = MagicMock()
        request.headers.get = MagicMock(return_value="token")

        with (
            patch("syntara.auth.csrf.validate_csrf"),
            pytest.raises(AuthenticationRequiredError),
        ):
            await get_refresh_token(request, db=AsyncMock())
