# Generated with AI assistance: Claude Code (Anthropic)
"""Unit tests for the OAuth 2.0 client credentials grant endpoint."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.auth.passwords import hash_password
from syntara.auth.router import _extract_basic_credentials, token
from syntara.auth.schemas import AccessTokenResponse
from syntara.auth.services.token_service import TokenService
from syntara.core.models.principal import PrincipalType
from syntara.service_accounts.models.service_account import ServiceAccount, ServiceAccountStatus
from syntara.service_accounts.models.service_account_credential import (
    ServiceAccountCredential,
    ServiceAccountCredentialStatus,
    ServiceAccountCredentialType,
)


def _make_sa_and_credential(
    *,
    client_id: str = "nx_sa_abc123",
    secret: str = "test-secret",  # noqa: S107
    sa_status: ServiceAccountStatus = ServiceAccountStatus.ACTIVE,
    cred_status: ServiceAccountCredentialStatus = ServiceAccountCredentialStatus.ACTIVE,
    old_hashed_secret: str | None = None,
    old_secret_valid_until: datetime | None = None,
) -> tuple[ServiceAccountCredential, ServiceAccount, str]:
    """Create a ServiceAccount + Credential pair with a known plaintext secret."""
    hashed = hash_password(secret)
    sa_id = uuid4()
    sa = ServiceAccount(
        id=sa_id,
        name="test-sa",
        status=sa_status,
        project_id=uuid4(),
        created_by=uuid4(),
        updated_by=uuid4(),
    )

    credential = ServiceAccountCredential(
        id=uuid4(),
        service_account_id=sa_id,
        credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
        identifier=client_id,
        hashed_secret=hashed,
        status=cred_status,
        old_hashed_secret=old_hashed_secret,
        old_secret_valid_until=old_secret_valid_until,
        created_by=sa.created_by,
        updated_by=sa.updated_by,
    )
    return credential, sa, secret


def _mock_request(*, basic_auth: tuple[str, str] | None = None) -> MagicMock:
    """Create a mock FastAPI Request."""
    req = MagicMock()
    if basic_auth:
        creds = base64.b64encode(f"{basic_auth[0]}:{basic_auth[1]}".encode()).decode()
        req.headers = {"Authorization": f"Basic {creds}"}
    else:
        req.headers = {}
    return req


class TestExtractBasicCredentials:
    """Tests for _extract_basic_credentials helper."""

    def test_valid_basic_header(self) -> None:
        req = _mock_request(basic_auth=("my_id", "my_secret"))
        result = _extract_basic_credentials(req)
        assert result == ("my_id", "my_secret")

    def test_no_auth_header(self) -> None:
        req = _mock_request()
        assert _extract_basic_credentials(req) is None

    def test_bearer_header_ignored(self) -> None:
        req = MagicMock()
        req.headers = {"Authorization": "Bearer some-token"}
        assert _extract_basic_credentials(req) is None

    def test_invalid_base64(self) -> None:
        req = MagicMock()
        req.headers = {"Authorization": "Basic !!!invalid!!!"}
        assert _extract_basic_credentials(req) is None

    def test_missing_colon(self) -> None:
        encoded = base64.b64encode(b"no-colon-here").decode()
        req = MagicMock()
        req.headers = {"Authorization": f"Basic {encoded}"}
        assert _extract_basic_credentials(req) is None

    def test_colon_in_secret(self) -> None:
        req = _mock_request(basic_auth=("id", "secret:with:colons"))
        result = _extract_basic_credentials(req)
        assert result == ("id", "secret:with:colons")


class TestTokenEndpoint:
    """Tests for POST /auth/token."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        settings = MagicMock()
        settings.jwt_sa_access_token_lifetime_minutes = 15
        settings.jwt_issuer = "https://orchestrator.test"
        return settings

    def _setup_db_result(
        self,
        db: AsyncMock,
        row: tuple[ServiceAccountCredential, ServiceAccount] | None,
    ) -> None:
        """Wire the mock db.exec to return the credential+SA join result."""
        result_mock = MagicMock()
        result_mock.one_or_none.return_value = row
        db.exec = AsyncMock(return_value=result_mock)

    @pytest.mark.asyncio
    async def test_valid_credentials_form_body(self, mock_db: AsyncMock, mock_settings: MagicMock) -> None:
        """AC1, AC3: Valid client_credentials via form body returns access token."""
        cred, sa, secret = _make_sa_and_credential()
        self._setup_db_result(mock_db, (cred, sa))

        req = _mock_request()
        with (
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router._get_token_service") as mock_ts,
            patch("syntara.auth.router.AuditEventDispatcher"),
        ):
            mock_ts.return_value.create_access_token.return_value = "jwt.token.here"
            response = await token(
                request=req,
                db=mock_db,
                grant_type="client_credentials",
                client_id=cred.identifier,
                client_secret=secret,
            )

        assert isinstance(response, AccessTokenResponse)
        assert response.access_token == "jwt.token.here"  # noqa: S105
        assert response.token_type == "Bearer"  # noqa: S105
        assert response.expires_in == 15 * 60

    @pytest.mark.asyncio
    async def test_valid_credentials_basic_auth(self, mock_db: AsyncMock, mock_settings: MagicMock) -> None:
        """AC2: Valid credentials via HTTP Basic auth header."""
        cred, sa, secret = _make_sa_and_credential()
        self._setup_db_result(mock_db, (cred, sa))

        req = _mock_request(basic_auth=(cred.identifier, secret))
        with (
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router._get_token_service") as mock_ts,
            patch("syntara.auth.router.AuditEventDispatcher"),
        ):
            mock_ts.return_value.create_access_token.return_value = "jwt.token.here"
            response = await token(
                request=req,
                db=mock_db,
                grant_type="client_credentials",
                client_id="",
                client_secret="",
            )

        assert response.access_token == "jwt.token.here"  # noqa: S105

    @pytest.mark.asyncio
    async def test_creates_sa_token_with_principal_type(self, mock_db: AsyncMock, mock_settings: MagicMock) -> None:
        """AC4, AC12: TokenService.create_access_token called with principal_type='service_account'."""
        cred, sa, secret = _make_sa_and_credential()
        self._setup_db_result(mock_db, (cred, sa))

        req = _mock_request()
        with (
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router._get_token_service") as mock_ts,
            patch("syntara.auth.router.AuditEventDispatcher"),
        ):
            mock_ts.return_value.create_access_token.return_value = "jwt"
            await token(
                request=req,
                db=mock_db,
                grant_type="client_credentials",
                client_id=cred.identifier,
                client_secret=secret,
            )

        mock_ts.return_value.create_access_token.assert_called_once_with(
            subject_id=sa.id,
            username=sa.name,
            token_version=sa.token_version,
            credential_id=cred.id,
            principal_type=PrincipalType.SERVICE_ACCOUNT,
        )

    @pytest.mark.asyncio
    async def test_invalid_client_id_returns_401(self, mock_db: AsyncMock) -> None:
        """AC5: Unknown client_id returns 401."""
        self._setup_db_result(mock_db, None)

        req = _mock_request()
        with (
            patch("syntara.auth.router.AuditEventDispatcher"),
            pytest.raises(Exception) as exc_info,
        ):
            await token(
                request=req,
                db=mock_db,
                grant_type="client_credentials",
                client_id="nonexistent",
                client_secret="any",  # noqa: S106
            )

        from syntara.auth.exceptions import AuthenticationRequiredError

        assert isinstance(exc_info.value, AuthenticationRequiredError)

    @pytest.mark.asyncio
    async def test_invalid_client_secret_returns_401(self, mock_db: AsyncMock) -> None:
        """AC6: Wrong client_secret returns 401."""
        cred, sa, _ = _make_sa_and_credential()
        self._setup_db_result(mock_db, (cred, sa))

        req = _mock_request()
        with (
            patch("syntara.auth.router.AuditEventDispatcher"),
            pytest.raises(Exception) as exc_info,
        ):
            await token(
                request=req,
                db=mock_db,
                grant_type="client_credentials",
                client_id=cred.identifier,
                client_secret="wrong-secret",  # noqa: S106
            )

        from syntara.auth.exceptions import AuthenticationRequiredError

        assert isinstance(exc_info.value, AuthenticationRequiredError)

    @pytest.mark.asyncio
    async def test_disabled_service_account_returns_401(self, mock_db: AsyncMock) -> None:
        """AC7: Disabled service account returns 401."""
        cred, sa, secret = _make_sa_and_credential(sa_status=ServiceAccountStatus.DISABLED)
        self._setup_db_result(mock_db, (cred, sa))

        req = _mock_request()
        with (
            patch("syntara.auth.router.AuditEventDispatcher"),
            pytest.raises(Exception) as exc_info,
        ):
            await token(
                request=req,
                db=mock_db,
                grant_type="client_credentials",
                client_id=cred.identifier,
                client_secret=secret,
            )

        from syntara.auth.exceptions import AuthenticationRequiredError

        assert isinstance(exc_info.value, AuthenticationRequiredError)

    @pytest.mark.asyncio
    async def test_deleted_service_account_returns_401(self, mock_db: AsyncMock) -> None:
        """AC8: Hard-deleted service account (credential gone) returns 401."""
        self._setup_db_result(mock_db, None)

        req = _mock_request()
        with (
            patch("syntara.auth.router.AuditEventDispatcher"),
            pytest.raises(Exception) as exc_info,
        ):
            await token(
                request=req,
                db=mock_db,
                grant_type="client_credentials",
                client_id="nx_sa_deleted",
                client_secret="any-secret",  # noqa: S106
            )

        from syntara.auth.exceptions import AuthenticationRequiredError

        assert isinstance(exc_info.value, AuthenticationRequiredError)

    @pytest.mark.asyncio
    async def test_builtin_admin_not_eligible(self, mock_db: AsyncMock) -> None:
        """AC9: Built-in admin has no credential, so identifier lookup returns 401."""
        self._setup_db_result(mock_db, None)

        req = _mock_request()
        with (
            patch("syntara.auth.router.AuditEventDispatcher"),
            pytest.raises(Exception) as exc_info,
        ):
            await token(
                request=req,
                db=mock_db,
                grant_type="client_credentials",
                client_id="admin",
                client_secret="admin-password",  # noqa: S106
            )

        from syntara.auth.exceptions import AuthenticationRequiredError

        assert isinstance(exc_info.value, AuthenticationRequiredError)

    @pytest.mark.asyncio
    async def test_no_refresh_token_issued(self, mock_db: AsyncMock, mock_settings: MagicMock) -> None:
        """AC10: Response has no refresh token."""
        cred, sa, secret = _make_sa_and_credential()
        self._setup_db_result(mock_db, (cred, sa))

        req = _mock_request()
        with (
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router._get_token_service") as mock_ts,
            patch("syntara.auth.router.AuditEventDispatcher"),
        ):
            mock_ts.return_value.create_access_token.return_value = "jwt"
            mock_ts.return_value.create_refresh_token = MagicMock()
            response = await token(
                request=req,
                db=mock_db,
                grant_type="client_credentials",
                client_id=cred.identifier,
                client_secret=secret,
            )

        mock_ts.return_value.create_refresh_token.assert_not_called()
        assert not hasattr(response, "refresh_token")

    @pytest.mark.asyncio
    async def test_sa_lifetime_independent(self, mock_db: AsyncMock) -> None:
        """AC11: SA token lifetime uses jwt_sa_access_token_lifetime_minutes."""
        cred, sa, secret = _make_sa_and_credential()
        self._setup_db_result(mock_db, (cred, sa))

        settings = MagicMock()
        settings.jwt_sa_access_token_lifetime_minutes = 30
        settings.jwt_access_token_lifetime_minutes = 15

        req = _mock_request()
        with (
            patch("syntara.auth.router.get_settings", return_value=settings),
            patch("syntara.auth.router._get_token_service") as mock_ts,
            patch("syntara.auth.router.AuditEventDispatcher"),
        ):
            mock_ts.return_value.create_access_token.return_value = "jwt"
            response = await token(
                request=req,
                db=mock_db,
                grant_type="client_credentials",
                client_id=cred.identifier,
                client_secret=secret,
            )

        assert response.expires_in == 30 * 60

    @pytest.mark.asyncio
    async def test_unsupported_grant_type_returns_400(self, mock_db: AsyncMock) -> None:
        """grant_type != 'client_credentials' returns 400."""
        from fastapi import HTTPException

        req = _mock_request()
        with pytest.raises(HTTPException) as exc_info:
            await token(
                request=req,
                db=mock_db,
                grant_type="authorization_code",
                client_id="any",
                client_secret="any",  # noqa: S106
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_credentials_returns_401(self, mock_db: AsyncMock) -> None:
        """No credentials in header or body returns 401."""
        req = _mock_request()
        with (
            patch("syntara.auth.router.AuditEventDispatcher"),
            pytest.raises(Exception) as exc_info,
        ):
            await token(
                request=req,
                db=mock_db,
                grant_type="client_credentials",
                client_id="",
                client_secret="",
            )

        from syntara.auth.exceptions import AuthenticationRequiredError

        assert isinstance(exc_info.value, AuthenticationRequiredError)

    @pytest.mark.asyncio
    async def test_updates_last_authenticated_at(self, mock_db: AsyncMock, mock_settings: MagicMock) -> None:
        """Successful auth updates last_authenticated_at and last_used_at."""
        cred, sa, secret = _make_sa_and_credential()
        assert sa.last_authenticated_at is None
        assert cred.last_used_at is None
        self._setup_db_result(mock_db, (cred, sa))

        req = _mock_request()
        with (
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router._get_token_service") as mock_ts,
            patch("syntara.auth.router.AuditEventDispatcher"),
        ):
            mock_ts.return_value.create_access_token.return_value = "jwt"
            await token(
                request=req,
                db=mock_db,
                grant_type="client_credentials",
                client_id=cred.identifier,
                client_secret=secret,
            )

        assert sa.last_authenticated_at is not None
        assert cred.last_used_at is not None  # type: ignore[unreachable]

    @pytest.mark.asyncio
    async def test_token_sets_actor_context_for_timestamp_audit(
        self, mock_db: AsyncMock, mock_settings: MagicMock
    ) -> None:
        """Client-credentials token must attribute timestamp CRUD to the SA (AAP-83651).

        /auth/token has no Bearer JWT for audit middleware; without actor_context,
        last_authenticated_at / last_used_at CRUD events stay null-actor.
        """
        from syntara.audit.emitter import actor_context_var

        cred, sa, secret = _make_sa_and_credential()
        self._setup_db_result(mock_db, (cred, sa))

        seen_actor_id = None
        seen_username = None
        seen_actor_type = None

        async def _capture_commit() -> None:
            nonlocal seen_actor_id, seen_username, seen_actor_type
            actor = actor_context_var.get()
            assert actor is not None
            seen_actor_id = actor.actor_id
            seen_username = actor.actor_username
            seen_actor_type = actor.actor_type

        mock_db.commit.side_effect = _capture_commit

        req = _mock_request()
        with (
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router._get_token_service") as mock_ts,
            patch("syntara.auth.router.AuditEventDispatcher"),
        ):
            mock_ts.return_value.create_access_token.return_value = "jwt"
            await token(
                request=req,
                db=mock_db,
                grant_type="client_credentials",
                client_id=cred.identifier,
                client_secret=secret,
            )

        assert seen_actor_id == sa.id
        assert seen_username == sa.name
        assert seen_actor_type == PrincipalType.SERVICE_ACCOUNT

    @pytest.mark.asyncio
    async def test_disabled_credential_returns_401(self, mock_db: AsyncMock) -> None:
        """Disabled credential (independent of SA status) returns 401."""
        cred, sa, secret = _make_sa_and_credential(cred_status=ServiceAccountCredentialStatus.DISABLED)
        self._setup_db_result(mock_db, (cred, sa))

        req = _mock_request()
        with (
            patch("syntara.auth.router.AuditEventDispatcher"),
            pytest.raises(Exception) as exc_info,
        ):
            await token(
                request=req,
                db=mock_db,
                grant_type="client_credentials",
                client_id=cred.identifier,
                client_secret=secret,
            )

        from syntara.auth.exceptions import AuthenticationRequiredError

        assert isinstance(exc_info.value, AuthenticationRequiredError)

    @pytest.mark.asyncio
    async def test_old_secret_accepted_during_grace_period(self, mock_db: AsyncMock, mock_settings: MagicMock) -> None:
        """Old secret is accepted during rotation grace period."""
        old_secret = "old-secret-value"  # noqa: S105
        new_secret = "new-secret-value"  # noqa: S105
        cred, sa, _ = _make_sa_and_credential(
            secret=new_secret,
            old_hashed_secret=hash_password(old_secret),
            old_secret_valid_until=datetime.now(UTC) + timedelta(hours=1),
        )
        self._setup_db_result(mock_db, (cred, sa))

        req = _mock_request()
        with (
            patch("syntara.auth.router.get_settings", return_value=mock_settings),
            patch("syntara.auth.router._get_token_service") as mock_ts,
            patch("syntara.auth.router.AuditEventDispatcher"),
        ):
            mock_ts.return_value.create_access_token.return_value = "jwt"
            response = await token(
                request=req,
                db=mock_db,
                grant_type="client_credentials",
                client_id=cred.identifier,
                client_secret=old_secret,
            )

        assert response.access_token == "jwt"  # noqa: S105

    @pytest.mark.asyncio
    async def test_old_secret_rejected_after_grace_period(self, mock_db: AsyncMock) -> None:
        """Old secret is rejected after grace period expires."""
        old_secret = "old-secret-value"  # noqa: S105
        new_secret = "new-secret-value"  # noqa: S105
        cred, sa, _ = _make_sa_and_credential(
            secret=new_secret,
            old_hashed_secret=hash_password(old_secret),
            old_secret_valid_until=datetime.now(UTC) - timedelta(hours=1),
        )
        self._setup_db_result(mock_db, (cred, sa))

        req = _mock_request()
        with (
            patch("syntara.auth.router.AuditEventDispatcher"),
            pytest.raises(Exception) as exc_info,
        ):
            await token(
                request=req,
                db=mock_db,
                grant_type="client_credentials",
                client_id=cred.identifier,
                client_secret=old_secret,
            )

        from syntara.auth.exceptions import AuthenticationRequiredError

        assert isinstance(exc_info.value, AuthenticationRequiredError)

    @pytest.mark.asyncio
    async def test_expired_credential_returns_401(self, mock_db: AsyncMock) -> None:
        """Expired credential (expires_at in the past) returns 401."""
        cred, sa, secret = _make_sa_and_credential()
        cred.expires_at = datetime.now(UTC) - timedelta(hours=1)
        self._setup_db_result(mock_db, (cred, sa))

        req = _mock_request()
        with (
            patch("syntara.auth.router.AuditEventDispatcher"),
            pytest.raises(Exception) as exc_info,
        ):
            await token(
                request=req,
                db=mock_db,
                grant_type="client_credentials",
                client_id=cred.identifier,
                client_secret=secret,
            )

        from syntara.auth.exceptions import AuthenticationRequiredError

        assert isinstance(exc_info.value, AuthenticationRequiredError)


class TestTokenServiceExtension:
    """Tests for TokenService.create_access_token with principal_type='service_account'."""

    @pytest.fixture
    def token_service(self) -> TokenService:
        """Create a TokenService with mocked key manager."""
        from unittest.mock import PropertyMock

        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

        from syntara.auth.services.token_service import KeyManager

        key_manager = MagicMock(spec=KeyManager)
        private_key = ec.generate_private_key(ec.SECP256R1())
        key_manager.get_private_key.return_value = private_key
        public_pem = private_key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        key_manager.get_public_key_for_kid.return_value = public_pem
        type(key_manager).key_id = PropertyMock(return_value="test-key")

        settings = MagicMock()
        settings.jwt_access_token_lifetime_minutes = 15
        settings.jwt_sa_access_token_lifetime_minutes = 30
        settings.jwt_issuer = "https://orchestrator.test"

        with patch("syntara.auth.services.token_service.get_settings", return_value=settings):
            return TokenService(key_manager=key_manager)

    def test_sa_token_contains_service_account_type(self, token_service: TokenService) -> None:
        """AC4: SA token JWT payload contains token_type='service_account'."""
        import jwt as pyjwt

        access_token = token_service.create_access_token(
            subject_id=uuid4(),
            username="ci-pipeline",
            principal_type=PrincipalType.SERVICE_ACCOUNT,
        )

        payload = pyjwt.decode(access_token, options={"verify_signature": False})
        assert payload["token_type"] == "service_account"  # noqa: S105

    def test_sa_token_uses_sa_lifetime(self, token_service: TokenService) -> None:
        """AC11: SA token uses jwt_sa_access_token_lifetime_minutes."""
        import jwt as pyjwt

        access_token = token_service.create_access_token(
            subject_id=uuid4(),
            username="ci-pipeline",
            principal_type=PrincipalType.SERVICE_ACCOUNT,
        )

        payload = pyjwt.decode(access_token, options={"verify_signature": False})
        lifetime = payload["exp"] - payload["iat"]
        assert lifetime == 30 * 60

    def test_sa_token_has_required_claims(self, token_service: TokenService) -> None:
        """AC4: SA token contains sub, iss, aud, exp, token_type."""
        import jwt as pyjwt

        sa_id = uuid4()
        access_token = token_service.create_access_token(
            subject_id=sa_id,
            username="ci-pipeline",
            principal_type=PrincipalType.SERVICE_ACCOUNT,
        )

        payload = pyjwt.decode(access_token, options={"verify_signature": False})
        assert payload["sub"] == str(sa_id)
        assert payload["iss"] == "https://orchestrator.test"
        assert payload["aud"] == "orchestrator-api"
        assert "exp" in payload
        assert payload["token_type"] == "service_account"  # noqa: S105

    def test_sa_token_omits_user_claims(self, token_service: TokenService) -> None:
        """SA tokens should not contain user-specific claims."""
        import jwt as pyjwt

        access_token = token_service.create_access_token(
            subject_id=uuid4(),
            username="ci-pipeline",
            principal_type=PrincipalType.SERVICE_ACCOUNT,
        )

        payload = pyjwt.decode(access_token, options={"verify_signature": False})
        assert "email" not in payload
        assert "amr" not in payload
        assert "idp" not in payload
        assert payload["token_ver"] == 0

    def test_user_token_unchanged(self, token_service: TokenService) -> None:
        """User tokens are not affected by the service_account extension."""
        import jwt as pyjwt

        access_token = token_service.create_access_token(
            subject_id=uuid4(),
            username="human-user",
            email="user@test.com",
        )

        payload = pyjwt.decode(access_token, options={"verify_signature": False})
        assert "token_type" not in payload
        assert payload["email"] == "user@test.com"
        assert "amr" in payload
        assert "idp" in payload

    def test_decode_sa_token_preserves_token_type(self, token_service: TokenService) -> None:
        """decode_token round-trip: SA token_type='service_account' is preserved."""
        sa_id = uuid4()
        access_token = token_service.create_access_token(
            subject_id=sa_id,
            username="ci-pipeline",
            principal_type=PrincipalType.SERVICE_ACCOUNT,
        )

        decoded = token_service.decode_token(access_token, token_type="access")  # noqa: S106
        assert decoded.token_type == "service_account"  # noqa: S105

    def test_decode_user_token_type_remains_access(self, token_service: TokenService) -> None:
        """decode_token round-trip: user token keeps token_type='access'."""
        access_token = token_service.create_access_token(
            subject_id=uuid4(),
            username="human-user",
            email="user@test.com",
        )

        decoded = token_service.decode_token(access_token, token_type="access")  # noqa: S106
        assert decoded.token_type == "access"  # noqa: S105

    def test_sa_token_contains_cred_id(self, token_service: TokenService) -> None:
        """SA token JWT payload contains cred_id claim when credential_id is provided."""
        import jwt as pyjwt

        cred_id = uuid4()
        access_token = token_service.create_access_token(
            subject_id=uuid4(),
            username="ci-pipeline",
            credential_id=cred_id,
            principal_type=PrincipalType.SERVICE_ACCOUNT,
        )

        payload = pyjwt.decode(access_token, options={"verify_signature": False})
        assert payload["cred_id"] == str(cred_id)

    def test_decode_sa_token_preserves_credential_id(self, token_service: TokenService) -> None:
        """decode_token round-trip: SA cred_id claim maps to credential_id field."""
        cred_id = uuid4()
        access_token = token_service.create_access_token(
            subject_id=uuid4(),
            username="ci-pipeline",
            credential_id=cred_id,
            principal_type=PrincipalType.SERVICE_ACCOUNT,
        )

        decoded = token_service.decode_token(access_token, token_type="access")  # noqa: S106
        assert decoded.credential_id == str(cred_id)


class TestUserFromPayloadPrincipalType:
    """Tests for _user_from_payload setting __principal_type__ on service account tokens."""

    def test_sa_token_sets_service_account_principal_type(self) -> None:
        """SA token produces a User with __principal_type__ = SERVICE_ACCOUNT."""
        from datetime import UTC, datetime

        from syntara.auth.dependencies import _user_from_payload
        from syntara.auth.services.token_service import TokenPayload

        payload = TokenPayload(
            sub=str(uuid4()),
            iss="orchestrator",
            iat=datetime.now(UTC),
            exp=datetime.now(UTC),
            token_type="service_account",  # noqa: S106
            preferred_username="my-sa",
        )
        user = _user_from_payload(payload)
        assert user.__principal_type__ == PrincipalType.SERVICE_ACCOUNT

    def test_user_token_keeps_user_principal_type(self) -> None:
        """User token keeps the default __principal_type__ = USER."""
        from datetime import UTC, datetime

        from syntara.auth.dependencies import _user_from_payload
        from syntara.auth.services.token_service import TokenPayload

        payload = TokenPayload(
            sub=str(uuid4()),
            iss="orchestrator",
            iat=datetime.now(UTC),
            exp=datetime.now(UTC),
            token_type="access",  # noqa: S106
            preferred_username="human",
            email="human@example.com",
        )
        user = _user_from_payload(payload)
        assert user.__principal_type__ == PrincipalType.USER
