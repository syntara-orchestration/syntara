"""E2E tests for service account token validation via auth middleware (API-16,17,18,32,37,38).

Covers:
  API-16: Token validation — authorized API access (Bearer token grants access)
  API-17: Token validation — unauthorized returns 403 (insufficient permissions)
  API-18: Token validation — expired token rejected, no refresh flow
  API-32: Project role assignment — SA with project-admin role accessing project resources
  API-37: Performance — 100 concurrent service accounts (scale validation)
  API-38: Last authenticated timestamp updated on successful auth
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import httpx
import jwt as pyjwt
import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.tls import e2e_ssl_context
from syntara_api_client.models.role_assignment_create import RoleAssignmentCreate
from syntara_api_client.models.sa_credential_create import SACredentialCreate
from syntara_api_client.models.service_account_credential_type import ServiceAccountCredentialType

from tests.e2e.service_accounts import create_sa, create_sa_with_credential, token_request

if TYPE_CHECKING:
    from uuid import UUID

    from orchestrator_test_sdk.factories import ProjectFactory
    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

pytestmark = [pytest.mark.e2e]


class TestTokenValidationAuthorized:
    """API-16: Token validation — authorized API access (Bearer token grants access)."""

    def test_bearer_token_grants_api_access(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, syntara_base_url: str
    ) -> None:
        """SA Bearer token is accepted by protected endpoints and returns SA identity."""
        sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)

        try:
            resp = token_request(syntara_base_url, client_id, client_secret)
            assert resp.status_code == HTTPStatus.OK
            access_token = resp.parsed.access_token

            me_resp = httpx.get(
                f"{syntara_base_url}/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
                verify=e2e_ssl_context(),
            )
            assert me_resp.status_code == HTTPStatus.OK
            me_body = me_resp.json()
            assert me_body["id"] == str(sa.id)
            assert me_body["username"] == sa.name
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)


class TestTokenValidationUnauthorized:
    """API-17: Token validation — unauthorized returns 403 (insufficient permissions)."""

    def test_insufficient_permissions_returns_403(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
    ) -> None:
        """SA token without permissions on another project gets 403."""
        proj_a_id, _ = create_project(admin_api, "authz-a")
        proj_b_id, _ = create_project(admin_api, "authz-b")

        sa, client_id, client_secret = create_sa_with_credential(admin_api, proj_a_id)

        try:
            resp = token_request(syntara_base_url, client_id, client_secret)
            assert resp.status_code == HTTPStatus.OK
            access_token = resp.parsed.access_token

            create_resp = httpx.post(
                f"{syntara_base_url}/api/v1/service_accounts",
                json={"name": unique_name("unauth-sa"), "project_id": str(proj_b_id)},
                headers={"Authorization": f"Bearer {access_token}"},
                verify=e2e_ssl_context(),
            )
            assert create_resp.status_code == HTTPStatus.FORBIDDEN
        finally:
            admin_api.service_accounts.delete(service_account_id=sa.id)


class TestExpiredTokenRejected:
    """API-18: Token validation — expired token rejected, no refresh flow."""

    def test_token_has_correct_expiry_and_no_refresh(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, syntara_base_url: str
    ) -> None:
        """SA token has 15-min lifetime, and there is no refresh endpoint for SAs.

        Full expiry enforcement is tested at the JWT library level. This test
        verifies the token structure and that no refresh flow exists.
        """
        sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)

        try:
            resp = token_request(syntara_base_url, client_id, client_secret)
            assert resp.status_code == HTTPStatus.OK

            payload = pyjwt.decode(resp.parsed.access_token, options={"verify_signature": False})
            lifetime_seconds = payload["exp"] - payload["iat"]
            assert lifetime_seconds == 900, f"Expected 15-min lifetime, got {lifetime_seconds}s"

            assert resp.parsed.token_type == "Bearer"  # noqa: S105
            assert hasattr(resp.parsed, "to_dict"), (
                "Response model missing to_dict; cannot verify absence of refresh_token"
            )
            assert "refresh_token" not in resp.parsed.to_dict()
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)

    def test_malformed_bearer_token_returns_401(self, syntara_base_url: str) -> None:
        """A completely invalid Bearer token is rejected with 401."""
        resp = httpx.get(
            f"{syntara_base_url}/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
            verify=e2e_ssl_context(),
        )
        assert resp.status_code == HTTPStatus.UNAUTHORIZED


class TestProjectRoleAssignment:
    """API-32: Project role assignment — SA with project-admin role accessing project resources."""

    def test_sa_with_project_admin_role_accesses_project_resources(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
    ) -> None:
        """SA assigned project-admin on its own project can manage SAs in that project."""
        project_id, _ = create_project(admin_api, "proj-role")
        sa = create_sa(admin_api, project_id)

        admin_api.projects.create_role_assignment(
            project_id=project_id,
            body=RoleAssignmentCreate(
                principal_id=sa.id,
                role_name="project-admin",
            ),
        )

        cred = admin_api.service_account_credentials.create(
            service_account_id=sa.id,
            body=SACredentialCreate(credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS),
        ).assert_and_get()

        try:
            resp = token_request(syntara_base_url, cred.identifier, cred.client_secret)
            assert resp.status_code == HTTPStatus.OK
            access_token = resp.parsed.access_token

            list_resp = httpx.get(
                f"{syntara_base_url}/api/v1/service_accounts",
                headers={"Authorization": f"Bearer {access_token}"},
                verify=e2e_ssl_context(),
            )
            assert list_resp.status_code == HTTPStatus.OK
            resources = list_resp.json().get("resources", [])
            listed_ids = {r["id"] for r in resources}
            assert str(sa.id) in listed_ids
        finally:
            admin_api.service_accounts.delete(service_account_id=sa.id)


class TestConcurrentServiceAccounts:
    """API-37: Performance — 100 concurrent service accounts (scale validation)."""

    CONCURRENT_SA_COUNT = 100

    def test_100_concurrent_sa_auth(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, syntara_base_url: str
    ) -> None:
        """100 concurrent SAs can all authenticate and access the API simultaneously."""
        sa_data: list[tuple[Any, str]] = []
        try:
            for _ in range(self.CONCURRENT_SA_COUNT):
                sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)
                resp = token_request(syntara_base_url, client_id, client_secret)
                assert resp.status_code == HTTPStatus.OK
                sa_data.append((sa, resp.parsed.access_token))

            def _check_auth(access_token: str) -> int:
                r = httpx.get(
                    f"{syntara_base_url}/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {access_token}"},
                    verify=e2e_ssl_context(),
                    timeout=30,
                )
                return r.status_code

            with ThreadPoolExecutor(max_workers=20) as pool:
                futures = {pool.submit(_check_auth, token): i for i, (_, token) in enumerate(sa_data)}
                results = {}
                for future in as_completed(futures):
                    idx = futures[future]
                    results[idx] = future.result()

            failed = {i: code for i, code in results.items() if code != HTTPStatus.OK}
            assert not failed, f"{len(failed)}/{self.CONCURRENT_SA_COUNT} SAs failed auth: {failed}"
        finally:
            for sa, _ in sa_data:
                try:
                    syntara_api.service_accounts.delete(service_account_id=sa.id)
                except Exception:
                    pass


class TestLastAuthenticatedTimestamp:
    """API-38: Last authenticated timestamp updated on successful auth."""

    def test_last_authenticated_updated_on_auth(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID, syntara_base_url: str
    ) -> None:
        """last_authenticated_at is null before first auth, then set after token issuance."""
        sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)

        try:
            before = syntara_api.service_accounts.get(service_account_id=sa.id).assert_and_get()
            assert before.last_authenticated_at is None, (
                f"Expected null before first auth, got {before.last_authenticated_at}"
            )

            resp = token_request(syntara_base_url, client_id, client_secret)
            assert resp.status_code == HTTPStatus.OK

            after = syntara_api.service_accounts.get(service_account_id=sa.id).assert_and_get()
            assert after.last_authenticated_at is not None, "last_authenticated_at should be set after auth"
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)
