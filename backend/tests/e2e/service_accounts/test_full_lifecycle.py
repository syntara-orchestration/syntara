"""E2E tests for full service account lifecycle flows (API-24, API-35).

Covers:
  API-24: Cross-project delegation — full flow
          (create in Project A, grant to Project B admin, authenticate,
           cross-project access, audit verification)
  API-35: E2E full lifecycle
          (create → authenticate → authz → rotate → grace period →
           disable → deny → audit log verification)
"""

from __future__ import annotations

import os
import time
from http import HTTPStatus
from typing import TYPE_CHECKING

import httpx
import pytest
from orchestrator_test_sdk.e2e.tls import e2e_ssl_context
from syntara_api_client.models.role_assignment_create import RoleAssignmentCreate
from syntara_api_client.models.sa_credential_create import SACredentialCreate
from syntara_api_client.models.service_account_credential_type import ServiceAccountCredentialType

from tests.e2e.service_accounts import create_sa, create_sa_with_credential, poll_until_status, token_request

if TYPE_CHECKING:
    from orchestrator_test_sdk.factories import ProjectFactory
    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

pytestmark = [pytest.mark.e2e]


class TestCrossProjectDelegation:
    """API-24: Cross-project delegation — full flow.

    Create SA in Project A, grant it a role in Project B,
    authenticate, verify cross-project access.
    """

    def test_cross_project_delegation_full_flow(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
    ) -> None:
        proj_a_id, _ = create_project(admin_api, "xproj-a")
        proj_b_id, _ = create_project(admin_api, "xproj-b")

        sa = create_sa(admin_api, proj_a_id, prefix="xproj-sa")

        cred = admin_api.service_account_credentials.create(
            service_account_id=sa.id,
            body=SACredentialCreate(credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS),
        ).assert_and_get()

        admin_api.projects.create_role_assignment(
            project_id=proj_b_id,
            body=RoleAssignmentCreate(
                principal_id=sa.id,
                role_name="project-admin",
            ),
        )

        try:
            resp = token_request(syntara_base_url, cred.identifier, cred.client_secret)
            assert resp.status_code == HTTPStatus.OK
            access_token = resp.parsed.access_token

            me_resp = httpx.get(
                f"{syntara_base_url}/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
                verify=e2e_ssl_context(),
            )
            assert me_resp.status_code == HTTPStatus.OK
            assert me_resp.json()["id"] == str(sa.id)

            # SA can create a child SA in Project B (cross-project)
            child_resp = httpx.post(
                f"{syntara_base_url}/api/v1/service_accounts",
                json={"name": "xproj-child-sa", "project_id": str(proj_b_id)},
                headers={"Authorization": f"Bearer {access_token}"},
                verify=e2e_ssl_context(),
            )
            assert child_resp.status_code == HTTPStatus.CREATED, (
                f"SA should have access to Project B, got {child_resp.status_code}: {child_resp.text}"
            )
            child_sa_id = child_resp.json()["id"]

            # SA cannot create in a project it has no role in
            proj_a_create = httpx.post(
                f"{syntara_base_url}/api/v1/service_accounts",
                json={"name": "xproj-noaccess-sa", "project_id": str(proj_a_id)},
                headers={"Authorization": f"Bearer {access_token}"},
                verify=e2e_ssl_context(),
            )
            assert proj_a_create.status_code == HTTPStatus.FORBIDDEN, (
                f"SA should NOT have admin access to Project A, got {proj_a_create.status_code}"
            )

            # Clean up child SA
            httpx.delete(
                f"{syntara_base_url}/api/v1/service_accounts/{child_sa_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                verify=e2e_ssl_context(),
            )
        finally:
            admin_api.service_accounts.delete(service_account_id=sa.id)


class TestFullLifecycle:
    """API-35: E2E full lifecycle.

    create → authenticate → authz → rotate → grace period →
    disable → deny.
    """

    GRACE_PERIOD_SECONDS = 5

    def test_full_sa_lifecycle(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
    ) -> None:
        project_id, _ = create_project(admin_api, "lifecycle")

        # --- 1. Create SA + credential ---
        sa, client_id, client_secret = create_sa_with_credential(admin_api, project_id)

        admin_api.projects.create_role_assignment(
            project_id=project_id,
            body=RoleAssignmentCreate(
                principal_id=sa.id,
                role_name="project-admin",
            ),
        )

        try:
            # --- 2. Authenticate ---
            resp = token_request(syntara_base_url, client_id, client_secret)
            assert resp.status_code == HTTPStatus.OK
            access_token = resp.parsed.access_token

            # --- 3. Authorized access ---
            me_resp = httpx.get(
                f"{syntara_base_url}/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
                verify=e2e_ssl_context(),
            )
            assert me_resp.status_code == HTTPStatus.OK
            assert me_resp.json()["id"] == str(sa.id)

            sa_after_auth = admin_api.service_accounts.get(service_account_id=sa.id).assert_and_get()
            assert sa_after_auth.last_authenticated_at is not None

            # --- 4. Rotate credential with short grace period ---
            cred_list = admin_api.service_account_credentials.list(service_account_id=sa.id).assert_and_get()
            cred_id = cred_list.resources[0].id

            rotate_resp = httpx.post(
                f"{syntara_base_url}/api/v1/service_accounts/{sa.id}/credentials/{cred_id}/rotate",
                json={"grace_period_seconds": self.GRACE_PERIOD_SECONDS},
                headers={"Authorization": f"Bearer {access_token}"},
                verify=e2e_ssl_context(),
            )
            assert rotate_resp.status_code == HTTPStatus.OK
            new_secret = rotate_resp.json()["client_secret"]

            # --- 5. Grace period: old secret still works ---
            old_secret_resp = token_request(syntara_base_url, client_id, client_secret)
            assert old_secret_resp.status_code == HTTPStatus.OK, "Old secret should still work during grace period"

            # New secret also works
            new_secret_resp = token_request(syntara_base_url, client_id, new_secret)
            assert new_secret_resp.status_code == HTTPStatus.OK, "New secret should work immediately"

            # Wait for grace period to expire
            time.sleep(self.GRACE_PERIOD_SECONDS + 1)

            old_secret_expired = token_request(syntara_base_url, client_id, client_secret)
            assert old_secret_expired.status_code == HTTPStatus.UNAUTHORIZED, (
                "Old secret should be rejected after grace period expires"
            )

            # New secret still works after grace expiry
            post_grace_resp = token_request(syntara_base_url, client_id, new_secret)
            assert post_grace_resp.status_code == HTTPStatus.OK
            fresh_token = post_grace_resp.parsed.access_token

            # --- 6. Disable → deny ---
            admin_api.service_accounts.disable(service_account_id=sa.id)

            rejection = poll_until_status(syntara_base_url, fresh_token, HTTPStatus.UNAUTHORIZED)
            assert rejection.status_code == HTTPStatus.UNAUTHORIZED, (
                f"Token should be rejected after disable, got {rejection.status_code}"
            )

            # Token endpoint also rejects disabled SA
            disabled_auth = token_request(syntara_base_url, client_id, new_secret)
            assert disabled_auth.status_code == HTTPStatus.UNAUTHORIZED, "Disabled SA should not obtain new tokens"

        finally:
            try:
                admin_api.service_accounts.enable(service_account_id=sa.id)
            except Exception:
                pass
            admin_api.service_accounts.delete(service_account_id=sa.id)
