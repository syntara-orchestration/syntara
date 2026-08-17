"""E2E tests for service account CRUD API endpoints (API-1 through API-4).

Covers:
  API-1: Create service account (201, credential generation, nx_sa_ client_id, high-entropy secret)
  API-2: Read service account — secret not exposed (GET detail and list omit secret)
  API-3: Update service account (name/description update, credentials unchanged)
  API-4: Delete service account — soft delete (204, subsequent GET 404)
"""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from syntara_api_client.models.service_account_credential_create import ServiceAccountCredentialCreate
from syntara_api_client.models.service_account_credential_type import ServiceAccountCredentialType
from syntara_api_client.models.service_account_status import ServiceAccountStatus
from syntara_api_client.models.service_account_update import ServiceAccountUpdate

from tests.e2e.service_accounts import create_sa

if TYPE_CHECKING:
    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

pytestmark = [pytest.mark.e2e]

_MIN_SECRET_LENGTH = 48


class TestCreateServiceAccount:
    """API-1: Create service account."""

    def test_create_returns_201_with_expected_fields(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID
    ) -> None:
        """POST /service_accounts returns 201 with required fields populated."""
        sa = create_sa(syntara_api, first_project_id, description="E2E test account")

        try:
            assert sa.name.startswith("e2e-sa-")
            assert sa.status == ServiceAccountStatus.ACTIVE
            assert sa.project_id == first_project_id
            assert sa.description == "E2E test account"
            assert sa.created_at is not None
            assert sa.updated_at is not None
            assert isinstance(sa.id, UUID)
            assert isinstance(sa.created_by, UUID)
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)

    def test_create_credential_returns_client_id_and_secret(
        self, syntara_api: SyntaraApiRegistry, first_project_id: UUID
    ) -> None:
        """POST /service_accounts/{id}/credentials returns identifier (nx_sa_ prefixed) and high-entropy secret."""
        sa = create_sa(syntara_api, first_project_id)

        try:
            cred_resp = syntara_api.service_account_credentials.create(
                service_account_id=sa.id,
                body=ServiceAccountCredentialCreate(
                    credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
                ),
            )
            assert cred_resp.status_code == HTTPStatus.CREATED, (
                f"Expected 201, got {cred_resp.status_code}: {cred_resp.content!r}"
            )

            cred = cred_resp.assert_and_get()

            assert cred.identifier.startswith("nx_sa_"), f"Expected nx_sa_ prefix, got {cred.identifier}"
            assert len(cred.identifier) == 22, f"Expected 22 chars (nx_sa_ + 16 hex), got {len(cred.identifier)}"
            assert isinstance(cred.client_secret, str)
            assert len(cred.client_secret) >= _MIN_SECRET_LENGTH
            assert cred.service_account_id == sa.id
            assert cred.credential_type == ServiceAccountCredentialType.CLIENT_CREDENTIALS
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)


class TestReadServiceAccount:
    """API-2: Read service account — secret not exposed."""

    def test_get_detail_omits_secret(self, syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
        """GET /service_accounts/{id} response has no client_secret field."""
        sa = create_sa(syntara_api, first_project_id)

        try:
            syntara_api.service_account_credentials.create(
                service_account_id=sa.id,
                body=ServiceAccountCredentialCreate(
                    credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
                ),
            ).assert_and_get()

            detail = syntara_api.service_accounts.get(service_account_id=sa.id).assert_and_get()
            assert not hasattr(detail, "client_secret") or getattr(detail, "client_secret", None) is None
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)

    def test_list_omits_secret(self, syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
        """GET /service_accounts list entries have no client_secret field."""
        sa = create_sa(syntara_api, first_project_id)

        try:
            syntara_api.service_account_credentials.create(
                service_account_id=sa.id,
                body=ServiceAccountCredentialCreate(
                    credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
                ),
            ).assert_and_get()

            list_resp = syntara_api.service_accounts.list().assert_and_get()
            matching = [r for r in list_resp.resources if r.id == sa.id]
            assert len(matching) == 1
            assert not hasattr(matching[0], "client_secret") or getattr(matching[0], "client_secret", None) is None
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)

    def test_get_credential_omits_secret(self, syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
        """GET /service_accounts/{id}/credentials/{cred_id} omits client_secret."""
        sa = create_sa(syntara_api, first_project_id)

        try:
            cred = syntara_api.service_account_credentials.create(
                service_account_id=sa.id,
                body=ServiceAccountCredentialCreate(
                    credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
                ),
            ).assert_and_get()

            read_cred = syntara_api.service_account_credentials.get(
                service_account_id=sa.id,
                credential_id=cred.id,
            ).assert_and_get()

            assert not hasattr(read_cred, "client_secret") or getattr(read_cred, "client_secret", None) is None
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)


class TestUpdateServiceAccount:
    """API-3: Update service account (name/description update, credentials unchanged)."""

    def test_update_name_and_description(self, syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
        """PATCH /service_accounts/{id} updates name and description."""
        sa = create_sa(syntara_api, first_project_id, description="original")

        try:
            new_name = unique_name("e2e-sa-updated")
            updated = syntara_api.service_accounts.update(
                service_account_id=sa.id,
                body=ServiceAccountUpdate(name=new_name, description="updated"),
            ).assert_and_get()

            assert updated.name == new_name
            assert updated.description == "updated"
            assert updated.id == sa.id
            assert updated.status == ServiceAccountStatus.ACTIVE

            reread = syntara_api.service_accounts.get(service_account_id=sa.id).assert_and_get()
            assert reread.name == new_name
            assert reread.description == "updated"
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)

    def test_update_preserves_credentials(self, syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
        """PATCH does not alter existing credentials."""
        sa = create_sa(syntara_api, first_project_id)

        try:
            cred = syntara_api.service_account_credentials.create(
                service_account_id=sa.id,
                body=ServiceAccountCredentialCreate(
                    credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
                ),
            ).assert_and_get()

            syntara_api.service_accounts.update(
                service_account_id=sa.id,
                body=ServiceAccountUpdate(description="after-update"),
            ).assert_and_get()

            creds_after = syntara_api.service_account_credentials.list(
                service_account_id=sa.id,
            ).assert_and_get()

            assert len(creds_after.resources) == 1
            assert creds_after.resources[0].id == cred.id
            assert creds_after.resources[0].identifier == cred.identifier
        finally:
            syntara_api.service_accounts.delete(service_account_id=sa.id)


class TestDeleteServiceAccount:
    """API-4: Delete service account — soft delete."""

    def test_delete_returns_204(self, syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
        """DELETE /service_accounts/{id} returns 204."""
        sa = create_sa(syntara_api, first_project_id)

        resp = syntara_api.service_accounts.delete(service_account_id=sa.id)
        assert resp.status_code == HTTPStatus.NO_CONTENT

    def test_get_after_delete_returns_404(self, syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
        """GET /service_accounts/{id} returns 404 after soft-delete."""
        sa = create_sa(syntara_api, first_project_id)
        syntara_api.service_accounts.delete(service_account_id=sa.id)

        resp = syntara_api.service_accounts.get(service_account_id=sa.id)
        assert resp.status_code == HTTPStatus.NOT_FOUND

    def test_deleted_excluded_from_list(self, syntara_api: SyntaraApiRegistry, first_project_id: UUID) -> None:
        """Soft-deleted service accounts do not appear in list results."""
        sa = create_sa(syntara_api, first_project_id)
        syntara_api.service_accounts.delete(service_account_id=sa.id)

        list_resp = syntara_api.service_accounts.list().assert_and_get()
        ids = [r.id for r in list_resp.resources]
        assert sa.id not in ids
