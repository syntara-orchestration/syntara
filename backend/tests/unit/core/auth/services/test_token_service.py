"""Unit tests for JWT TokenService.

Tests cover:
- Token creation (access and refresh tokens)
- Token validation (signature, claims, issuer)
- Token expiry handling
- Algorithm enforcement (ES256)
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from syntara.auth.exceptions import InvalidTokenError, TokenExpiredError
from syntara.auth.services.token_service import (
    KeyManager,
    TokenPayload,
    TokenService,
    clear_key_manager_cache,
    get_key_manager,
)


class TestKeyManager:
    """Tests for KeyManager."""

    def test_raises_when_no_key_configured(self) -> None:
        """Test that KeyManager raises RuntimeError when no key is configured."""
        with patch("syntara.auth.services.token_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                jwt_private_key_path=None,
                jwt_private_key_base64=None,
                jwt_key_id="test-key",
            )
            key_manager = KeyManager()

            with pytest.raises(RuntimeError, match="No JWT signing key configured"):
                key_manager.get_private_key()

    def test_key_is_cached(self) -> None:
        """Test that the private key is cached after first access."""
        with patch("syntara.auth.services.token_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                jwt_private_key_path=None,
                jwt_private_key_base64=None,
                jwt_key_id="test-key",
            )
            key_manager = KeyManager()
            key_manager._private_key = ec.generate_private_key(ec.SECP256R1())
            key1 = key_manager.get_private_key()
            key2 = key_manager.get_private_key()

            assert key1 is key2

    def test_public_key_pem_derivation(self) -> None:
        """Test that public key PEM is correctly derived from private key."""
        with patch("syntara.auth.services.token_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                jwt_private_key_path=None,
                jwt_private_key_base64=None,
                jwt_key_id="test-key",
            )
            key_manager = KeyManager()
            key_manager._private_key = ec.generate_private_key(ec.SECP256R1())
            public_key_pem = key_manager.get_public_key_pem()

            assert public_key_pem.startswith(b"-----BEGIN PUBLIC KEY-----")
            assert public_key_pem.endswith(b"-----END PUBLIC KEY-----\n")

    def test_jwks_format(self) -> None:
        """Test that JWKS is correctly formatted."""
        with patch("syntara.auth.services.token_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                jwt_private_key_path=None,
                jwt_private_key_base64=None,
                jwt_key_id="test-key-id",
            )
            key_manager = KeyManager()
            key_manager._private_key = ec.generate_private_key(ec.SECP256R1())
            jwks = key_manager.get_jwks()

            assert "keys" in jwks
            assert len(jwks["keys"]) == 1

            key = jwks["keys"][0]
            assert key["kid"] == "test-key-id"
            assert key["kty"] == "EC"
            assert key["use"] == "sig"
            assert key["alg"] == "ES256"
            assert key["crv"] == "P-256"
            assert "x" in key
            assert "y" in key


@pytest.fixture
def token_service() -> TokenService:
    """Create a TokenService with a test signing key."""
    with patch("syntara.auth.services.token_service.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            jwt_private_key_path=None,
            jwt_private_key_base64=None,
            jwt_key_id="test-key",
            jwt_issuer="https://localhost:8000",
            jwt_access_token_lifetime_minutes=15,
            jwt_refresh_token_lifetime_hours=8,
        )
        key_manager = KeyManager()
        key_manager._private_key = ec.generate_private_key(ec.SECP256R1())
        return TokenService(key_manager=key_manager)


class TestTokenCreation:
    """Tests for token creation."""

    def test_create_access_token_returns_string(self, token_service: TokenService) -> None:
        """Test that create_access_token returns a JWT string."""
        user_id = uuid4()
        token = token_service.create_access_token(
            subject_id=user_id,
            username="test-instance/testuser",
            email="test@example.com",
        )

        assert isinstance(token, str)
        assert len(token) > 0
        # JWT has 3 parts separated by dots
        assert len(token.split(".")) == 3

    def test_create_access_token_contains_correct_claims(self, token_service: TokenService) -> None:
        """Test that access token contains all required claims."""
        user_id = uuid4()
        token = token_service.create_access_token(
            subject_id=user_id,
            username="testuser",
            email="test@example.com",
        )

        # Decode without verification to inspect claims
        payload = jwt.decode(token, options={"verify_signature": False, "verify_aud": False})
        header = jwt.get_unverified_header(token)

        assert payload["sub"] == str(user_id)
        assert payload["email"] == "test@example.com"
        assert payload["preferred_username"] == "testuser"
        assert payload["amr"] == ["pwd"]
        assert payload["idp"] == "local"
        assert payload["groups"] == []
        assert payload["aud"] == "orchestrator-api"
        assert payload["iss"] == "https://localhost:8000"
        assert header["typ"] == "at+jwt"
        assert "iat" in payload
        assert "exp" in payload

    def test_create_access_token_with_federated_claims(self, token_service: TokenService) -> None:
        """Test that access token correctly includes federated auth claims."""
        user_id = uuid4()
        token = token_service.create_access_token(
            subject_id=user_id,
            username="oidc-user",
            email="oidc@example.com",
            amr=["fed", "mfa"],
            idp="azure-ad-prod",
        )

        payload = jwt.decode(token, options={"verify_signature": False, "verify_aud": False})
        assert payload["amr"] == ["fed", "mfa"]
        assert payload["idp"] == "azure-ad-prod"

    def test_create_access_token_with_groups(self, token_service: TokenService) -> None:
        """Test that access token includes groups when provided."""
        user_id = uuid4()
        token = token_service.create_access_token(
            subject_id=user_id,
            username="test-user",
            email="test@example.com",
            groups=["engineering", "admins"],
        )

        payload = jwt.decode(token, options={"verify_signature": False, "verify_aud": False})
        assert payload["groups"] == ["engineering", "admins"]

    def test_create_access_token_with_first_and_last_name(self, token_service: TokenService) -> None:
        """Test that access token includes given_name, family_name, and computed name."""
        user_id = uuid4()
        token = token_service.create_access_token(
            subject_id=user_id,
            username="alice",
            email="alice@example.com",
            first_name="Alice",
            last_name="Smith",
        )

        payload = jwt.decode(token, options={"verify_signature": False, "verify_aud": False})
        assert payload["given_name"] == "Alice"
        assert payload["family_name"] == "Smith"
        assert payload["name"] == "Alice Smith"

    def test_create_access_token_with_first_name_only(self, token_service: TokenService) -> None:
        """Test that access token omits family_name when last_name is not provided."""
        user_id = uuid4()
        token = token_service.create_access_token(
            subject_id=user_id,
            username="alice",
            email="alice@example.com",
            first_name="Alice",
        )

        payload = jwt.decode(token, options={"verify_signature": False, "verify_aud": False})
        assert payload["given_name"] == "Alice"
        assert payload["name"] == "Alice"
        assert "family_name" not in payload

    def test_create_access_token_has_correct_expiry(self, token_service: TokenService) -> None:
        """Test that access token expires after configured lifetime."""
        user_id = uuid4()
        before = datetime.now(UTC)

        token = token_service.create_access_token(
            subject_id=user_id,
            username="test/user",
            email="test@example.com",
        )

        after = datetime.now(UTC)
        payload = jwt.decode(token, options={"verify_signature": False})

        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        iat = datetime.fromtimestamp(payload["iat"], tz=UTC)

        # Token should be issued within a reasonable window (allow 1 second tolerance)
        # JWT timestamps are integer seconds, so we need to account for truncation
        assert before.replace(microsecond=0) <= iat <= after + timedelta(seconds=1)

        # Expiry should be 15 minutes after issue (configured value)
        expected_exp_min = before.replace(microsecond=0) + timedelta(minutes=15)
        expected_exp_max = after + timedelta(minutes=15, seconds=1)
        assert expected_exp_min <= exp <= expected_exp_max

    def test_create_access_token_includes_kid_header(self, token_service: TokenService) -> None:
        """Test that access token includes key ID in header."""
        token = token_service.create_access_token(
            subject_id=uuid4(),
            username="test/user",
            email="test@example.com",
        )

        header = jwt.get_unverified_header(token)
        assert header["kid"] == "test-key"
        assert header["alg"] == "ES256"

    def test_create_refresh_token_returns_tuple(self, token_service: TokenService) -> None:
        """Test that create_refresh_token returns (token, jti, expiry) tuple."""
        user_id = uuid4()
        result = token_service.create_refresh_token(user_id=user_id)

        assert isinstance(result, tuple)
        assert len(result) == 3

        token, jti, expires_at = result
        assert isinstance(token, str)
        assert isinstance(jti, str)
        assert isinstance(expires_at, datetime)

    def test_create_refresh_token_contains_correct_claims(self, token_service: TokenService) -> None:
        """Test that refresh token contains required claims."""
        user_id = uuid4()
        token, jti, _exp = token_service.create_refresh_token(user_id=user_id)

        payload = jwt.decode(token, options={"verify_signature": False})

        assert payload["sub"] == str(user_id)
        assert payload["jti"] == jti
        assert payload["typ"] == "refresh"
        assert payload["iss"] == "https://localhost:8000"
        assert payload["aud"] == "orchestrator-api"
        assert "iat" in payload
        assert "exp" in payload
        # Refresh tokens should NOT have user profile claims
        assert "email" not in payload
        assert "preferred_username" not in payload
        assert "groups" not in payload
        assert "amr" not in payload
        assert "idp" not in payload

    def test_create_refresh_token_has_correct_expiry(self, token_service: TokenService) -> None:
        """Test that refresh token expires after configured lifetime."""
        user_id = uuid4()
        before = datetime.now(UTC)

        token, _jti, expires_at = token_service.create_refresh_token(user_id=user_id)

        after = datetime.now(UTC)
        payload = jwt.decode(token, options={"verify_signature": False})

        exp_from_payload = datetime.fromtimestamp(payload["exp"], tz=UTC)

        # Returned expiry should match token expiry
        assert abs((exp_from_payload - expires_at).total_seconds()) < 1

        # Expiry should be 8 hours after issue (configured value)
        expected_exp_min = before + timedelta(hours=8)
        expected_exp_max = after + timedelta(hours=8)
        assert expected_exp_min <= expires_at <= expected_exp_max

    def test_refresh_token_jti_is_unique(self, token_service: TokenService) -> None:
        """Test that each refresh token has a unique JTI."""
        user_id = uuid4()

        _, jti1, _ = token_service.create_refresh_token(user_id=user_id)
        _, jti2, _ = token_service.create_refresh_token(user_id=user_id)

        assert jti1 != jti2


class TestTokenValidation:
    """Tests for token validation."""

    def test_decode_valid_access_token(self, token_service: TokenService) -> None:
        """Test that a valid access token can be decoded."""
        user_id = uuid4()
        token = token_service.create_access_token(
            subject_id=user_id,
            username="testuser",
            email="test@example.com",
        )

        payload = token_service.decode_token(token, token_type="access")  # noqa: S106

        assert isinstance(payload, TokenPayload)
        assert payload.sub == str(user_id)
        assert payload.email == "test@example.com"
        assert payload.preferred_username == "testuser"
        assert payload.groups == []
        assert payload.amr == ["pwd"]
        assert payload.idp == "local"
        assert payload.token_type == "access"  # noqa: S105
        assert payload.iss == "https://localhost:8000"
        assert payload.aud == "orchestrator-api"
        assert payload.jti is None  # Access tokens don't have JTI

    def test_decode_valid_refresh_token(self, token_service: TokenService) -> None:
        """Test that a valid refresh token can be decoded."""
        user_id = uuid4()
        token, jti, _exp = token_service.create_refresh_token(user_id=user_id)

        payload = token_service.decode_token(token, token_type="refresh")  # noqa: S106

        assert isinstance(payload, TokenPayload)
        assert payload.sub == str(user_id)
        assert payload.jti == jti
        assert payload.token_type == "refresh"  # noqa: S105
        assert payload.iss == "https://localhost:8000"

    def test_decode_token_wrong_type_raises_error(self, token_service: TokenService) -> None:
        """Test that decoding with wrong token type raises InvalidTokenError."""
        user_id = uuid4()
        access_token = token_service.create_access_token(
            subject_id=user_id,
            username="test/user",
            email="test@example.com",
        )

        with pytest.raises(InvalidTokenError):
            token_service.decode_token(access_token, token_type="refresh")  # noqa: S106

    def test_decode_token_invalid_signature_raises_error(self, token_service: TokenService) -> None:
        """Test that a token with invalid signature raises InvalidTokenError."""
        user_id = uuid4()
        token = token_service.create_access_token(
            subject_id=user_id,
            username="test/user",
            email="test@example.com",
        )

        # Tamper with the token by modifying the signature
        parts = token.split(".")
        parts[2] = parts[2][:-5] + "XXXXX"  # Corrupt signature
        tampered_token = ".".join(parts)

        with pytest.raises(InvalidTokenError):
            token_service.decode_token(tampered_token, token_type="access")  # noqa: S106

    def test_decode_token_wrong_issuer_raises_error(self, token_service: TokenService) -> None:
        """Test that a token with wrong issuer raises InvalidTokenError."""
        # Create a token with a different issuer using raw JWT
        key_manager = token_service._key_manager
        payload = {
            "sub": str(uuid4()),
            "iss": "wrong-issuer",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "aud": "orchestrator-api",
        }
        token = jwt.encode(
            payload,
            key_manager.get_private_key(),
            algorithm="ES256",
            headers={"kid": key_manager.key_id, "typ": "at+jwt"},
        )

        with pytest.raises(InvalidTokenError):
            token_service.decode_token(token, token_type="access")  # noqa: S106

    def test_decode_token_wrong_kid_raises_error(self, token_service: TokenService) -> None:
        """Test that a token with unknown key ID raises InvalidTokenError."""
        key_manager = token_service._key_manager
        payload = {
            "sub": str(uuid4()),
            "iss": "https://localhost:8000",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "aud": "orchestrator-api",
        }
        token = jwt.encode(
            payload,
            key_manager.get_private_key(),
            algorithm="ES256",
            headers={"kid": "unknown-key-id"},
        )

        with pytest.raises(InvalidTokenError):
            token_service.decode_token(token, token_type="access")  # noqa: S106

    def test_decode_malformed_token_raises_error(self, token_service: TokenService) -> None:
        """Test that a malformed token raises InvalidTokenError."""
        with pytest.raises(InvalidTokenError):
            token_service.decode_token("not.a.valid.jwt", token_type="access")  # noqa: S106

    def test_decode_token_missing_claims_raises_error(self, token_service: TokenService) -> None:
        """Test that a token missing required claims raises InvalidTokenError."""
        key_manager = token_service._key_manager
        # Missing 'sub' claim
        payload = {
            "iss": "https://localhost:8000",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "aud": "orchestrator-api",
        }
        token = jwt.encode(
            payload,
            key_manager.get_private_key(),
            algorithm="ES256",
            headers={"kid": key_manager.key_id, "typ": "at+jwt"},
        )

        with pytest.raises(InvalidTokenError):
            token_service.decode_token(token, token_type="access")  # noqa: S106


class TestTokenExpiry:
    """Tests for token expiry handling."""

    def test_decode_expired_token_raises_error(self, token_service: TokenService) -> None:
        """Test that an expired token raises TokenExpiredError."""
        key_manager = token_service._key_manager
        # Create a token that expired 1 hour ago
        payload = {
            "sub": str(uuid4()),
            "iss": "https://localhost:8000",
            "iat": datetime.now(UTC) - timedelta(hours=2),
            "exp": datetime.now(UTC) - timedelta(hours=1),
            "aud": "orchestrator-api",
        }
        token = jwt.encode(
            payload,
            key_manager.get_private_key(),
            algorithm="ES256",
            headers={"kid": key_manager.key_id, "typ": "at+jwt"},
        )

        with pytest.raises(TokenExpiredError):
            token_service.decode_token(token, token_type="access")  # noqa: S106

    def test_token_valid_just_before_expiry(self, token_service: TokenService) -> None:
        """Test that a token is valid just before expiry."""
        key_manager = token_service._key_manager
        # Create a token that expires in 10 seconds
        payload = {
            "sub": str(uuid4()),
            "email": "test@example.com",
            "preferred_username": "test-user",
            "iss": "https://localhost:8000",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(seconds=10),
            "aud": "orchestrator-api",
        }
        token = jwt.encode(
            payload,
            key_manager.get_private_key(),
            algorithm="ES256",
            headers={"kid": key_manager.key_id, "typ": "at+jwt"},
        )

        # Should not raise
        result = token_service.decode_token(token, token_type="access")  # noqa: S106
        assert result.token_type == "access"  # noqa: S105

    def test_token_invalid_just_after_expiry(self, token_service: TokenService) -> None:
        """Test that a token is invalid just after expiry."""
        key_manager = token_service._key_manager
        # Create a token that expired 1 second ago
        payload = {
            "sub": str(uuid4()),
            "iss": "https://localhost:8000",
            "iat": datetime.now(UTC) - timedelta(seconds=10),
            "exp": datetime.now(UTC) - timedelta(seconds=1),
            "aud": "orchestrator-api",
        }
        token = jwt.encode(
            payload,
            key_manager.get_private_key(),
            algorithm="ES256",
            headers={"kid": key_manager.key_id, "typ": "at+jwt"},
        )

        with pytest.raises(TokenExpiredError):
            token_service.decode_token(token, token_type="access")  # noqa: S106


class TestAlgorithmEnforcement:
    """Tests for algorithm enforcement (ES256)."""

    def test_token_uses_es256_algorithm(self, token_service: TokenService) -> None:
        """Test that created tokens use ES256 algorithm."""
        token = token_service.create_access_token(
            subject_id=uuid4(),
            username="test/user",
            email="test@example.com",
        )

        header = jwt.get_unverified_header(token)
        assert header["alg"] == "ES256"

    def test_reject_token_with_none_algorithm(self, token_service: TokenService) -> None:
        """Test that tokens with 'none' algorithm are rejected."""
        # Create a token with 'none' algorithm (algorithm confusion attack)
        payload = {
            "sub": str(uuid4()),
            "iss": "https://localhost:8000",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "aud": "orchestrator-api",
        }
        # Manually construct a token with 'none' algorithm
        import base64
        import json

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "typ": "at+jwt", "kid": "test-key"}).encode()
        ).rstrip(b"=")
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload, default=str).encode()).rstrip(b"=")
        token = f"{header.decode()}.{payload_b64.decode()}."

        with pytest.raises(InvalidTokenError):
            token_service.decode_token(token, token_type="access")  # noqa: S106

    def test_reject_token_with_hs256_algorithm(self, token_service: TokenService) -> None:
        """Test that tokens signed with HS256 are rejected.

        This tests protection against algorithm substitution attacks where
        an attacker tries to use a symmetric key with HMAC.
        """
        key_manager = token_service._key_manager

        payload = {
            "sub": str(uuid4()),
            "iss": "https://localhost:8000",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "aud": "orchestrator-api",
        }

        # Create a token with HS256 using an arbitrary secret
        token = jwt.encode(
            payload,
            "arbitrary-secret-key",
            algorithm="HS256",
            headers={"kid": key_manager.key_id, "typ": "at+jwt"},
        )

        # Should reject because we only accept ES256
        with pytest.raises(InvalidTokenError):
            token_service.decode_token(token, token_type="access")  # noqa: S106

    def test_key_is_p256_curve(self, token_service: TokenService) -> None:
        """Test that the generated key uses P-256 curve (required for ES256)."""
        key_manager = token_service._key_manager
        private_key = key_manager.get_private_key()

        # Check curve name
        curve = private_key.curve
        assert curve.name == "secp256r1"  # P-256 curve


class TestKeyRotation:
    """Tests for key rotation with backup keys."""

    def test_backup_keys_not_loaded_when_none_configured(self) -> None:
        """Test that backup keys loading succeeds when none are configured."""
        with patch("syntara.auth.services.token_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                jwt_private_key_path=None,
                jwt_private_key_base64=None,
                jwt_key_id="test-key",
                jwt_backup_keys=None,
            )
            key_manager = KeyManager()
            key_manager._load_backup_keys()

            assert key_manager._backup_keys == {}
            assert key_manager._backup_keys_loaded is True

    def test_get_public_key_for_kid_returns_primary_key(self) -> None:
        """Test that get_public_key_for_kid returns the primary key for its ID."""
        with patch("syntara.auth.services.token_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                jwt_private_key_path=None,
                jwt_private_key_base64=None,
                jwt_key_id="primary-key",
                jwt_backup_keys=None,
            )
            key_manager = KeyManager()
            key_manager._private_key = ec.generate_private_key(ec.SECP256R1())
            public_key_pem = key_manager.get_public_key_for_kid("primary-key")

            assert public_key_pem is not None
            assert public_key_pem.startswith(b"-----BEGIN PUBLIC KEY-----")

    def test_get_public_key_for_kid_returns_none_for_unknown(self) -> None:
        """Test that get_public_key_for_kid returns None for unknown key ID."""
        with patch("syntara.auth.services.token_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                jwt_private_key_path=None,
                jwt_private_key_base64=None,
                jwt_key_id="primary-key",
                jwt_backup_keys=None,
            )
            key_manager = KeyManager()
            public_key_pem = key_manager.get_public_key_for_kid("unknown-key")

            assert public_key_pem is None

    def test_get_all_key_ids_returns_primary_when_no_backups(self) -> None:
        """Test that get_all_key_ids returns only primary key when no backups."""
        with patch("syntara.auth.services.token_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                jwt_private_key_path=None,
                jwt_private_key_base64=None,
                jwt_key_id="primary-key",
                jwt_backup_keys=None,
            )
            key_manager = KeyManager()
            key_ids = key_manager.get_all_key_ids()

            assert key_ids == ["primary-key"]

    def test_backup_key_skipped_when_missing_key_id(self) -> None:
        """Test that backup key config without key_id is skipped."""
        with patch("syntara.auth.services.token_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                jwt_private_key_path=None,
                jwt_private_key_base64=None,
                jwt_key_id="primary-key",
                jwt_backup_keys=[{"key_base64": "somevalue"}],  # Missing key_id
            )
            key_manager = KeyManager()
            key_manager._load_backup_keys()

            assert key_manager._backup_keys == {}

    def test_backup_key_skipped_when_same_as_primary(self) -> None:
        """Test that backup key with same ID as primary is skipped."""
        with patch("syntara.auth.services.token_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                jwt_private_key_path=None,
                jwt_private_key_base64=None,
                jwt_key_id="primary-key",
                jwt_backup_keys=[{"key_id": "primary-key", "key_base64": "somevalue"}],
            )
            key_manager = KeyManager()
            key_manager._load_backup_keys()

            assert "primary-key" not in key_manager._backup_keys

    def test_backup_key_skipped_when_missing_key_data(self) -> None:
        """Test that backup key config without key_path or key_base64 is skipped."""
        with patch("syntara.auth.services.token_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                jwt_private_key_path=None,
                jwt_private_key_base64=None,
                jwt_key_id="primary-key",
                jwt_backup_keys=[{"key_id": "backup-key"}],  # Missing key data
            )
            key_manager = KeyManager()
            key_manager._load_backup_keys()

            assert key_manager._backup_keys == {}

    def test_jwks_includes_only_primary_when_no_backups(self) -> None:
        """Test that JWKS includes only primary key when no backups configured."""
        with patch("syntara.auth.services.token_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                jwt_private_key_path=None,
                jwt_private_key_base64=None,
                jwt_key_id="primary-key",
                jwt_backup_keys=None,
            )
            key_manager = KeyManager()
            key_manager._private_key = ec.generate_private_key(ec.SECP256R1())
            jwks = key_manager.get_jwks()

            assert len(jwks["keys"]) == 1
            assert jwks["keys"][0]["kid"] == "primary-key"

    def test_token_with_backup_key_can_be_verified(self) -> None:
        """Test that tokens signed with backup key can be verified.

        This tests the key rotation scenario where:
        1. A token was signed with a previous (now backup) key
        2. The server now has a new primary key
        3. The old token should still be verifiable using the backup key
        """
        import base64

        # Generate two different keys (simulating primary and backup)
        primary_key = ec.generate_private_key(ec.SECP256R1())
        backup_key = ec.generate_private_key(ec.SECP256R1())

        # Encode backup key to base64 for settings
        backup_key_pem = backup_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        backup_key_base64 = base64.b64encode(backup_key_pem).decode("ascii")

        # Create a token signed with the backup key (as if it was the old primary)
        backup_payload = {
            "sub": str(uuid4()),
            "email": "test@example.com",
            "preferred_username": "test-user",
            "aud": "orchestrator-api",
            "iss": "https://localhost:8000",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(hours=1),
        }
        token_with_backup_key = jwt.encode(
            backup_payload,
            backup_key,
            algorithm="ES256",
            headers={"kid": "backup-key-id", "typ": "at+jwt"},
        )

        # Set up settings with new primary key and the backup key
        with patch("syntara.auth.services.token_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                jwt_private_key_path=None,
                jwt_private_key_base64=None,
                jwt_key_id="new-primary-key",
                jwt_backup_keys=[
                    {"key_id": "backup-key-id", "key_base64": backup_key_base64},
                ],
                jwt_issuer="https://localhost:8000",
                jwt_access_token_lifetime_minutes=15,
                jwt_refresh_token_lifetime_hours=8,
            )

            # Create a fresh KeyManager that will use our mocked settings
            key_manager = KeyManager()

            # Manually set the primary key to our generated one
            # (since we can't use the mocked settings for the primary key loading)
            key_manager._private_key = primary_key
            key_manager._public_key_pem = None  # Reset to force recalculation

            # Create TokenService with our key manager
            token_service = TokenService(key_manager=key_manager)

            # Verify the token signed with backup key can be decoded
            payload = token_service.decode_token(token_with_backup_key, token_type="access")  # noqa: S106

            assert payload.sub == backup_payload["sub"]
            assert payload.email == "test@example.com"
            assert payload.preferred_username == "test-user"
            assert payload.token_type == "access"  # noqa: S105

    def test_jwks_includes_backup_keys(self) -> None:
        """Test that JWKS includes both primary and backup keys."""
        import base64

        # Generate a backup key
        backup_key = ec.generate_private_key(ec.SECP256R1())
        backup_key_pem = backup_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        backup_key_base64 = base64.b64encode(backup_key_pem).decode("ascii")

        with patch("syntara.auth.services.token_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                jwt_private_key_path=None,
                jwt_private_key_base64=None,
                jwt_key_id="primary-key",
                jwt_backup_keys=[
                    {"key_id": "backup-key-1", "key_base64": backup_key_base64},
                ],
            )
            key_manager = KeyManager()
            key_manager._private_key = ec.generate_private_key(ec.SECP256R1())
            jwks = key_manager.get_jwks()

            assert len(jwks["keys"]) == 2

            key_ids = {k["kid"] for k in jwks["keys"]}
            assert key_ids == {"primary-key", "backup-key-1"}

            # Verify all keys have correct structure
            for key in jwks["keys"]:
                assert key["kty"] == "EC"
                assert key["use"] == "sig"
                assert key["alg"] == "ES256"
                assert key["crv"] == "P-256"
                assert "x" in key
                assert "y" in key


class TestTokenVersionClaim:
    """Tests for token_ver claim in access tokens."""

    def test_access_token_includes_token_ver_default(self, token_service: TokenService) -> None:
        """Test that token_ver claim is included in access token with default value 0."""
        user_id = uuid4()
        token = token_service.create_access_token(
            subject_id=user_id,
            username="testuser",
            email="test@example.com",
        )

        payload = jwt.decode(token, options={"verify_signature": False, "verify_aud": False})
        assert payload["token_ver"] == 0

    def test_access_token_includes_token_ver_custom(self, token_service: TokenService) -> None:
        """Test that token_ver claim has custom value when passed."""
        user_id = uuid4()
        token = token_service.create_access_token(
            subject_id=user_id,
            username="testuser",
            email="test@example.com",
            token_version=42,
        )

        payload = jwt.decode(token, options={"verify_signature": False, "verify_aud": False})
        assert payload["token_ver"] == 42

    def test_decode_token_returns_token_version(self, token_service: TokenService) -> None:
        """Test that token_version is decoded from token payload."""
        user_id = uuid4()
        token = token_service.create_access_token(
            subject_id=user_id,
            username="testuser",
            email="test@example.com",
            token_version=7,
        )

        payload = token_service.decode_token(token, token_type="access")  # noqa: S106

        assert isinstance(payload, TokenPayload)
        assert payload.token_version == 7


class TestCacheInvalidation:
    """Tests for KeyManager and TokenService cache invalidation (AAP-71275)."""

    def test_get_key_manager_returns_same_instance(self) -> None:
        """Successive calls should return the same cached KeyManager."""
        clear_key_manager_cache()
        try:
            km1 = get_key_manager()
            km2 = get_key_manager()
            assert km1 is km2
        finally:
            clear_key_manager_cache()

    def test_clear_key_manager_cache_forces_new_instance(self) -> None:
        """Clearing the cache should produce a new KeyManager on next call."""
        clear_key_manager_cache()
        try:
            km1 = get_key_manager()
            clear_key_manager_cache()
            km2 = get_key_manager()
            assert km1 is not km2
        finally:
            clear_key_manager_cache()

    def test_clear_token_service_cache_forces_new_instance(self) -> None:
        """Clearing the cache should produce a new TokenService on next call."""
        from syntara.auth.dependencies import _get_token_service, clear_token_service_cache

        clear_token_service_cache()
        clear_key_manager_cache()
        try:
            ts1 = _get_token_service()
            clear_token_service_cache()
            clear_key_manager_cache()
            ts2 = _get_token_service()
            assert ts1 is not ts2
        finally:
            clear_token_service_cache()
            clear_key_manager_cache()
