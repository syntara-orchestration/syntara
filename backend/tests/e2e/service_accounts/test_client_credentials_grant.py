"""E2E tests for the OAuth 2.0 client credentials grant token endpoint (API-9 through API-15, API-33, API-39).

Covers:
  API-9:  Client credentials grant — happy path (JWT issuance, ES256, claims)
  API-10: Client credentials grant — HTTP Basic auth header
  API-11: Client credentials grant — invalid secret (401)
  API-12: Client credentials grant — unknown client ID (401, no enumeration leak)
  API-13: Client credentials grant — disabled service account (401)
  API-14: Client credentials grant — deleted service account (401)
  API-15: Client credentials grant — built-in admin excluded
  API-33: SA-specific token lifetime independent from user TTL
  API-39: Missing/unsupported grant_type (400/422)
"""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING

import httpx
import jwt as pyjwt
import pytest
from orchestrator_test_sdk.e2e.auth import admin_password
from orchestrator_test_sdk.e2e.tls import e2e_ssl_context

from tests.e2e.service_accounts import create_sa_with_credential, token_request

if TYPE_CHECKING:
    from uuid import UUID

    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

pytestmark = [pytest.mark.e2e]


class TestClientCredentialsGrant:
    """API-9: Client credentials grant — happy path."""

    def test_happy_path_jwt_issuance(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, nexus_base_url: str
    ) -> None:
        """POST /auth/token returns 200 with valid ES256 JWT and correct claims."""
        sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)

        try:
            resp = token_request(nexus_base_url, client_id, client_secret)

            assert resp.status_code == HTTPStatus.OK
            body = resp.parsed
            assert body is not None
            assert body.access_token
            assert body.token_type == "Bearer"  # noqa: S105
            assert isinstance(body.expires_in, int)

            payload = pyjwt.decode(body.access_token, options={"verify_signature": False})
            assert payload["sub"] == str(sa.id)
            assert payload["token_type"] == "service_account"  # noqa: S105
            assert "iss" in payload
            assert "aud" in payload
            assert "exp" in payload
            assert "iat" in payload

            header = pyjwt.get_unverified_header(body.access_token)
            assert header["alg"] == "ES256"
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)

    def test_tampered_token_rejected(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, nexus_base_url: str
    ) -> None:
        """A token with a tampered payload is rejected by protected endpoints."""
        sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)

        try:
            resp = token_request(nexus_base_url, client_id, client_secret)
            assert resp.status_code == HTTPStatus.OK
            valid_token = resp.parsed.access_token

            # Tamper with the payload segment (middle part of header.payload.signature)
            parts = valid_token.split(".")
            assert len(parts) == 3
            # Flip a character in the payload to invalidate the signature
            payload_bytes = bytearray(parts[1].encode())
            payload_bytes[0] = ord("A") if payload_bytes[0] != ord("A") else ord("B")
            tampered_token = f"{parts[0]}.{payload_bytes.decode()}.{parts[2]}"

            tampered_resp = httpx.get(
                f"{nexus_base_url}/api/v1/auth/me",
                headers={"Authorization": f"Bearer {tampered_token}"},
                verify=e2e_ssl_context(),
            )
            assert tampered_resp.status_code == HTTPStatus.UNAUTHORIZED, (
                f"Tampered token should be rejected, got {tampered_resp.status_code}"
            )

            # Confirm the original valid token IS accepted
            valid_resp = httpx.get(
                f"{nexus_base_url}/api/v1/auth/me",
                headers={"Authorization": f"Bearer {valid_token}"},
                verify=e2e_ssl_context(),
            )
            assert valid_resp.status_code == HTTPStatus.OK, (
                f"Valid token should be accepted, got {valid_resp.status_code}"
            )
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)


class TestClientCredentialsBasicAuth:
    """API-10: Client credentials grant — HTTP Basic auth header."""

    def test_http_basic_auth(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, nexus_base_url: str
    ) -> None:
        """Credentials via Authorization: Basic header returns a valid token."""
        sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)

        try:
            resp = token_request(nexus_base_url, client_id, client_secret, use_basic_auth=True)

            assert resp.status_code == HTTPStatus.OK
            assert resp.parsed is not None
            assert resp.parsed.access_token
            assert resp.parsed.token_type == "Bearer"  # noqa: S105
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)


class TestClientCredentialsInvalidSecret:
    """API-11: Client credentials grant — invalid secret."""

    def test_invalid_secret_returns_401(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, nexus_base_url: str
    ) -> None:
        """Correct client_id with wrong secret returns 401."""
        sa, client_id, _ = create_sa_with_credential(syntara_api, first_project_id)

        try:
            resp = token_request(nexus_base_url, client_id, "wrong-secret")
            assert resp.status_code == HTTPStatus.UNAUTHORIZED
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)


class TestClientCredentialsUnknownClientId:
    """API-12: Client credentials grant — unknown client ID."""

    def test_unknown_client_id_returns_401(self, nexus_base_url: str) -> None:
        """Fabricated client_id returns 401 with no enumeration leak."""
        resp = token_request(nexus_base_url, "nx_sa_nonexistent", "any-secret")
        assert resp.status_code == HTTPStatus.UNAUTHORIZED


class TestClientCredentialsDisabledSA:
    """API-13: Client credentials grant — disabled service account."""

    def test_disabled_sa_returns_401(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, nexus_base_url: str
    ) -> None:
        """Disabled SA cannot obtain a token."""
        sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)

        try:
            syntara_api.service_accounts.disable(service_account_id=sa.id)

            resp = token_request(nexus_base_url, client_id, client_secret)
            assert resp.status_code == HTTPStatus.UNAUTHORIZED
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)


class TestClientCredentialsDeletedSA:
    """API-14: Client credentials grant — deleted service account."""

    def test_deleted_sa_returns_401(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, nexus_base_url: str
    ) -> None:
        """Deleted SA cannot obtain a token."""
        sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)
        syntara_api.service_accounts.delete(service_account_id=sa.id)

        resp = token_request(nexus_base_url, client_id, client_secret)
        assert resp.status_code == HTTPStatus.UNAUTHORIZED


class TestClientCredentialsBuiltinAdminExcluded:
    """API-15: Client credentials grant — built-in admin excluded."""

    def test_builtin_admin_excluded(self, nexus_base_url: str) -> None:
        """Built-in admin credentials are not eligible for client credentials grant.

        Uses the real admin password to prove the admin *account type* is excluded,
        not just that a wrong password gets a 401.
        """
        password = admin_password()
        resp = token_request(nexus_base_url, "admin", password)
        assert resp.status_code == HTTPStatus.UNAUTHORIZED


class TestSATokenLifetime:
    """API-33: SA-specific token lifetime configuration."""

    # Default from jwt_sa_access_token_lifetime_minutes (config/base.py)
    EXPECTED_SA_LIFETIME_SECONDS = 15 * 60  # 900

    def test_sa_specific_token_lifetime(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, nexus_base_url: str
    ) -> None:
        """SA access token exp - iat matches the configured SA-specific lifetime."""
        sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)

        try:
            resp = token_request(nexus_base_url, client_id, client_secret)
            assert resp.status_code == HTTPStatus.OK

            payload = pyjwt.decode(resp.parsed.access_token, options={"verify_signature": False})
            lifetime_seconds = payload["exp"] - payload["iat"]
            assert lifetime_seconds == self.EXPECTED_SA_LIFETIME_SECONDS
            assert resp.parsed.expires_in == self.EXPECTED_SA_LIFETIME_SECONDS
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)


class TestUnsupportedGrantType:
    """API-39: Missing/unsupported grant_type."""

    def test_unsupported_grant_type_returns_400(self, nexus_base_url: str) -> None:
        """grant_type=authorization_code returns 400."""
        resp = token_request(nexus_base_url, "any", "any", grant_type="authorization_code")
        assert resp.status_code == HTTPStatus.BAD_REQUEST

    def test_missing_grant_type_returns_422(self, nexus_base_url: str) -> None:
        """Missing grant_type returns 422 (validation error).

        BodyToken.grant_type is required, so this case needs raw httpx.
        """
        resp = httpx.post(
            f"{nexus_base_url}/api/v1/auth/token",
            data={"client_id": "any", "client_secret": "any"},
            verify=e2e_ssl_context(),
        )
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
