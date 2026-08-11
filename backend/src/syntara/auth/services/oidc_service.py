"""OIDC authentication service.

Handles the full OpenID Connect authorization code flow with PKCE:
- OIDC discovery configuration fetching
- Authorization URL generation with state/nonce/PKCE
- Authorization code exchange for tokens
- ID token validation (signature, issuer, audience, nonce)
- User claim extraction
"""

import hashlib
import secrets
import ssl
import time
from base64 import urlsafe_b64encode
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode, urlparse
from uuid import UUID

import httpx
import jwt as pyjwt
import structlog
from jwt import PyJWKClient
from langchain_core._security._ssrf_protection import validate_safe_url
from starlette import status

from syntara.auth.exceptions import OIDCErrorCode
from syntara.core.config.base import get_encryption_key, get_settings
from syntara.core.exceptions import NexusError
from syntara.core.lib.encryption import EncryptionError, SecretEncryptor, key_from_string
from syntara.core.lib.sanitization import escape_control_chars, has_control_chars
from syntara.identity_providers.models.identity_provider_configuration import OIDCClaimMapping

logger = structlog.stdlib.get_logger(__name__)

OIDC_STATE_TTL_SECONDS = 600  # 10 minutes

# Bounded cache for PyJWKClient instances keyed by jwks_uri.
# PyJWKClient has built-in JWKS caching, but a new instance per call loses the cache.
# LRU eviction prevents unbounded growth when providers are deleted/recreated.
_MAX_JWKS_CLIENTS = 32


def _create_insecure_ssl_context() -> ssl.SSLContext:
    """Build an SSL context that skips all certificate verification.

    Both hostname verification and CA trust-chain validation are disabled,
    allowing self-signed or internally-signed certificates.
    Used when the admin has explicitly opted in via ``disable_tls_verify``.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


@lru_cache(maxsize=_MAX_JWKS_CLIENTS)
def _get_jwks_client(jwks_uri: str, *, disable_tls_verify: bool = False) -> PyJWKClient:
    """Return a cached PyJWKClient for the given JWKS URI.

    The LRU cache ensures we reuse the same client (and its internal JWKS
    key-set cache) across calls for the same ``jwks_uri``.  ``PyJWKClient``
    caches the fetched key-set for ``lifespan`` seconds, so repeated
    ``get_signing_key_from_jwt`` calls within that window avoid a network
    round-trip.  See:
    https://github.com/ansible/django-ansible-base/commit/7dfca80
    """
    kwargs: dict[str, Any] = {"timeout": 10, "cache_jwk_set": True, "lifespan": 300}
    if disable_tls_verify:
        kwargs["ssl_context"] = _create_insecure_ssl_context()
    return PyJWKClient(jwks_uri, **kwargs)


_SSL_VERIFY_FAILED_MARKER = "CERTIFICATE_VERIFY_FAILED"

_TLS_VERIFY_HINT = (
    "TLS certificate verification failed while connecting to the identity provider. "
    "If the provider uses a self-signed or internally-signed certificate, "
    'enable "Skip TLS certificate verification" in the identity provider configuration.'
)


def _is_ssl_verification_error(exc: Exception) -> bool:
    """Return True if the exception chain indicates an SSL certificate verification failure."""
    return _SSL_VERIFY_FAILED_MARKER in str(exc)


class OIDCError(NexusError):
    """Base exception for OIDC flow errors."""

    def __init__(self, message: str, *, error_code: OIDCErrorCode | None = None) -> None:
        """Initialize with message and optional OAuth2 error code."""
        super().__init__(message)
        self.error_code = error_code


class OIDCService:
    """Service for OIDC authorization code flow with PKCE.

    Stateless utility — no connection state. OIDC flow state is encoded
    as a signed JWT in the OAuth2 state parameter (no server-side storage).
    """

    def _validate_url(self, url: str) -> None:
        """Validate a URL to mitigate SSRF attacks.

        Delegates to the shared validate_url_no_ssrf() utility for hostname
        resolution checks. OIDC-specific scheme enforcement (HTTPS required
        unless oidc_allow_private_networks is enabled) is applied here.

        Note: a TOCTOU DNS rebinding gap exists between this validation and the
        subsequent HTTP request. See validate_url_no_ssrf() for details.

        Raises:
            OIDCError: If the URL fails validation

        """
        parsed = urlparse(url)
        allow_private = get_settings().oidc_allow_private_networks

        if parsed.scheme == "http" and not allow_private:
            msg = "OIDC issuer URL must use HTTPS"
            raise OIDCError(msg)
        if parsed.scheme not in ("https", "http"):
            msg = "OIDC issuer URL must use HTTPS"
            raise OIDCError(msg)

        try:
            validate_safe_url(url, allow_private=allow_private, allow_http=True)
        except ValueError as e:
            raise OIDCError(str(e)) from e

    async def fetch_discovery_config(self, issuer_url: str, *, disable_tls_verify: bool = False) -> dict[str, Any]:
        """Fetch OIDC discovery configuration from the provider.

        Args:
            issuer_url: The OIDC issuer URL
            disable_tls_verify: Skip TLS certificate verification (insecure)

        Returns:
            Discovery configuration dictionary

        Raises:
            OIDCError: If discovery fails

        """
        discovery_url = f"{issuer_url.rstrip('/')}/.well-known/openid-configuration"

        # SSRF mitigation: validate URL scheme and resolved IPs.
        # See _validate_url docstring for TOCTOU DNS rebinding notes.
        #
        # Note: follow_redirects=True is intentionally kept on all OIDC HTTP
        # clients.  A redirect-based SSRF bypass would require an admin-configured
        # provider URL to redirect to internal infrastructure; since provider
        # config is admin-only, this is an accepted risk.  Disabling redirects
        # would break legitimate providers behind load balancers or HTTP→HTTPS
        # upgrades.  If stricter controls are needed, a redirect-validating
        # httpx transport hook can be added without breaking existing configs.
        self._validate_url(discovery_url)

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, verify=not disable_tls_verify) as client:
                response = await client.get(discovery_url)

            if response.status_code != status.HTTP_200_OK:
                msg = f"Discovery endpoint returned HTTP {response.status_code}"
                raise OIDCError(msg)

            data: dict[str, Any] = response.json()

            required = {"authorization_endpoint", "token_endpoint", "issuer", "jwks_uri"}
            missing = required - set(data.keys())
            if missing:
                msg = f"Discovery response missing: {', '.join(sorted(missing))}"
                raise OIDCError(msg)

            return data

        except httpx.TimeoutException as e:
            msg = f"Discovery request timed out for {issuer_url}"
            raise OIDCError(msg) from e
        except httpx.ConnectError as e:
            if _is_ssl_verification_error(e):
                logger.warning("TLS certificate verification failed during OIDC discovery", issuer=issuer_url)
                raise OIDCError(_TLS_VERIFY_HINT) from e
            msg = f"Discovery request failed: {e}"
            raise OIDCError(msg) from e
        except httpx.RequestError as e:
            msg = f"Discovery request failed: {e}"
            raise OIDCError(msg) from e
        except ValueError as e:
            # Covers JSONDecodeError (subclass of ValueError) when the response is not valid JSON
            msg = f"Discovery response is not valid JSON from {issuer_url}"
            raise OIDCError(msg) from e

    def generate_pkce(self) -> tuple[str, str]:
        """Generate PKCE code verifier and challenge.

        Returns:
            Tuple of (code_verifier, code_challenge)

        """
        code_verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return code_verifier, code_challenge

    def generate_nonce(self) -> str:
        """Generate a cryptographically secure nonce value."""
        return secrets.token_urlsafe(32)

    # AAD (Associated Authenticated Data) for AES-GCM encryption of OIDC state.
    # Binds ciphertext to this specific context so encrypted values from other
    # uses of SecretEncryptor (e.g. credential fields, id_token_hint) cannot
    # be substituted.
    _STATE_AAD_ID = "oidc-flow"
    _STATE_AAD_FIELD = "state"

    def store_oidc_state(
        self,
        provider_id: UUID,
        nonce: str,
        code_verifier: str,
        redirect_to: str | None = None,
        origin: str | None = None,
        flow_type: str | None = None,
        user_id: str | None = None,
        session_jti: str | None = None,
    ) -> str:
        """Encrypt OIDC flow state and return as the OAuth2 state parameter.

        Uses AES-256-GCM (via SecretEncryptor) so the payload — including
        the PKCE code_verifier — is not visible in the browser URL bar.
        An ``exp`` timestamp is embedded for TTL enforcement on decode.
        """
        now = time.time()
        payload: dict[str, Any] = {
            "provider_id": str(provider_id),
            "nonce": nonce,
            "code_verifier": code_verifier,
            "exp": now + OIDC_STATE_TTL_SECONDS,
        }
        if redirect_to:
            payload["redirect_to"] = redirect_to
        if origin:
            payload["origin"] = origin
        if flow_type:
            payload["flow_type"] = flow_type
        if user_id:
            payload["user_id"] = user_id
        if session_jti:
            payload["session_jti"] = session_jti

        enc_key = key_from_string(get_encryption_key().get_secret_value())
        encryptor = SecretEncryptor(enc_key)
        token = encryptor.encrypt_field(payload, self._STATE_AAD_ID, self._STATE_AAD_FIELD)
        logger.debug("Encrypted OIDC state")
        return token

    def retrieve_oidc_state(self, state: str) -> dict[str, str] | None:
        """Decrypt and validate an encrypted OIDC state parameter.

        Checks the embedded ``exp`` timestamp for TTL enforcement.
        Returns state data dict or None if invalid/expired/tampered.
        """
        enc_key = key_from_string(get_encryption_key().get_secret_value())
        encryptor = SecretEncryptor(enc_key)
        try:
            payload: dict[str, Any] = encryptor.decrypt_field(state, self._STATE_AAD_ID, self._STATE_AAD_FIELD)
        except EncryptionError:
            logger.warning("OIDC state decryption failed (invalid or tampered)")
            return None

        exp = payload.pop("exp", 0)
        if time.time() > exp:
            logger.warning("OIDC state expired")
            return None

        result: dict[str, str] = {k: str(v) for k, v in payload.items()}
        return result

    async def exchange_code_for_tokens(
        self,
        token_endpoint: str,
        code: str,
        redirect_uri: str,
        client_id: str,
        client_secret: str,
        code_verifier: str,
        *,
        disable_tls_verify: bool = False,
    ) -> dict[str, Any]:
        """Exchange authorization code for tokens at the token endpoint.

        Args:
            token_endpoint: Provider's token endpoint URL
            code: Authorization code from the callback
            redirect_uri: The redirect URI used in the authorize request
            client_id: OAuth 2.0 client ID
            client_secret: OAuth 2.0 client secret
            code_verifier: PKCE code verifier
            disable_tls_verify: Skip TLS certificate verification (insecure)

        Returns:
            Token response dictionary containing access_token, id_token, etc.

        Raises:
            OIDCError: If token exchange fails

        """
        # SSRF mitigation: validate token endpoint URL before making the request.
        # The token_endpoint may come from discovery or manual IdP configuration;
        # an attacker who controls IdP config could target internal services (AAP-71276).
        self._validate_url(token_endpoint)

        try:
            token_data: dict[str, str] = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
            }
            if client_secret:
                token_data["client_secret"] = client_secret
            if code_verifier:
                token_data["code_verifier"] = code_verifier

            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, verify=not disable_tls_verify) as client:
                response = await client.post(
                    token_endpoint,
                    data=token_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

            if response.status_code not in (status.HTTP_200_OK, status.HTTP_201_CREATED):
                logger.warning("Token exchange failed", status=response.status_code)
                msg = f"Token exchange failed with HTTP {response.status_code}"
                raise OIDCError(msg)

            result: dict[str, Any] = response.json()
            return result

        except httpx.TimeoutException as e:
            msg = "Token exchange request timed out"
            raise OIDCError(msg) from e
        except httpx.ConnectError as e:
            if _is_ssl_verification_error(e):
                logger.warning("TLS certificate verification failed during token exchange", error=str(e))
                raise OIDCError(_TLS_VERIFY_HINT) from e
            msg = f"Token exchange request failed: {e}"
            raise OIDCError(msg) from e
        except httpx.RequestError as e:
            msg = f"Token exchange request failed: {e}"
            raise OIDCError(msg) from e

    def validate_id_token(
        self,
        id_token: str,
        jwks_uri: str,
        issuer: str,
        client_id: str,
        nonce: str,
        *,
        disable_tls_verify: bool = False,
    ) -> dict[str, Any]:
        """Validate an OIDC ID token.

        Verifies signature via provider's JWKS, validates issuer, audience, and nonce.

        Args:
            id_token: The raw ID token JWT
            jwks_uri: URL to the provider's JWKS endpoint
            issuer: Expected issuer claim
            client_id: Expected audience claim
            nonce: Expected nonce claim
            disable_tls_verify: Skip TLS certificate verification (insecure)

        Returns:
            Decoded ID token claims

        Raises:
            OIDCError: If validation fails

        """
        # SSRF mitigation: validate jwks_uri before fetching keys.
        # The URI may come from discovery or manual config (AAP-71276).
        self._validate_url(jwks_uri)

        try:
            # PyJWKClient instance is cached via _get_jwks_client (LRU).  Its
            # internal JWKS response cache avoids repeated network fetches, but
            # the signing-key *lookup* itself (~38ms) is performed each call.
            # The LRU on _get_jwks_client ensures we reuse the same client (and
            # its built-in lifespan cache) across calls for the same jwks_uri,
            # which amortises the cost.  See:
            # https://github.com/ansible/django-ansible-base/commit/7dfca80
            jwks_client = _get_jwks_client(jwks_uri, disable_tls_verify=disable_tls_verify)
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)

            claims: dict[str, Any] = pyjwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256", "ES256", "PS256"],
                audience=client_id,
                issuer=issuer,
            )

            if claims.get("nonce") != nonce:
                msg = "ID token nonce mismatch"
                raise OIDCError(msg)

            return claims

        except pyjwt.ExpiredSignatureError as e:
            msg = "ID token has expired"
            raise OIDCError(msg) from e
        except pyjwt.InvalidIssuerError as e:
            msg = "ID token issuer mismatch"
            raise OIDCError(msg) from e
        except pyjwt.InvalidAudienceError as e:
            msg = "ID token audience mismatch"
            raise OIDCError(msg) from e
        except pyjwt.PyJWTError as e:
            if _is_ssl_verification_error(e):
                logger.warning("TLS certificate verification failed during JWKS fetch", error=str(e))
                raise OIDCError(_TLS_VERIFY_HINT) from e
            msg = f"ID token validation failed: {e}"
            raise OIDCError(msg) from e

    async def fetch_userinfo(
        self, userinfo_endpoint: str, access_token: str, *, disable_tls_verify: bool = False
    ) -> dict[str, Any]:
        """Fetch user claims from the OIDC userinfo endpoint.

        Per OIDC Core §5.3, the userinfo endpoint returns claims about the
        authenticated user.  This supplements the ID token when it contains
        only minimal claims (e.g. just ``sub``).

        Args:
            userinfo_endpoint: Provider's userinfo endpoint URL
            access_token: Bearer access token from the token exchange
            disable_tls_verify: Skip TLS certificate verification (insecure)

        Returns:
            Userinfo claims dictionary

        Raises:
            OIDCError: If the request fails

        """
        self._validate_url(userinfo_endpoint)

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, verify=not disable_tls_verify) as client:
                response = await client.get(
                    userinfo_endpoint,
                    headers={"Authorization": f"Bearer {access_token}"},
                )

            if response.status_code != status.HTTP_200_OK:
                msg = f"Userinfo endpoint returned HTTP {response.status_code}"
                raise OIDCError(msg)

            result: dict[str, Any] = response.json()
            return result

        except httpx.TimeoutException as e:
            msg = "Userinfo request timed out"
            raise OIDCError(msg) from e
        except httpx.ConnectError as e:
            if _is_ssl_verification_error(e):
                logger.warning("TLS certificate verification failed during userinfo fetch", error=str(e))
                raise OIDCError(_TLS_VERIFY_HINT) from e
            msg = f"Userinfo request failed: {e}"
            raise OIDCError(msg) from e
        except httpx.RequestError as e:
            msg = f"Userinfo request failed: {e}"
            raise OIDCError(msg) from e
        except ValueError as e:
            msg = "Userinfo response is not valid JSON"
            raise OIDCError(msg) from e

    def extract_user_claims(
        self,
        id_token_claims: dict[str, Any],
        claim_mapping: OIDCClaimMapping | None = None,
    ) -> dict[str, str | None]:
        """Extract user information from ID token claims.

        Args:
            id_token_claims: Decoded ID token claims
            claim_mapping: Optional mapping of Nexus fields to IdP claim names.
                If None, uses default OIDC claim names.

        Returns:
            Dict with canonical keys: sub, email, name, preferred_username
            (and optionally groups)

        """
        if claim_mapping is None:
            claim_mapping = OIDCClaimMapping()

        result: dict[str, str | None] = {
            "sub": id_token_claims.get(claim_mapping.subject),
            "email": id_token_claims.get(claim_mapping.email),
            "given_name": id_token_claims.get(claim_mapping.first_name),
            "family_name": id_token_claims.get(claim_mapping.last_name),
            # Hardcoded: "name" is a standard OIDC claim used only as a fallback
            # when given_name/family_name aren't available.  Custom mappings
            # (e.g. Azure AD "displayName") are handled via claim_mapping.first_name,
            # which takes priority in _auto_create_user.
            "name": id_token_claims.get("name"),
            "preferred_username": id_token_claims.get(claim_mapping.username),
        }

        identity_claims = {"sub", "email"}
        for key, value in result.items():
            if not isinstance(value, str) or not has_control_chars(value):
                continue
            if key in identity_claims:
                logger.warning(
                    "Rejected OIDC token: control characters in identity claim",
                    claim=key,
                    escaped_value=escape_control_chars(value),
                )
                msg = "Authentication failed. Please try again."
                raise OIDCError(msg)
            escaped = escape_control_chars(value)
            logger.warning(
                "Escaped control characters in OIDC claim",
                claim=key,
                escaped_value=escaped,
            )
            result[key] = escaped

        return result

    def build_authorization_url(
        self,
        authorization_endpoint: str,
        client_id: str,
        redirect_uri: str,
        scopes: str,
        state: str,
        nonce: str,
        code_challenge: str | None = None,
    ) -> str:
        """Build the OIDC authorization URL.

        Args:
            authorization_endpoint: Provider's authorization endpoint
            client_id: OAuth 2.0 client ID
            redirect_uri: Callback URL
            scopes: Space-separated scopes
            state: State parameter
            nonce: Nonce parameter
            code_challenge: PKCE code challenge (omit for confidential clients)

        Returns:
            Full authorization URL

        """
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scopes,
            "state": state,
            "nonce": nonce,
        }

        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        return f"{authorization_endpoint}?{urlencode(params)}"
