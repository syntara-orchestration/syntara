"""JWT Token Service for token creation and validation.

This module provides ES256 (ECDSA P-256) JWT token creation and validation
for access and refresh tokens.

Usage:
    from syntara.auth.services import TokenService

    # Create service instance (typically via dependency injection)
    token_service = TokenService()

    # Create tokens for authenticated user
    access_token = token_service.create_access_token(
        subject_id=user.id,
        username=user.username,
        email=user.email,
    )

    # Validate and decode token
    payload = token_service.decode_token(access_token, token_type="access")
"""

import base64
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import jwt
import structlog
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from syntara.auth.exceptions import InvalidTokenError, TokenExpiredError
from syntara.core.config.base import get_settings
from syntara.core.models.principal import PrincipalType

logger = structlog.stdlib.get_logger(__name__)

JWT_ALGORITHM = "ES256"


@dataclass
class TokenPayload:
    """Decoded JWT token payload.

    Attributes:
        sub: Subject (user ID)
        iss: Issuer
        iat: Issued at timestamp
        exp: Expiration timestamp
        jti: JWT ID (for refresh tokens only)
        email: User email (access tokens only)
        username: Prefixed username (access tokens only)
        token_type: Token type (access or refresh)
        auth_source: Authentication source (local or oidc) (access tokens only)
        groups: Group memberships (access tokens only)
        amr: Authentication methods references (access tokens only)
        idp: Identity provider identifier (access tokens only)

    """

    sub: str
    iss: str
    iat: datetime
    exp: datetime
    token_type: str
    aud: str | None = None
    jti: str | None = None
    email: str | None = None
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    preferred_username: str | None = None
    groups: list[str] | None = None
    token_version: int | None = None
    credential_id: str | None = None
    amr: list[str] | None = None
    idp: str | None = None


class KeyManager:
    """Manages ES256 (ECDSA P-256) keys for JWT signing.

    Handles key loading from file/environment and key rotation support
    via key IDs (kid).

    Supports backup keys for verification-only during key rotation. Backup keys
    can verify existing tokens but are never used for signing new tokens.
    """

    def __init__(self) -> None:
        """Initialize key manager with settings."""
        self._settings = get_settings()
        self._private_key: ec.EllipticCurvePrivateKey | None = None
        self._public_key_pem: bytes | None = None
        self._key_id: str = self._settings.jwt_key_id
        # Backup keys: dict mapping key_id -> public key PEM (for verification only)
        self._backup_keys: dict[str, bytes] = {}
        self._backup_keys_loaded: bool = False

    @property
    def key_id(self) -> str:
        """Get the current key ID."""
        return self._key_id

    def _load_key_from_path(self, path: str) -> ec.EllipticCurvePrivateKey:
        """Load private key from PEM file.

        Args:
            path: Path to PEM file

        Returns:
            Loaded private key

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is not a valid EC private key

        """
        key_path = Path(path)
        if not key_path.exists():
            msg = f"JWT private key file not found: {path}"
            raise FileNotFoundError(msg)

        pem_data = key_path.read_bytes()
        loaded_key = serialization.load_pem_private_key(pem_data, password=None)

        if not isinstance(loaded_key, ec.EllipticCurvePrivateKey):
            msg = "JWT private key must be an EC key (ES256 requires P-256 curve)"
            raise TypeError(msg)

        logger.info("Loaded JWT signing key from file", path=path, key_id=self._key_id)
        return loaded_key

    def _load_key_from_base64(self, encoded: str) -> ec.EllipticCurvePrivateKey:
        """Load private key from base64-encoded PEM.

        Args:
            encoded: Base64-encoded PEM string

        Returns:
            Loaded private key

        Raises:
            ValueError: If data is not a valid EC private key

        """
        pem_data = base64.b64decode(encoded)
        loaded_key = serialization.load_pem_private_key(pem_data, password=None)

        if not isinstance(loaded_key, ec.EllipticCurvePrivateKey):
            msg = "JWT private key must be an EC key (ES256 requires P-256 curve)"
            raise TypeError(msg)

        logger.info("Loaded JWT signing key from environment", key_id=self._key_id)
        return loaded_key

    def get_private_key(self) -> ec.EllipticCurvePrivateKey:
        """Get the private key for signing.

        Priority:
        1. Already loaded key (cached)
        2. Key from file path (APP_JWT_PRIVATE_KEY_PATH)
        3. Key from base64 env var (APP_JWT_PRIVATE_KEY_BASE64)

        Returns:
            EC private key for signing

        Raises:
            RuntimeError: If no key is configured

        """
        if self._private_key is not None:
            return self._private_key

        # Try loading from file path
        if self._settings.jwt_private_key_path:
            self._private_key = self._load_key_from_path(self._settings.jwt_private_key_path)
            return self._private_key

        # Try loading from base64 environment variable
        if self._settings.jwt_private_key_base64:
            key_data = self._settings.jwt_private_key_base64.get_secret_value()
            self._private_key = self._load_key_from_base64(key_data)
            return self._private_key

        msg = (
            "No JWT signing key configured. "
            "Set APP_JWT_PRIVATE_KEY_PATH or APP_JWT_PRIVATE_KEY_BASE64, "
            "or run 'make secrets-generate' to create development keys."
        )
        raise RuntimeError(msg)

    def get_public_key_pem(self) -> bytes:
        """Get the public key in PEM format for verification.

        Returns:
            PEM-encoded public key bytes

        """
        if self._public_key_pem is not None:
            return self._public_key_pem

        private_key = self.get_private_key()
        public_key = private_key.public_key()
        self._public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return self._public_key_pem

    def _load_backup_keys(self) -> None:
        """Load backup keys from settings for verification during key rotation.

        Backup keys are public keys only (derived from private keys) and are
        used to verify tokens that were signed with previous keys.
        """
        if self._backup_keys_loaded:
            return

        self._backup_keys_loaded = True
        backup_keys_config = self._settings.jwt_backup_keys

        if not backup_keys_config:
            return

        for key_config in backup_keys_config:
            key_id = key_config.get("key_id")
            if not key_id:
                logger.warning("Backup key config missing 'key_id', skipping")
                continue

            # Skip if this key_id matches the primary key
            if key_id == self._key_id:
                logger.warning(
                    "Backup key has same key_id as primary key, skipping",
                    key_id=key_id,
                )
                continue

            try:
                # Load private key, extract public key
                private_key: ec.EllipticCurvePrivateKey | None = None

                if key_path := key_config.get("key_path"):
                    private_key = self._load_key_from_path(key_path)
                elif key_base64 := key_config.get("key_base64"):
                    private_key = self._load_key_from_base64(key_base64)
                else:
                    logger.warning(
                        "Backup key config missing 'key_path' or 'key_base64', skipping",
                        key_id=key_id,
                    )
                    continue

                # Store only the public key PEM
                public_key = private_key.public_key()
                public_key_pem = public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
                self._backup_keys[key_id] = public_key_pem
                logger.info("Loaded backup key for verification", key_id=key_id)

            except (FileNotFoundError, TypeError, ValueError) as e:
                logger.warning(
                    "Failed to load backup key, skipping",
                    key_id=key_id,
                    error=str(e),
                )

    def get_public_key_for_kid(self, kid: str) -> bytes | None:
        """Get the public key PEM for a given key ID.

        Looks up the public key for the specified key ID, checking the primary
        key first and then backup keys.

        Args:
            kid: The key ID from the JWT header

        Returns:
            PEM-encoded public key bytes, or None if key ID is unknown

        """
        # Check primary key first
        if kid == self._key_id:
            return self.get_public_key_pem()

        # Load backup keys if not already loaded
        self._load_backup_keys()

        # Check backup keys
        return self._backup_keys.get(kid)

    def get_all_key_ids(self) -> list[str]:
        """Get all known key IDs (primary + backup).

        Returns:
            List of all key IDs that can be used for verification

        """
        self._load_backup_keys()
        return [self._key_id, *self._backup_keys.keys()]

    def _public_key_to_jwk(self, kid: str, public_key_pem: bytes) -> dict[str, str]:
        """Convert a public key PEM to JWK format.

        Args:
            kid: The key ID for this key
            public_key_pem: PEM-encoded public key bytes

        Returns:
            JWK dictionary for the key

        """
        public_key = serialization.load_pem_public_key(public_key_pem)
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            msg = "Public key must be an EC key"
            raise TypeError(msg)

        public_numbers = public_key.public_numbers()

        def to_base64url(num: int, length: int) -> str:
            """Convert integer to base64url without padding."""
            num_bytes = num.to_bytes(length, byteorder="big")
            return base64.urlsafe_b64encode(num_bytes).rstrip(b"=").decode("ascii")

        # P-256 curve uses 32-byte coordinates
        x = to_base64url(public_numbers.x, 32)
        y = to_base64url(public_numbers.y, 32)

        return {
            "kid": kid,
            "kty": "EC",
            "use": "sig",
            "alg": "ES256",
            "crv": "P-256",
            "x": x,
            "y": y,
        }

    def get_jwks(self) -> dict[str, Any]:
        """Get the JWKS (JSON Web Key Set) for public key distribution.

        Returns all keys (primary + backup) for verification. The primary key
        is listed first, followed by any backup keys.

        Returns:
            JWKS dictionary with all public keys in JWK format

        """
        keys: list[dict[str, str]] = []

        # Add primary key first
        primary_jwk = self._public_key_to_jwk(self._key_id, self.get_public_key_pem())
        keys.append(primary_jwk)

        # Add backup keys
        self._load_backup_keys()
        for backup_kid, backup_pem in self._backup_keys.items():
            try:
                backup_jwk = self._public_key_to_jwk(backup_kid, backup_pem)
                keys.append(backup_jwk)
            except (TypeError, ValueError) as e:
                logger.warning(
                    "Failed to convert backup key to JWK, skipping",
                    key_id=backup_kid,
                    error=str(e),
                )

        return {"keys": keys}


_key_manager_instance: KeyManager | None = None
_key_manager_lock = threading.Lock()


def get_key_manager() -> KeyManager:
    """Get cached key manager instance.

    The ``KeyManager`` is cached for the lifetime of the process.
    Call ``clear_key_manager_cache`` to force a reload (e.g. during
    emergency key rotation or in tests).

    Thread-safe: uses a lock to prevent concurrent initialization.
    """
    global _key_manager_instance  # noqa: PLW0603
    with _key_manager_lock:
        if _key_manager_instance is None:
            _key_manager_instance = KeyManager()
        return _key_manager_instance


def clear_key_manager_cache() -> None:
    """Clear the cached KeyManager, forcing a reload on next access.

    Use this for emergency key rotation (e.g. via a SIGHUP handler)
    or to prevent cross-test contamination in unit tests.
    """
    global _key_manager_instance  # noqa: PLW0603
    with _key_manager_lock:
        _key_manager_instance = None
    logger.info("KeyManager cache cleared, new keys will be loaded on next access")


class TokenService:
    """JWT Token Service for creating and validating tokens.

    This service handles ES256 JWT creation and validation for both
    access tokens (short-lived, stateless) and refresh tokens (longer-lived,
    tracked in PostgreSQL).
    """

    def __init__(self, key_manager: KeyManager | None = None) -> None:
        """Initialize token service.

        Args:
            key_manager: Optional key manager instance (uses cached instance if None)

        """
        self._settings = get_settings()
        self._key_manager = key_manager or get_key_manager()

    # JWT audience claim value
    _AUDIENCE: str = "orchestrator-api"

    def create_access_token(
        self,
        subject_id: UUID | str,
        username: str,
        email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        amr: list[str] | None = None,
        idp: str = "local",
        groups: list[str] | None = None,
        token_version: int = 0,
        credential_id: UUID | str | None = None,
        *,
        principal_type: PrincipalType = PrincipalType.USER,
    ) -> str:
        """Create a JWT access token.

        Args:
            subject_id: Principal UUID (user or service account, stored in 'sub' claim)
            username: Username or service account name
            email: User email
            first_name: User's first name (OIDC 'given_name' claim)
            last_name: User's last name (OIDC 'family_name' claim)
            amr: Authentication methods references (e.g., ["pwd"], ["fed", "mfa"])
            idp: Identity provider identifier (e.g., "local", "azure-ad-prod")
            groups: Group memberships
            token_version: Token version counter for stale token detection
            credential_id: SA credential UUID embedded in the JWT for per-credential revocation
            principal_type: Principal type — PrincipalType.USER or PrincipalType.SERVICE_ACCOUNT

        Returns:
            Encoded JWT string

        """
        now = datetime.now(UTC)
        is_service_account = principal_type == PrincipalType.SERVICE_ACCOUNT

        lifetime_minutes = (
            self._settings.jwt_sa_access_token_lifetime_minutes
            if is_service_account
            else self._settings.jwt_access_token_lifetime_minutes
        )
        exp = now + timedelta(minutes=lifetime_minutes)

        if groups is None:
            groups = []

        cred_id_str = str(credential_id) if credential_id is not None else None

        if is_service_account:
            # SAs get permissions via direct role assignments, not group membership
            payload: dict[str, Any] = {
                "sub": str(subject_id),
                "iss": self._settings.jwt_issuer,
                "aud": self._AUDIENCE,
                "iat": now,
                "exp": exp,
                "token_type": "service_account",
                "preferred_username": username,
                "groups": [],
                "token_ver": token_version,
                "cred_id": cred_id_str,
            }
        else:
            if amr is None:
                amr = ["pwd"]

            payload = {
                "sub": str(subject_id),
                "iss": self._settings.jwt_issuer,
                "aud": self._AUDIENCE,
                "iat": now,
                "exp": exp,
                "preferred_username": username,
                "email": email,
                "groups": groups,
                "token_ver": token_version,
                "amr": amr,
                "idp": idp,
            }
            if first_name:
                display_name = f"{first_name} {last_name}".strip() if last_name else first_name
                payload["name"] = display_name
                payload["given_name"] = first_name
                if last_name:
                    payload["family_name"] = last_name

        headers = {
            "kid": self._key_manager.key_id,
            "typ": "at+jwt",
        }

        token = jwt.encode(
            payload,
            self._key_manager.get_private_key(),
            algorithm=JWT_ALGORITHM,
            headers=headers,
        )

        logger.debug(
            "Created access token",
            subject_id=str(subject_id),
            principal_type=principal_type,
            expires_at=exp.isoformat(),
        )

        return token

    def create_refresh_token(self, user_id: UUID | str) -> tuple[str, str, datetime]:
        """Create a JWT refresh token.

        Args:
            user_id: User UUID (stored in 'sub' claim)

        Returns:
            Tuple of (encoded JWT string, JTI, expiration datetime)

        """
        now = datetime.now(UTC)
        exp = now + timedelta(hours=self._settings.jwt_refresh_token_lifetime_hours)
        jti = secrets.token_urlsafe(16)

        payload = {
            "sub": str(user_id),
            "jti": jti,
            "typ": "refresh",
            "iss": self._settings.jwt_issuer,
            "aud": self._AUDIENCE,
            "iat": now,
            "exp": exp,
        }

        headers = {
            "kid": self._key_manager.key_id,
        }

        token = jwt.encode(
            payload,
            self._key_manager.get_private_key(),
            algorithm=JWT_ALGORITHM,
            headers=headers,
        )

        logger.debug(
            "Created refresh token",
            user_id=str(user_id),
            jti=jti,
            expires_at=exp.isoformat(),
        )

        return token, jti, exp

    def decode_token(self, token: str, *, token_type: str = "access") -> TokenPayload:  # noqa: S107
        """Decode and validate a JWT token.

        Args:
            token: The JWT token string
            token_type: Expected token type ("access" or "refresh")

        Returns:
            Decoded token payload

        Raises:
            TokenExpiredError: If token has expired
            InvalidTokenError: If token is invalid (signature, issuer, claims, etc.)

        """
        try:
            # Read kid from header to select the correct verification key (signature is verified below)
            unverified_header = jwt.get_unverified_header(token)  # NOSONAR
            kid = unverified_header.get("kid")

            # Look up the public key for this key ID (supports key rotation)
            public_key_pem = self._key_manager.get_public_key_for_kid(kid) if kid else None
            if public_key_pem is None:
                logger.warning(
                    "Token has unknown key ID",
                    kid=kid,
                    known_keys=self._key_manager.get_all_key_ids(),
                )
                raise InvalidTokenError

            # Decode and verify with the matching public key
            payload = jwt.decode(
                token,
                public_key_pem,
                algorithms=[JWT_ALGORITHM],
                issuer=self._settings.jwt_issuer,
                audience=self._AUDIENCE,
            )

            # Validate token type via header typ or payload typ
            actual_type = unverified_header.get("typ", "").replace("at+jwt", "access")
            if actual_type != token_type:
                # Fall back to payload typ claim (refresh tokens)
                actual_type = payload.get("typ", "access")
            if actual_type != token_type:
                logger.warning(
                    "Token type mismatch",
                    expected=token_type,
                    actual=actual_type,
                )
                raise InvalidTokenError(f"Expected {token_type} token, got {actual_type}")  # noqa: EM102, TRY003

            # Convert timestamps
            iat = datetime.fromtimestamp(payload["iat"], tz=UTC)
            exp = datetime.fromtimestamp(payload["exp"], tz=UTC)

            return TokenPayload(
                sub=payload["sub"],
                iss=payload["iss"],
                iat=iat,
                exp=exp,
                token_type=payload.get("token_type", actual_type),
                aud=payload.get("aud"),
                jti=payload.get("jti"),
                email=payload.get("email"),
                name=payload.get("name"),
                preferred_username=payload.get("preferred_username"),
                groups=payload.get("groups"),
                token_version=payload.get("token_ver"),
                credential_id=payload.get("cred_id"),
                amr=payload.get("amr"),
                idp=payload.get("idp"),
            )

        except jwt.ExpiredSignatureError as e:
            logger.debug("Token expired")
            raise TokenExpiredError from e
        except jwt.InvalidIssuerError as e:
            logger.warning("Invalid token issuer")
            raise InvalidTokenError from e
        except jwt.InvalidSignatureError as e:
            logger.warning("Invalid token signature")
            raise InvalidTokenError from e
        except jwt.DecodeError as e:
            logger.warning("Failed to decode token", error=str(e))
            raise InvalidTokenError from e
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid token", error=str(e))
            raise InvalidTokenError from e
        except KeyError as e:
            logger.warning("Missing required claim", claim=str(e))
            raise InvalidTokenError from e

    def get_jwks(self) -> dict[str, Any]:
        """Get the JWKS for public key distribution.

        Returns:
            JWKS dictionary

        """
        return self._key_manager.get_jwks()
