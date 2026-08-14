"""E2E tests for client secret rotation with grace period (API-19, API-20).

Covers:
  API-19: Secret rotation — grace period (both old and new secrets valid during grace window)
  API-20: Secret rotation — old secret rejected after grace period expires
"""

from __future__ import annotations

import os
import time
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.tls import e2e_ssl_context
from syntara_api_client import Client
from syntara_api_client.api.authentication.token import sync_detailed
from syntara_api_client.models.body_token import BodyToken
from syntara_api_client.models.service_account_create import ServiceAccountCreate
from syntara_api_client.models.service_account_credential_create import ServiceAccountCredentialCreate
from syntara_api_client.models.service_account_credential_rotate_request import ServiceAccountCredentialRotateRequest
from syntara_api_client.models.service_account_credential_type import ServiceAccountCredentialType

if TYPE_CHECKING:
    from uuid import UUID

    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

pytestmark = [pytest.mark.e2e]


def _token_request(base_url: str, client_id: str, client_secret: str) -> Any:  # noqa: ANN401
    """POST /auth/token via the generated client."""
    client = Client(base_url=f"{base_url}/api/v1", verify_ssl=e2e_ssl_context())
    return sync_detailed(
        client=client,
        body=BodyToken(grant_type="client_credentials", client_id=client_id, client_secret=client_secret),
    )


class TestSecretRotationGracePeriod:
    """API-19: Secret rotation — grace period."""

    def test_grace_period_both_secrets_valid(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, syntara_base_url: str
    ) -> None:
        """During the grace period, both old and new secrets are accepted."""
        sa = syntara_api.service_accounts.create(
            body=ServiceAccountCreate(name=unique_name("e2e-sa"), project_id=first_project_id),
        ).assert_and_get()

        try:
            cred = syntara_api.service_account_credentials.create(
                service_account_id=sa.id,
                body=ServiceAccountCredentialCreate(credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS),
            ).assert_and_get()

            old_secret = cred.client_secret
            client_id = cred.identifier

            rotated = syntara_api.service_account_credentials.rotate(
                service_account_id=sa.id,
                credential_id=cred.id,
                body=ServiceAccountCredentialRotateRequest(grace_period_seconds=3600),
            ).assert_and_get()

            new_secret = rotated.client_secret
            assert new_secret != old_secret

            resp_old = _token_request(syntara_base_url, client_id, old_secret)
            assert resp_old.status_code == HTTPStatus.OK, (
                f"Old secret should work during grace period, got {resp_old.status_code}"
            )

            resp_new = _token_request(syntara_base_url, client_id, new_secret)
            assert resp_new.status_code == HTTPStatus.OK, f"New secret should work, got {resp_new.status_code}"
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)


class TestSecretRotationGraceExpiry:
    """API-20: Secret rotation — old secret rejected after grace period expires."""

    GRACE_PERIOD_SECONDS = 3
    POLL_TIMEOUT_SECONDS = 10
    POLL_INTERVAL_SECONDS = 0.5

    def test_old_secret_rejected_after_grace(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, syntara_base_url: str
    ) -> None:
        """After the grace period, only the new secret works."""
        sa = syntara_api.service_accounts.create(
            body=ServiceAccountCreate(name=unique_name("e2e-sa"), project_id=first_project_id),
        ).assert_and_get()

        try:
            cred = syntara_api.service_account_credentials.create(
                service_account_id=sa.id,
                body=ServiceAccountCredentialCreate(credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS),
            ).assert_and_get()

            old_secret = cred.client_secret
            client_id = cred.identifier

            rotated = syntara_api.service_account_credentials.rotate(
                service_account_id=sa.id,
                credential_id=cred.id,
                body=ServiceAccountCredentialRotateRequest(grace_period_seconds=self.GRACE_PERIOD_SECONDS),
            ).assert_and_get()

            new_secret = rotated.client_secret

            # Verify old secret still works during grace period
            resp_during = _token_request(syntara_base_url, client_id, old_secret)
            assert resp_during.status_code == HTTPStatus.OK, (
                f"Old secret should work during grace period, got {resp_during.status_code}"
            )

            # Poll until old secret is rejected (grace period expired)
            deadline = time.monotonic() + self.POLL_TIMEOUT_SECONDS
            old_rejected = False
            while time.monotonic() < deadline:
                time.sleep(self.POLL_INTERVAL_SECONDS)
                resp_old = _token_request(syntara_base_url, client_id, old_secret)
                if resp_old.status_code == HTTPStatus.UNAUTHORIZED:
                    old_rejected = True
                    break

            assert old_rejected, (
                f"Old secret was still accepted after {self.POLL_TIMEOUT_SECONDS}s "
                f"(grace_period={self.GRACE_PERIOD_SECONDS}s)"
            )

            resp_new = _token_request(syntara_base_url, client_id, new_secret)
            assert resp_new.status_code == HTTPStatus.OK, f"New secret should still work, got {resp_new.status_code}"
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)
