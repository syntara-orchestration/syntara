# ruff: noqa: S105, S106
"""Unit tests for OIDC service.

Tests cover:
- Discovery configuration fetching
- PKCE generation
- Nonce generation
- Signed JWT state encoding and decoding
- Token exchange
- ID token validation
- User claims extraction
- Authorization URL building
"""

import hashlib
import socket
import time
from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import jwt as pyjwt
import pytest
from starlette import status

from syntara.auth.services.oidc_service import (
    OIDCError,
    OIDCService,
    _create_insecure_ssl_context,
    _get_jwks_client,
    _is_ssl_verification_error,
)
from syntara.identity_providers.models.identity_provider_configuration import OIDCClaimMapping

_real_getaddrinfo = socket.getaddrinfo

_PUBLIC_IP = "93.184.216.34"
_STUBBED_HOSTS = {"example.com", "evil-idp.com", "other-issuer.com"}


def _fake_getaddrinfo(
    host: str,
    port: int | str | None,
    family: int = 0,
    type: int = 0,  # noqa: A002
    proto: int = 0,
    flags: int = 0,
) -> list[tuple[socket.AddressFamily, socket.SocketKind, int, str, tuple[str, int]]]:
    """Return a public IP for test hostnames so validate_safe_url skips real DNS."""
    if host in _STUBBED_HOSTS:
        resolved_port = int(port) if port else 443
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (_PUBLIC_IP, resolved_port))]
    return _real_getaddrinfo(host, port, family, type, proto, flags)  # type: ignore[return-value]


@pytest.fixture(autouse=True)
def _stub_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent validate_safe_url from doing real DNS lookups in unit tests."""
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)


@pytest.fixture
def oidc_service() -> OIDCService:
    """Create an OIDCService instance."""
    return OIDCService()


class TestCreateInsecureSslContext:
    """Tests for _create_insecure_ssl_context helper."""

    def test_returns_ssl_context(self) -> None:
        """Test that an SSLContext is returned."""
        import ssl

        ctx = _create_insecure_ssl_context()
        assert isinstance(ctx, ssl.SSLContext)

    def test_verify_mode_is_cert_optional(self) -> None:
        """Test that verify_mode skips CA trust-chain validation."""
        import ssl

        ctx = _create_insecure_ssl_context()
        assert ctx.verify_mode == ssl.CERT_NONE

    def test_minimum_tls_version_is_1_3(self) -> None:
        """Test that minimum TLS version is set to 1.3."""
        import ssl

        ctx = _create_insecure_ssl_context()
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3


class TestIsSslVerificationError:
    """Tests for _is_ssl_verification_error helper."""

    def test_detects_ssl_cert_verify_failed(self) -> None:
        err = Exception("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        assert _is_ssl_verification_error(err) is True

    def test_rejects_generic_connection_error(self) -> None:
        err = Exception("Connection refused")
        assert _is_ssl_verification_error(err) is False

    def test_detects_wrapped_ssl_error(self) -> None:
        err = httpx.ConnectError(
            "[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate",
            request=MagicMock(),
        )
        assert _is_ssl_verification_error(err) is True


class TestGetJwksClient:
    """Tests for _get_jwks_client with disable_tls_verify."""

    def test_default_has_no_custom_ssl_context(self) -> None:
        """Test that the default client does not use a custom SSL context."""
        _get_jwks_client.cache_clear()
        with patch("syntara.auth.services.oidc_service.PyJWKClient") as mock_cls:
            _get_jwks_client("https://example.com/jwks")
            call_kwargs = mock_cls.call_args
            assert "ssl_context" not in call_kwargs.kwargs

    def test_disable_tls_verify_passes_ssl_context(self) -> None:
        """Test that disable_tls_verify passes an insecure SSL context."""
        import ssl

        _get_jwks_client.cache_clear()
        with patch("syntara.auth.services.oidc_service.PyJWKClient") as mock_cls:
            _get_jwks_client("https://example.com/jwks", disable_tls_verify=True)
            call_kwargs = mock_cls.call_args
            ctx = call_kwargs.kwargs["ssl_context"]
            assert isinstance(ctx, ssl.SSLContext)
            assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3
            assert ctx.verify_mode == ssl.CERT_NONE


class TestFetchDiscoveryConfig:
    """Tests for fetch_discovery_config method."""

    @pytest.mark.asyncio
    async def test_successful_discovery(self, oidc_service: OIDCService) -> None:
        """Test successful discovery configuration fetch."""
        mock_response = MagicMock()
        mock_response.status_code = status.HTTP_200_OK
        mock_response.json.return_value = {
            "issuer": "https://example.com",
            "authorization_endpoint": "https://example.com/authorize",
            "token_endpoint": "https://example.com/token",
            "jwks_uri": "https://example.com/jwks",
            "userinfo_endpoint": "https://example.com/userinfo",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient", return_value=mock_client):
            config = await oidc_service.fetch_discovery_config("https://example.com")

        assert config["issuer"] == "https://example.com"
        assert config["authorization_endpoint"] == "https://example.com/authorize"
        assert config["token_endpoint"] == "https://example.com/token"
        assert config["jwks_uri"] == "https://example.com/jwks"

        mock_client.get.assert_called_once_with("https://example.com/.well-known/openid-configuration")

    @pytest.mark.asyncio
    async def test_discovery_timeout(self, oidc_service: OIDCService) -> None:
        """Test discovery request timeout."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(OIDCError, match="Discovery request timed out"):
                await oidc_service.fetch_discovery_config("https://example.com")

    @pytest.mark.asyncio
    async def test_discovery_non_200_status(self, oidc_service: OIDCService) -> None:
        """Test discovery with non-200 status code."""
        mock_response = MagicMock()
        mock_response.status_code = status.HTTP_404_NOT_FOUND

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(OIDCError, match="Discovery endpoint returned HTTP 404"):
                await oidc_service.fetch_discovery_config("https://example.com")

    @pytest.mark.asyncio
    async def test_discovery_missing_required_fields(self, oidc_service: OIDCService) -> None:
        """Test discovery with missing required fields."""
        mock_response = MagicMock()
        mock_response.status_code = status.HTTP_200_OK
        mock_response.json.return_value = {
            "issuer": "https://example.com",
            "authorization_endpoint": "https://example.com/authorize",
            # Missing token_endpoint and jwks_uri
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(OIDCError, match="Discovery response missing"):
                await oidc_service.fetch_discovery_config("https://example.com")

    @pytest.mark.asyncio
    async def test_discovery_request_error(self, oidc_service: OIDCService) -> None:
        """Test discovery with request error."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection failed", request=MagicMock()))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(OIDCError, match="Discovery request failed"):
                await oidc_service.fetch_discovery_config("https://example.com")

    @pytest.mark.asyncio
    async def test_discovery_follows_redirects(self, oidc_service: OIDCService) -> None:
        """Test that discovery request follows redirects."""
        mock_response = MagicMock()
        mock_response.status_code = status.HTTP_200_OK
        mock_response.json.return_value = {
            "issuer": "https://example.com",
            "authorization_endpoint": "https://example.com/authorize",
            "token_endpoint": "https://example.com/token",
            "jwks_uri": "https://example.com/jwks",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value = mock_client
            await oidc_service.fetch_discovery_config("https://example.com")

            # Verify AsyncClient was created with follow_redirects=True and verify=True
            mock_async_client.assert_called_once_with(timeout=10.0, follow_redirects=True, verify=True)

    @pytest.mark.asyncio
    async def test_discovery_disable_tls_verify(self, oidc_service: OIDCService) -> None:
        """Test that discovery passes verify=False when disable_tls_verify is True."""
        mock_response = MagicMock()
        mock_response.status_code = status.HTTP_200_OK
        mock_response.json.return_value = {
            "issuer": "https://example.com",
            "authorization_endpoint": "https://example.com/authorize",
            "token_endpoint": "https://example.com/token",
            "jwks_uri": "https://example.com/jwks",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value = mock_client
            await oidc_service.fetch_discovery_config("https://example.com", disable_tls_verify=True)

            mock_async_client.assert_called_once_with(timeout=10.0, follow_redirects=True, verify=False)

    @pytest.mark.asyncio
    async def test_discovery_ssl_verification_error(self, oidc_service: OIDCService) -> None:
        """SSL cert verification failure produces actionable error message."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.ConnectError(
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate",
                request=MagicMock(),
            )
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(OIDCError, match="TLS certificate verification failed"):
                await oidc_service.fetch_discovery_config("https://example.com")

    @pytest.mark.asyncio
    async def test_discovery_non_ssl_connect_error_uses_generic_message(self, oidc_service: OIDCService) -> None:
        """Non-SSL ConnectError falls through to generic message."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused", request=MagicMock()))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(OIDCError, match="Discovery request failed"):
                await oidc_service.fetch_discovery_config("https://example.com")


class TestGeneratePKCE:
    """Tests for generate_pkce method."""

    def test_generates_verifier_and_challenge(self, oidc_service: OIDCService) -> None:
        """Test that PKCE generates both verifier and challenge."""
        code_verifier, code_challenge = oidc_service.generate_pkce()

        assert isinstance(code_verifier, str)
        assert isinstance(code_challenge, str)
        assert len(code_verifier) > 0
        assert len(code_challenge) > 0

    def test_challenge_is_sha256_of_verifier(self, oidc_service: OIDCService) -> None:
        """Test that code challenge is S256 of verifier."""
        code_verifier, code_challenge = oidc_service.generate_pkce()

        # Manually compute expected challenge
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        expected_challenge = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

        assert code_challenge == expected_challenge

    def test_generates_unique_values(self, oidc_service: OIDCService) -> None:
        """Test that multiple calls generate unique values."""
        verifier1, challenge1 = oidc_service.generate_pkce()
        verifier2, challenge2 = oidc_service.generate_pkce()

        assert verifier1 != verifier2
        assert challenge1 != challenge2


class TestGenerateNonce:
    """Tests for generate_nonce method."""

    def test_generates_nonce(self, oidc_service: OIDCService) -> None:
        """Test that a nonce is generated."""
        nonce = oidc_service.generate_nonce()

        assert isinstance(nonce, str)
        assert len(nonce) > 0

    def test_generates_unique_values(self, oidc_service: OIDCService) -> None:
        """Test that multiple calls generate unique values."""
        nonce1 = oidc_service.generate_nonce()
        nonce2 = oidc_service.generate_nonce()

        assert nonce1 != nonce2


class TestStoreOidcState:
    """Tests for store_oidc_state method (AES-256-GCM encryption)."""

    def test_returns_encrypted_token(self, oidc_service: OIDCService) -> None:
        """Test that state is returned as an encrypted token string."""
        with patch("syntara.auth.services.oidc_service.get_encryption_key") as mock_key:
            mock_key.return_value.get_secret_value.return_value = "a" * 64
            state = oidc_service.store_oidc_state(
                provider_id=uuid4(),
                nonce="test-nonce-456",
                code_verifier="test-verifier-789",
            )

        assert isinstance(state, str)
        assert len(state) > 0

    def test_payload_is_not_readable(self, oidc_service: OIDCService) -> None:
        """Test that the code_verifier is not visible in the state token."""
        with patch("syntara.auth.services.oidc_service.get_encryption_key") as mock_key:
            mock_key.return_value.get_secret_value.return_value = "a" * 64
            state = oidc_service.store_oidc_state(
                provider_id=uuid4(),
                nonce="test-nonce",
                code_verifier="super-secret-verifier",
            )

        assert "super-secret-verifier" not in state

    def test_includes_all_fields(self, oidc_service: OIDCService) -> None:
        """Test that all state fields survive encrypt/decrypt roundtrip."""
        provider_id = uuid4()

        with patch("syntara.auth.services.oidc_service.get_encryption_key") as mock_key:
            mock_key.return_value.get_secret_value.return_value = "a" * 64
            state = oidc_service.store_oidc_state(
                provider_id=provider_id,
                nonce="test-nonce",
                code_verifier="test-verifier",
                redirect_to="https://example.com/dashboard",
                origin="https://example.com",
                flow_type="link",
                user_id="user-123",
                session_jti="jti-456",
            )

            result = oidc_service.retrieve_oidc_state(state)

        assert result is not None
        assert result["provider_id"] == str(provider_id)
        assert result["nonce"] == "test-nonce"
        assert result["code_verifier"] == "test-verifier"
        assert result["redirect_to"] == "https://example.com/dashboard"
        assert result["origin"] == "https://example.com"
        assert result["flow_type"] == "link"
        assert result["user_id"] == "user-123"
        assert result["session_jti"] == "jti-456"


class TestRetrieveOidcState:
    """Tests for retrieve_oidc_state method (AES-256-GCM decryption)."""

    def test_decrypts_valid_state(self, oidc_service: OIDCService) -> None:
        """Test that a valid encrypted state is decrypted."""
        provider_id = uuid4()

        with patch("syntara.auth.services.oidc_service.get_encryption_key") as mock_key:
            mock_key.return_value.get_secret_value.return_value = "a" * 64
            state = oidc_service.store_oidc_state(
                provider_id=provider_id,
                nonce="test-nonce",
                code_verifier="test-verifier",
            )
            result = oidc_service.retrieve_oidc_state(state)

        assert result is not None
        assert result["provider_id"] == str(provider_id)
        assert result["nonce"] == "test-nonce"
        assert result["code_verifier"] == "test-verifier"

    def test_returns_none_for_tampered_state(self, oidc_service: OIDCService) -> None:
        """Test that a tampered token returns None."""
        with patch("syntara.auth.services.oidc_service.get_encryption_key") as mock_key:
            mock_key.return_value.get_secret_value.return_value = "a" * 64
            result = oidc_service.retrieve_oidc_state("tampered-garbage-token")

        assert result is None

    def test_returns_none_for_wrong_key(self, oidc_service: OIDCService) -> None:
        """Test that decryption with a different key fails."""
        with patch("syntara.auth.services.oidc_service.get_encryption_key") as mock_key:
            mock_key.return_value.get_secret_value.return_value = "a" * 64
            state = oidc_service.store_oidc_state(
                provider_id=uuid4(),
                nonce="test-nonce",
                code_verifier="test-verifier",
            )

        with patch("syntara.auth.services.oidc_service.get_encryption_key") as mock_key:
            mock_key.return_value.get_secret_value.return_value = "b" * 64
            result = oidc_service.retrieve_oidc_state(state)

        assert result is None

    def test_returns_none_for_expired_state(self, oidc_service: OIDCService) -> None:
        """Test that state with an expired timestamp returns None."""
        with patch("syntara.auth.services.oidc_service.get_encryption_key") as mock_key:
            mock_key.return_value.get_secret_value.return_value = "a" * 64

            # Encrypt state with exp in the past
            with patch("syntara.auth.services.oidc_service.time.time", return_value=time.time() - 700):
                state = oidc_service.store_oidc_state(
                    provider_id=uuid4(),
                    nonce="test-nonce",
                    code_verifier="test-verifier",
                )

            result = oidc_service.retrieve_oidc_state(state)

        assert result is None

    def test_exp_is_stripped_from_result(self, oidc_service: OIDCService) -> None:
        """Test that the exp claim is not returned to the caller."""
        with patch("syntara.auth.services.oidc_service.get_encryption_key") as mock_key:
            mock_key.return_value.get_secret_value.return_value = "a" * 64
            state = oidc_service.store_oidc_state(
                provider_id=uuid4(),
                nonce="test-nonce",
                code_verifier="test-verifier",
            )
            result = oidc_service.retrieve_oidc_state(state)

        assert result is not None
        assert "exp" not in result


class TestExchangeCodeForTokens:
    """Tests for exchange_code_for_tokens method."""

    @pytest.mark.asyncio
    async def test_successful_exchange_200(self, oidc_service: OIDCService) -> None:
        """Test successful token exchange with 200 status."""
        mock_response = MagicMock()
        mock_response.status_code = status.HTTP_200_OK
        mock_response.json.return_value = {
            "access_token": "access-token-123",
            "id_token": "id-token-456",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient", return_value=mock_client):
            tokens = await oidc_service.exchange_code_for_tokens(
                token_endpoint="https://example.com/token",
                code="auth-code-123",
                redirect_uri="https://app.example.com/callback",
                client_id="client-123",
                client_secret="secret-456",
                code_verifier="verifier-789",
            )

        assert tokens["access_token"] == "access-token-123"
        assert tokens["id_token"] == "id-token-456"
        assert tokens["token_type"] == "Bearer"

        # Verify the request was made correctly
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://example.com/token"
        assert call_args[1]["data"]["grant_type"] == "authorization_code"
        assert call_args[1]["data"]["code"] == "auth-code-123"
        assert call_args[1]["data"]["code_verifier"] == "verifier-789"

    @pytest.mark.asyncio
    async def test_successful_exchange_201(self, oidc_service: OIDCService) -> None:
        """Test successful token exchange with 201 status."""
        mock_response = MagicMock()
        mock_response.status_code = status.HTTP_201_CREATED
        mock_response.json.return_value = {
            "access_token": "access-token-123",
            "id_token": "id-token-456",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient", return_value=mock_client):
            tokens = await oidc_service.exchange_code_for_tokens(
                token_endpoint="https://example.com/token",
                code="auth-code-123",
                redirect_uri="https://app.example.com/callback",
                client_id="client-123",
                client_secret="secret-456",
                code_verifier="verifier-789",
            )

        assert tokens["access_token"] == "access-token-123"
        assert tokens["id_token"] == "id-token-456"

    @pytest.mark.asyncio
    async def test_exchange_failure(self, oidc_service: OIDCService) -> None:
        """Test token exchange failure with error status."""
        mock_response = MagicMock()
        mock_response.status_code = status.HTTP_400_BAD_REQUEST
        mock_response.text = "invalid_grant"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(OIDCError, match="Token exchange failed with HTTP 400"):
                await oidc_service.exchange_code_for_tokens(
                    token_endpoint="https://example.com/token",
                    code="invalid-code",
                    redirect_uri="https://app.example.com/callback",
                    client_id="client-123",
                    client_secret="secret-456",
                    code_verifier="verifier-789",
                )

    @pytest.mark.asyncio
    async def test_exchange_timeout(self, oidc_service: OIDCService) -> None:
        """Test token exchange timeout."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(OIDCError, match="Token exchange request timed out"):
                await oidc_service.exchange_code_for_tokens(
                    token_endpoint="https://example.com/token",
                    code="auth-code-123",
                    redirect_uri="https://app.example.com/callback",
                    client_id="client-123",
                    client_secret="secret-456",
                    code_verifier="verifier-789",
                )

    @pytest.mark.asyncio
    async def test_rejects_http_token_endpoint(self, oidc_service: OIDCService) -> None:
        """Test that token exchange rejects HTTP endpoints (SSRF, AAP-71276)."""
        with patch("syntara.auth.services.oidc_service.get_settings") as mock_gs:
            mock_gs.return_value.oidc_allow_private_networks = False
            with pytest.raises(OIDCError, match="OIDC issuer URL must use HTTPS"):
                await oidc_service.exchange_code_for_tokens(
                    token_endpoint="http://example.com/token",
                    code="auth-code-123",
                    redirect_uri="https://app.example.com/callback",
                    client_id="client-123",
                    client_secret="secret-456",
                    code_verifier="verifier-789",
                )

    @pytest.mark.asyncio
    async def test_rejects_private_ip_token_endpoint(self, oidc_service: OIDCService) -> None:
        """Test that token exchange rejects endpoints resolving to private IPs (SSRF, AAP-71276)."""
        with (
            patch("syntara.auth.services.oidc_service.get_settings") as mock_gs,
            patch("socket.getaddrinfo") as mock_getaddrinfo,
        ):
            mock_gs.return_value.oidc_allow_private_networks = False
            mock_getaddrinfo.return_value = [(None, None, None, None, ("127.0.0.1", 443))]
            with pytest.raises(OIDCError, match="SSRF blocked"):
                await oidc_service.exchange_code_for_tokens(
                    token_endpoint="https://evil-idp.com/token",
                    code="auth-code-123",
                    redirect_uri="https://app.example.com/callback",
                    client_id="client-123",
                    client_secret="secret-456",
                    code_verifier="verifier-789",
                )

    async def test_allow_private_still_blocks_cloud_metadata(self, oidc_service: OIDCService) -> None:
        """Cloud metadata endpoints are blocked even when oidc_allow_private_networks=True."""
        with patch("syntara.auth.services.oidc_service.get_settings") as mock_gs:
            mock_gs.return_value.oidc_allow_private_networks = True
            with pytest.raises(OIDCError, match="SSRF blocked"):
                oidc_service._validate_url("http://169.254.169.254/latest/meta-data/")

    @pytest.mark.asyncio
    async def test_exchange_disable_tls_verify(self, oidc_service: OIDCService) -> None:
        """Test that token exchange passes verify=False when disable_tls_verify is True."""
        mock_response = MagicMock()
        mock_response.status_code = status.HTTP_200_OK
        mock_response.json.return_value = {
            "access_token": "access-token-123",
            "id_token": "id-token-456",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value = mock_client
            await oidc_service.exchange_code_for_tokens(
                token_endpoint="https://example.com/token",
                code="auth-code-123",
                redirect_uri="https://app.example.com/callback",
                client_id="client-123",
                client_secret="secret-456",
                code_verifier="verifier-789",
                disable_tls_verify=True,
            )

            mock_async_client.assert_called_once_with(timeout=10.0, follow_redirects=True, verify=False)

    @pytest.mark.asyncio
    async def test_rejects_non_http_scheme_token_endpoint(self, oidc_service: OIDCService) -> None:
        """Test that token exchange rejects non-HTTP(S) schemes (SSRF, AAP-71276)."""
        with patch("syntara.auth.services.oidc_service.get_settings") as mock_gs:
            mock_gs.return_value.oidc_allow_private_networks = False
            with pytest.raises(OIDCError, match="OIDC issuer URL must use HTTPS"):
                await oidc_service.exchange_code_for_tokens(
                    token_endpoint="ftp://example.com/token",
                    code="auth-code-123",
                    redirect_uri="https://app.example.com/callback",
                    client_id="client-123",
                    client_secret="secret-456",
                    code_verifier="verifier-789",
                )

    @pytest.mark.asyncio
    async def test_exchange_ssl_verification_error(self, oidc_service: OIDCService) -> None:
        """SSL cert verification failure during token exchange produces actionable message."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError(
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
                request=MagicMock(),
            )
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(OIDCError, match="TLS certificate verification failed"):
                await oidc_service.exchange_code_for_tokens(
                    token_endpoint="https://example.com/token",
                    code="auth-code-123",
                    redirect_uri="https://app.example.com/callback",
                    client_id="client-123",
                    client_secret="secret-456",
                    code_verifier="verifier-789",
                )


class TestFetchUserinfo:
    """Tests for fetch_userinfo method (OIDC Core §5.3)."""

    @pytest.mark.asyncio
    async def test_successful_userinfo_fetch(self, oidc_service: OIDCService) -> None:
        """Test successful userinfo fetch returns claims."""
        mock_response = MagicMock()
        mock_response.status_code = status.HTTP_200_OK
        mock_response.json.return_value = {
            "sub": "user-123",
            "email": "user@example.com",
            "name": "Test User",
            "preferred_username": "testuser",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient", return_value=mock_client):
            claims = await oidc_service.fetch_userinfo(
                userinfo_endpoint="https://example.com/userinfo",
                access_token="access-token-123",
            )

        assert claims["email"] == "user@example.com"
        assert claims["name"] == "Test User"
        mock_client.get.assert_called_once_with(
            "https://example.com/userinfo",
            headers={"Authorization": "Bearer access-token-123"},
        )

    @pytest.mark.asyncio
    async def test_userinfo_non_200_status(self, oidc_service: OIDCService) -> None:
        """Test userinfo failure with non-200 status."""
        mock_response = MagicMock()
        mock_response.status_code = status.HTTP_401_UNAUTHORIZED

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(OIDCError, match="Userinfo endpoint returned HTTP 401"):
                await oidc_service.fetch_userinfo(
                    userinfo_endpoint="https://example.com/userinfo",
                    access_token="bad-token",
                )

    @pytest.mark.asyncio
    async def test_userinfo_timeout(self, oidc_service: OIDCService) -> None:
        """Test userinfo request timeout."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(OIDCError, match="Userinfo request timed out"):
                await oidc_service.fetch_userinfo(
                    userinfo_endpoint="https://example.com/userinfo",
                    access_token="access-token-123",
                )

    @pytest.mark.asyncio
    async def test_userinfo_invalid_json(self, oidc_service: OIDCService) -> None:
        """Test userinfo response with invalid JSON."""
        mock_response = MagicMock()
        mock_response.status_code = status.HTTP_200_OK
        mock_response.json.side_effect = ValueError("Invalid JSON")

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(OIDCError, match="Userinfo response is not valid JSON"):
                await oidc_service.fetch_userinfo(
                    userinfo_endpoint="https://example.com/userinfo",
                    access_token="access-token-123",
                )

    @pytest.mark.asyncio
    async def test_userinfo_disable_tls_verify(self, oidc_service: OIDCService) -> None:
        """Test that userinfo passes verify=False when disable_tls_verify is True."""
        mock_response = MagicMock()
        mock_response.status_code = status.HTTP_200_OK
        mock_response.json.return_value = {
            "sub": "user-123",
            "email": "user@example.com",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value = mock_client
            await oidc_service.fetch_userinfo(
                userinfo_endpoint="https://example.com/userinfo",
                access_token="access-token-123",
                disable_tls_verify=True,
            )

            mock_async_client.assert_called_once_with(timeout=10.0, follow_redirects=True, verify=False)

    @pytest.mark.asyncio
    async def test_userinfo_ssrf_validation(self, oidc_service: OIDCService) -> None:
        """Test that userinfo endpoint is validated against SSRF."""
        with patch("syntara.auth.services.oidc_service.get_settings") as mock_gs:
            mock_gs.return_value.oidc_allow_private_networks = False
            with pytest.raises(OIDCError, match="OIDC issuer URL must use HTTPS"):
                await oidc_service.fetch_userinfo(
                    userinfo_endpoint="http://example.com/userinfo",
                    access_token="access-token-123",
                )

    @pytest.mark.asyncio
    async def test_userinfo_ssl_verification_error(self, oidc_service: OIDCService) -> None:
        """SSL cert verification failure during userinfo fetch produces actionable message."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.ConnectError(
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
                request=MagicMock(),
            )
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("syntara.auth.services.oidc_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(OIDCError, match="TLS certificate verification failed"):
                await oidc_service.fetch_userinfo(
                    userinfo_endpoint="https://example.com/userinfo",
                    access_token="access-token-123",
                )


class TestValidateIdToken:
    """Tests for validate_id_token method."""

    def test_successful_validation(self, oidc_service: OIDCService) -> None:
        """Test successful ID token validation."""
        claims = {
            "sub": "user-123",
            "iss": "https://example.com",
            "aud": "client-123",
            "nonce": "nonce-456",
            "email": "user@example.com",
            "name": "Test User",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
        }

        mock_signing_key = MagicMock()
        mock_signing_key.key = "mock-key"

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt = MagicMock(return_value=mock_signing_key)

        with patch("syntara.auth.services.oidc_service._get_jwks_client", return_value=mock_jwks_client):
            with patch("syntara.auth.services.oidc_service.pyjwt.decode", return_value=claims):
                result = oidc_service.validate_id_token(
                    id_token="mock-id-token",
                    jwks_uri="https://example.com/jwks",
                    issuer="https://example.com",
                    client_id="client-123",
                    nonce="nonce-456",
                )

        assert result["sub"] == "user-123"
        assert result["email"] == "user@example.com"
        assert result["nonce"] == "nonce-456"

    def test_expired_token(self, oidc_service: OIDCService) -> None:
        """Test validation fails for expired token."""
        mock_signing_key = MagicMock()
        mock_signing_key.key = "mock-key"

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt = MagicMock(return_value=mock_signing_key)

        with (
            patch("syntara.auth.services.oidc_service._get_jwks_client", return_value=mock_jwks_client),
            patch(
                "syntara.auth.services.oidc_service.pyjwt.decode",
                side_effect=pyjwt.ExpiredSignatureError("Token expired"),
            ),
            pytest.raises(OIDCError, match="ID token has expired"),
        ):
            oidc_service.validate_id_token(
                id_token="expired-token",
                jwks_uri="https://example.com/jwks",
                issuer="https://example.com",
                client_id="client-123",
                nonce="nonce-456",
            )

    def test_issuer_mismatch(self, oidc_service: OIDCService) -> None:
        """Test validation fails for issuer mismatch."""
        mock_signing_key = MagicMock()
        mock_signing_key.key = "mock-key"

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt = MagicMock(return_value=mock_signing_key)

        with (
            patch("syntara.auth.services.oidc_service._get_jwks_client", return_value=mock_jwks_client),
            patch(
                "syntara.auth.services.oidc_service.pyjwt.decode",
                side_effect=pyjwt.InvalidIssuerError("Issuer mismatch"),
            ),
            pytest.raises(OIDCError, match="ID token issuer mismatch"),
        ):
            oidc_service.validate_id_token(
                id_token="token-with-wrong-issuer",
                jwks_uri="https://example.com/jwks",
                issuer="https://example.com",
                client_id="client-123",
                nonce="nonce-456",
            )

    def test_audience_mismatch(self, oidc_service: OIDCService) -> None:
        """Test validation fails for audience mismatch."""
        mock_signing_key = MagicMock()
        mock_signing_key.key = "mock-key"

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt = MagicMock(return_value=mock_signing_key)

        with (
            patch("syntara.auth.services.oidc_service._get_jwks_client", return_value=mock_jwks_client),
            patch(
                "syntara.auth.services.oidc_service.pyjwt.decode",
                side_effect=pyjwt.InvalidAudienceError("Audience mismatch"),
            ),
            pytest.raises(OIDCError, match="ID token audience mismatch"),
        ):
            oidc_service.validate_id_token(
                id_token="token-with-wrong-audience",
                jwks_uri="https://example.com/jwks",
                issuer="https://example.com",
                client_id="client-123",
                nonce="nonce-456",
            )

    def test_nonce_mismatch(self, oidc_service: OIDCService) -> None:
        """Test validation fails for nonce mismatch."""
        claims = {
            "sub": "user-123",
            "iss": "https://example.com",
            "aud": "client-123",
            "nonce": "wrong-nonce",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        }

        mock_signing_key = MagicMock()
        mock_signing_key.key = "mock-key"

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt = MagicMock(return_value=mock_signing_key)

        with patch("syntara.auth.services.oidc_service._get_jwks_client", return_value=mock_jwks_client):
            with patch("syntara.auth.services.oidc_service.pyjwt.decode", return_value=claims):
                with pytest.raises(OIDCError, match="ID token nonce mismatch"):
                    oidc_service.validate_id_token(
                        id_token="token-with-wrong-nonce",
                        jwks_uri="https://example.com/jwks",
                        issuer="https://example.com",
                        client_id="client-123",
                        nonce="expected-nonce",
                    )

    def test_disable_tls_verify_passed_to_jwks_client(self, oidc_service: OIDCService) -> None:
        """Test that disable_tls_verify is forwarded to _get_jwks_client."""
        claims = {
            "sub": "user-123",
            "iss": "https://example.com",
            "aud": "client-123",
            "nonce": "nonce-456",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
        }

        mock_signing_key = MagicMock()
        mock_signing_key.key = "mock-key"

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt = MagicMock(return_value=mock_signing_key)

        with patch(
            "syntara.auth.services.oidc_service._get_jwks_client", return_value=mock_jwks_client
        ) as mock_get_jwks:
            with patch("syntara.auth.services.oidc_service.pyjwt.decode", return_value=claims):
                oidc_service.validate_id_token(
                    id_token="mock-id-token",
                    jwks_uri="https://example.com/jwks",
                    issuer="https://example.com",
                    client_id="client-123",
                    nonce="nonce-456",
                    disable_tls_verify=True,
                )

            mock_get_jwks.assert_called_once_with("https://example.com/jwks", disable_tls_verify=True)

    def test_rejects_http_jwks_uri(self, oidc_service: OIDCService) -> None:
        """Test that ID token validation rejects HTTP jwks_uri (SSRF, AAP-71276)."""
        with patch("syntara.auth.services.oidc_service.get_settings") as mock_gs:
            mock_gs.return_value.oidc_allow_private_networks = False
            with pytest.raises(OIDCError, match="OIDC issuer URL must use HTTPS"):
                oidc_service.validate_id_token(
                    id_token="mock-token",
                    jwks_uri="http://example.com/jwks",
                    issuer="https://example.com",
                    client_id="client-123",
                    nonce="nonce-456",
                )

    def test_rejects_private_ip_jwks_uri(self, oidc_service: OIDCService) -> None:
        """Test that ID token validation rejects jwks_uri resolving to private IPs (SSRF, AAP-71276)."""
        with (
            patch("syntara.auth.services.oidc_service.get_settings") as mock_gs,
            patch("socket.getaddrinfo") as mock_getaddrinfo,
        ):
            mock_gs.return_value.oidc_allow_private_networks = False
            mock_getaddrinfo.return_value = [(None, None, None, None, ("10.0.0.1", 443))]
            with pytest.raises(OIDCError, match="SSRF blocked"):
                oidc_service.validate_id_token(
                    id_token="mock-token",
                    jwks_uri="https://evil-idp.com/jwks",
                    issuer="https://example.com",
                    client_id="client-123",
                    nonce="nonce-456",
                )

    def test_validate_ssl_verification_error(self, oidc_service: OIDCService) -> None:
        """SSL cert verification failure during JWKS fetch produces actionable message."""
        from jwt.exceptions import PyJWKClientConnectionError

        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key_from_jwt = MagicMock(
            side_effect=PyJWKClientConnectionError(
                "Fail to fetch data from the url, err: "
                '"<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] '
                'certificate verify failed: self-signed certificate>"'
            )
        )

        with (
            patch("syntara.auth.services.oidc_service._get_jwks_client", return_value=mock_jwks_client),
            pytest.raises(OIDCError, match="TLS certificate verification failed"),
        ):
            oidc_service.validate_id_token(
                id_token="mock-token",
                jwks_uri="https://example.com/jwks",
                issuer="https://example.com",
                client_id="client-123",
                nonce="nonce-456",
            )


class TestExtractUserClaims:
    """Tests for extract_user_claims method."""

    def test_extracts_all_fields(self, oidc_service: OIDCService) -> None:
        """Test extraction of all user claim fields."""
        id_token_claims = {
            "sub": "user-123",
            "email": "user@example.com",
            "name": "Test User",
            "preferred_username": "testuser",
            "other_field": "ignored",
        }

        result = oidc_service.extract_user_claims(id_token_claims)

        assert result["sub"] == "user-123"
        assert result["email"] == "user@example.com"
        assert result["name"] == "Test User"
        assert result["preferred_username"] == "testuser"
        assert "other_field" not in result

    def test_handles_missing_fields(self, oidc_service: OIDCService) -> None:
        """Test extraction with missing optional fields."""
        id_token_claims = {
            "sub": "user-123",
            # All other fields missing
        }

        result = oidc_service.extract_user_claims(id_token_claims)

        assert result["sub"] == "user-123"
        assert result["email"] is None
        assert result["name"] is None
        assert result["preferred_username"] is None

    def test_custom_claim_mapping(self, oidc_service: OIDCService) -> None:
        """Test extraction with custom claim mapping (e.g. Azure AD claim names)."""
        mapping = OIDCClaimMapping(
            subject="sub",
            email="mail",
            username="upn",
            first_name="givenName",
            last_name="surname",
        )
        id_token_claims = {
            "sub": "user-456",
            "mail": "azure-user@example.com",
            "upn": "azure-user",
            "givenName": "Azure",
            "surname": "User",
        }

        result = oidc_service.extract_user_claims(id_token_claims, mapping)

        assert result["sub"] == "user-456"
        assert result["email"] == "azure-user@example.com"
        assert result["preferred_username"] == "azure-user"
        assert result["given_name"] == "Azure"
        assert result["family_name"] == "User"

    def test_rejects_control_chars_in_email(self, oidc_service: OIDCService) -> None:
        id_token_claims = {"sub": "u1", "email": "user17\n@example.com"}
        with pytest.raises(OIDCError):
            oidc_service.extract_user_claims(id_token_claims)

    def test_rejects_control_chars_in_sub(self, oidc_service: OIDCService) -> None:
        id_token_claims = {"sub": "sub-123\n"}
        with pytest.raises(OIDCError):
            oidc_service.extract_user_claims(id_token_claims)

    def test_escapes_control_chars_in_preferred_username(self, oidc_service: OIDCService) -> None:
        id_token_claims = {"sub": "u1", "preferred_username": "test\ruser"}
        result = oidc_service.extract_user_claims(id_token_claims)
        assert result["preferred_username"] == "test\\ruser"

    def test_escapes_control_chars_in_name(self, oidc_service: OIDCService) -> None:
        id_token_claims = {"sub": "u1", "name": "Test\x00User"}
        result = oidc_service.extract_user_claims(id_token_claims)
        assert result["name"] == "Test\\x00User"

    def test_escapes_control_chars_in_given_name(self, oidc_service: OIDCService) -> None:
        id_token_claims = {"sub": "u1", "given_name": "Test\nUser", "family_name": "Last\rName"}
        result = oidc_service.extract_user_claims(id_token_claims)
        assert result["given_name"] == "Test\\nUser"
        assert result["family_name"] == "Last\\rName"

    def test_clean_claims_unchanged(self, oidc_service: OIDCService) -> None:
        id_token_claims = {
            "sub": "user-123",
            "email": "user@example.com",
            "name": "Test User",
            "preferred_username": "testuser",
        }
        result = oidc_service.extract_user_claims(id_token_claims)
        assert result["sub"] == "user-123"
        assert result["email"] == "user@example.com"
        assert result["name"] == "Test User"
        assert result["preferred_username"] == "testuser"


class TestBuildAuthorizationUrl:
    """Tests for build_authorization_url method."""

    def test_builds_url_with_pkce(self, oidc_service: OIDCService) -> None:
        """Test building authorization URL with PKCE."""
        url = oidc_service.build_authorization_url(
            authorization_endpoint="https://example.com/authorize",
            client_id="client-123",
            redirect_uri="https://app.example.com/callback",
            scopes="openid profile email",
            state="state-456",
            nonce="nonce-789",
            code_challenge="challenge-abc",
        )

        assert url.startswith("https://example.com/authorize?")
        assert "response_type=code" in url
        assert "client_id=client-123" in url
        assert "redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback" in url
        assert "scope=openid+profile+email" in url
        assert "state=state-456" in url
        assert "nonce=nonce-789" in url
        assert "code_challenge=challenge-abc" in url
        assert "code_challenge_method=S256" in url

    def test_builds_url_without_pkce(self, oidc_service: OIDCService) -> None:
        """Test building authorization URL without PKCE."""
        url = oidc_service.build_authorization_url(
            authorization_endpoint="https://example.com/authorize",
            client_id="client-123",
            redirect_uri="https://app.example.com/callback",
            scopes="openid profile email",
            state="state-456",
            nonce="nonce-789",
            code_challenge=None,
        )

        assert url.startswith("https://example.com/authorize?")
        assert "response_type=code" in url
        assert "client_id=client-123" in url
        assert "code_challenge" not in url
        assert "code_challenge_method" not in url

    def test_proper_url_encoding(self, oidc_service: OIDCService) -> None:
        """Test that special characters are properly URL encoded."""
        url = oidc_service.build_authorization_url(
            authorization_endpoint="https://example.com/authorize",
            client_id="client with spaces",
            redirect_uri="https://app.example.com/callback?param=value",
            scopes="openid profile email",
            state="state+special/chars",
            nonce="nonce-789",
            code_challenge=None,
        )

        assert "client_id=client+with+spaces" in url
        assert "redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback%3Fparam%3Dvalue" in url
        assert "state=state%2Bspecial%2Fchars" in url
