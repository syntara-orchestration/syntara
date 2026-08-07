"""E2E tests for service account token revocation on disable/delete (API-21,22,23).

Covers:
  API-21: Disable — immediate token invalidation (outstanding tokens rejected)
  API-22: Delete — immediate token invalidation (outstanding tokens rejected)
  API-23: Re-enable disabled service account (authentication restored)
"""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING

import httpx
import pytest
from syntara_api_client.models.service_account_credential_create import ServiceAccountCredentialCreate
from syntara_api_client.models.service_account_credential_type import ServiceAccountCredentialType

from tests.e2e.service_accounts import (
    create_sa_with_credential,
    poll_until_status,
    token_request,
)

if TYPE_CHECKING:
    from uuid import UUID

    from syntara_api_client.api import SyntaraApiRegistry
from orchestrator_test_sdk.e2e.tls import e2e_ssl_context

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

pytestmark = [pytest.mark.e2e]


class TestDisableTokenInvalidation:
    """API-21: Disable — immediate token invalidation (outstanding tokens rejected)."""

    def test_disable_invalidates_outstanding_tokens(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, syntara_base_url: str
    ) -> None:
        """Outstanding Bearer tokens are rejected after the SA is disabled."""
        sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)

        try:
            resp = token_request(syntara_base_url, client_id, client_secret)
            assert resp.status_code == HTTPStatus.OK
            access_token = resp.parsed.access_token

            pre_resp = httpx.get(
                f"{syntara_base_url}/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
                verify=e2e_ssl_context(),
            )
            assert pre_resp.status_code == HTTPStatus.OK, "Token should work before disable"

            syntara_api.service_accounts.disable(service_account_id=sa.id)

            rejection = poll_until_status(syntara_base_url, access_token, HTTPStatus.UNAUTHORIZED)
            assert rejection.status_code == HTTPStatus.UNAUTHORIZED, (
                f"Expected 401 after disable, still got {rejection.status_code}"
            )
        finally:
            try:
                syntara_api.service_accounts.enable(service_account_id=sa.id)
            except Exception:
                pass
            syntara_api.service_accounts.delete(service_account_id=sa.id)


class TestDeleteTokenInvalidation:
    """API-22: Delete — immediate token invalidation (outstanding tokens rejected)."""

    def test_delete_invalidates_outstanding_tokens(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, syntara_base_url: str
    ) -> None:
        """Outstanding Bearer tokens are rejected after the SA is deleted."""
        sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)

        resp = token_request(syntara_base_url, client_id, client_secret)
        assert resp.status_code == HTTPStatus.OK
        access_token = resp.parsed.access_token

        pre_resp = httpx.get(
            f"{syntara_base_url}/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
            verify=e2e_ssl_context(),
        )
        assert pre_resp.status_code == HTTPStatus.OK, "Token should work before delete"

        syntara_api.service_accounts.delete(service_account_id=sa.id)

        rejection = poll_until_status(syntara_base_url, access_token, HTTPStatus.UNAUTHORIZED)
        assert rejection.status_code == HTTPStatus.UNAUTHORIZED, (
            f"Expected 401 after delete, still got {rejection.status_code}"
        )


class TestReEnableRestoresAuth:
    """API-23: Re-enable disabled service account (authentication restored)."""

    def test_re_enable_restores_authentication(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, syntara_base_url: str
    ) -> None:
        """After re-enabling a disabled SA, a fresh token grants access again.

        The old token remains revoked (token_version was incremented on disable).
        The SA must re-authenticate via client credentials to get a new token.
        """
        sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)

        try:
            resp = token_request(syntara_base_url, client_id, client_secret)
            assert resp.status_code == HTTPStatus.OK
            old_token = resp.parsed.access_token

            syntara_api.service_accounts.disable(service_account_id=sa.id)

            rejection = poll_until_status(syntara_base_url, old_token, HTTPStatus.UNAUTHORIZED)
            assert rejection.status_code == HTTPStatus.UNAUTHORIZED, "Old token should be rejected after disable"

            syntara_api.service_accounts.enable(service_account_id=sa.id)

            new_resp = token_request(syntara_base_url, client_id, client_secret)
            assert new_resp.status_code == HTTPStatus.OK, "Client credentials grant should succeed after re-enable"
            new_token = new_resp.parsed.access_token

            me_resp = poll_until_status(syntara_base_url, new_token, HTTPStatus.OK)
            assert me_resp.status_code == HTTPStatus.OK, "New token should grant access after re-enable"

            old_still_dead = httpx.get(
                f"{syntara_base_url}/api/v1/auth/me",
                headers={"Authorization": f"Bearer {old_token}"},
                verify=e2e_ssl_context(),
            )
            assert old_still_dead.status_code == HTTPStatus.UNAUTHORIZED, (
                "Old token should remain revoked after re-enable (token_version incremented on disable)"
            )
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)


class TestCredentialDisableTokenInvalidation:
    """Disabling a credential invalidates only that credential's tokens."""

    def test_disable_credential_invalidates_its_tokens_only(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, syntara_base_url: str
    ) -> None:
        """Token from credential A is rejected after disable; token from credential B still works."""
        sa, client_id_a, client_secret_a = create_sa_with_credential(syntara_api, first_project_id)

        try:
            cred_b = syntara_api.service_account_credentials.create(
                service_account_id=sa.id,
                body=ServiceAccountCredentialCreate(credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS),
            ).assert_and_get()

            token_a = token_request(syntara_base_url, client_id_a, client_secret_a).parsed.access_token
            token_b = token_request(syntara_base_url, cred_b.identifier, cred_b.client_secret).parsed.access_token

            pre_a = httpx.get(
                f"{syntara_base_url}/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token_a}"},
                verify=e2e_ssl_context(),
            )
            assert pre_a.status_code == HTTPStatus.OK, "Token A should work before disable"

            creds = syntara_api.service_account_credentials.list(service_account_id=sa.id).assert_and_get()
            cred_a_id = next(c.id for c in creds.resources if c.identifier == client_id_a)

            syntara_api.service_account_credentials.disable(
                service_account_id=sa.id,
                credential_id=cred_a_id,
            )

            rejection_a = poll_until_status(syntara_base_url, token_a, HTTPStatus.UNAUTHORIZED)
            assert rejection_a.status_code == HTTPStatus.UNAUTHORIZED, (
                f"Token A should be rejected after credential disable, got {rejection_a.status_code}"
            )

            me_b = httpx.get(
                f"{syntara_base_url}/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token_b}"},
                verify=e2e_ssl_context(),
            )
            assert me_b.status_code == HTTPStatus.OK, "Token B should still work — only credential A was disabled"
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)

    def test_delete_credential_invalidates_its_tokens(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, syntara_base_url: str
    ) -> None:
        """Token from a deleted credential is rejected."""
        sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)

        try:
            access_token = token_request(syntara_base_url, client_id, client_secret).parsed.access_token

            pre = httpx.get(
                f"{syntara_base_url}/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
                verify=e2e_ssl_context(),
            )
            assert pre.status_code == HTTPStatus.OK, "Token should work before delete"

            creds = syntara_api.service_account_credentials.list(service_account_id=sa.id).assert_and_get()
            cred_id = next(c.id for c in creds.resources if c.identifier == client_id)

            syntara_api.service_account_credentials.delete(
                service_account_id=sa.id,
                credential_id=cred_id,
            )

            rejection = poll_until_status(syntara_base_url, access_token, HTTPStatus.UNAUTHORIZED)
            assert rejection.status_code == HTTPStatus.UNAUTHORIZED, (
                f"Expected 401 after credential delete, got {rejection.status_code}"
            )
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)
