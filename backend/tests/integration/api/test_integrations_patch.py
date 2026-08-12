"""Contract tests for PATCH /api/v1/integrations/{id}."""

from datetime import UTC, datetime
from uuid import uuid4

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.integrations.models.integration import IntegrationStatus
from tests.integration.helpers.credential import CredentialFactory
from tests.integration.helpers.integration import IntegrationFactory

BASE_URL = "/api/v1/integrations"


class TestIntegrationsPatch:
    """Contract tests for PATCH /api/v1/integrations/{id}."""

    async def test_patch_name_returns_200(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Patching the name field returns 200 with updated value."""
        integration = await integration_factory.create(name=f"before-{uuid4().hex[:8]}")
        await test_db_session.commit()

        new_name = f"after-{uuid4().hex[:8]}"
        response = await auth_client.patch(f"{BASE_URL}/{integration.id}", json={"name": new_name})
        assert response.status_code == 200
        assert response.json()["name"] == new_name

    async def test_patch_enabled_field(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Patching only the enabled field updates it correctly."""
        integration = await integration_factory.create(enabled=True)
        await test_db_session.commit()

        response = await auth_client.patch(f"{BASE_URL}/{integration.id}", json={"enabled": False})
        assert response.status_code == 200
        assert response.json()["enabled"] is False

    async def test_patch_partial_update_does_not_change_other_fields(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Patching one field does not alter unrelated fields."""
        original_name = f"partial-{uuid4().hex[:8]}"
        integration = await integration_factory.create(name=original_name, enabled=True)
        await test_db_session.commit()

        response = await auth_client.patch(f"{BASE_URL}/{integration.id}", json={"enabled": False})
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == original_name
        assert data["enabled"] is False

    async def test_patch_unknown_id_returns_404(self, auth_client: AsyncClient) -> None:
        """PATCH on a non-existent ID returns 404."""
        response = await auth_client.patch(f"{BASE_URL}/{uuid4()}", json={"enabled": False})
        assert response.status_code == 404

    async def test_patch_name_conflict_returns_409(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Patching to an existing name returns 409."""
        existing_name = f"existing-{uuid4().hex[:8]}"
        await integration_factory.create(name=existing_name)
        target = await integration_factory.create(name=f"target-{uuid4().hex[:8]}")
        await test_db_session.commit()

        response = await auth_client.patch(f"{BASE_URL}/{target.id}", json={"name": existing_name})
        assert response.status_code == 409

    async def test_patch_name_too_long_returns_422(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Patching with a name longer than 255 characters returns 422."""
        integration = await integration_factory.create()
        await test_db_session.commit()

        response = await auth_client.patch(f"{BASE_URL}/{integration.id}", json={"name": "x" * 256})
        assert response.status_code == 422

    async def test_patch_invalid_uuid_returns_422(self, auth_client: AsyncClient) -> None:
        """PATCH with a non-UUID path parameter returns 422."""
        response = await auth_client.patch(f"{BASE_URL}/not-a-uuid", json={"enabled": False})
        assert response.status_code == 422

    async def test_patch_requires_authentication(self, base_client: AsyncClient) -> None:
        """PATCH requires authentication."""
        response = await base_client.patch(f"{BASE_URL}/{uuid4()}", json={"enabled": False})
        assert response.status_code == 401

    async def test_patch_rejects_validation_status(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """PATCH with system-managed validation_status field returns 422."""
        integration = await integration_factory.create(name=f"sys-vs-{uuid4().hex[:8]}")
        await test_db_session.commit()

        response = await auth_client.patch(
            f"{BASE_URL}/{integration.id}",
            json={"validation_status": "available"},
        )
        assert response.status_code == 422

    async def test_patch_rejects_last_validated_at(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """PATCH with system-managed last_validated_at field returns 422."""
        integration = await integration_factory.create(name=f"sys-lv-{uuid4().hex[:8]}")
        await test_db_session.commit()

        response = await auth_client.patch(
            f"{BASE_URL}/{integration.id}",
            json={"last_validated_at": "2026-01-01T00:00:00Z"},
        )
        assert response.status_code == 422

    async def test_patch_rejects_validation_error(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """PATCH with system-managed validation_error field returns 422."""
        integration = await integration_factory.create(name=f"sys-ve-{uuid4().hex[:8]}")
        await test_db_session.commit()

        response = await auth_client.patch(
            f"{BASE_URL}/{integration.id}",
            json={"validation_error": "injected error"},
        )
        assert response.status_code == 422

    async def test_patch_system_fields_unchanged_after_valid_edit(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """System-managed fields retain their values after a valid user-field PATCH."""
        integration = await integration_factory.create(name=f"sys-retain-{uuid4().hex[:8]}")
        integration.validation_status = IntegrationStatus.AVAILABLE
        integration.last_validated_at = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        integration.validation_error = None
        await test_db_session.commit()

        new_name = f"sys-retain-updated-{uuid4().hex[:8]}"
        response = await auth_client.patch(
            f"{BASE_URL}/{integration.id}",
            json={"name": new_name},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == new_name
        assert data["validation_status"] == "available"
        assert data["last_validated_at"] is not None

    async def test_patch_description(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Patching the description field updates it correctly."""
        integration = await integration_factory.create(name=f"desc-{uuid4().hex[:8]}")
        await test_db_session.commit()

        response = await auth_client.patch(
            f"{BASE_URL}/{integration.id}",
            json={"description": "Updated description for testing"},
        )
        assert response.status_code == 200
        assert response.json()["description"] == "Updated description for testing"

    async def test_patch_configuration_url(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
    ) -> None:
        """Patching the configuration with a new base_url updates it correctly."""
        integration = await integration_factory.create(name=f"cfg-{uuid4().hex[:8]}")
        await test_db_session.commit()

        new_url = "https://updated-mcp.example.com"
        response = await auth_client.patch(
            f"{BASE_URL}/{integration.id}",
            json={
                "configuration": {
                    "integration_type": "mcp_server",
                    "base_url": new_url,
                },
            },
        )
        assert response.status_code == 200
        assert response.json()["configuration"]["base_url"] == new_url

    async def test_patch_management_credential_id(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
        credential_factory: CredentialFactory,
    ) -> None:
        """Patching management_credential_id links the integration to a credential."""
        integration = await integration_factory.create(name=f"cred-link-{uuid4().hex[:8]}")
        ct = await credential_factory.create_type("HTTP Bearer Token")
        project = await credential_factory.create_project()
        cred = await credential_factory.create(ct, project)
        await test_db_session.commit()

        response = await auth_client.patch(
            f"{BASE_URL}/{integration.id}",
            json={"management_credential_id": str(cred.id)},
        )
        assert response.status_code == 200
        assert response.json()["management_credential_id"] == str(cred.id)

    async def test_patch_management_credential_id_replacement(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
        credential_factory: CredentialFactory,
    ) -> None:
        """Replacing the management credential updates the integration."""
        ct = await credential_factory.create_type("HTTP Bearer Token")
        project = await credential_factory.create_project()
        cred_a = await credential_factory.create(ct, project, name=f"cred-a-{uuid4().hex[:8]}")
        cred_b = await credential_factory.create(ct, project, name=f"cred-b-{uuid4().hex[:8]}")

        integration = await integration_factory.create(name=f"cred-swap-{uuid4().hex[:8]}")
        integration.management_credential_id = cred_a.id
        await test_db_session.commit()

        response = await auth_client.patch(
            f"{BASE_URL}/{integration.id}",
            json={"management_credential_id": str(cred_b.id)},
        )
        assert response.status_code == 200
        assert response.json()["management_credential_id"] == str(cred_b.id)


class TestIntegrationCredentialCascade:
    """Tests for credential deletion impact on integrations (Test 37)."""

    async def test_delete_credential_nullifies_integration_management_credential(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        integration_factory: IntegrationFactory,
        credential_factory: CredentialFactory,
    ) -> None:
        """Deleting a credential sets the integration's management_credential_id to NULL."""
        ct = await credential_factory.create_type("HTTP Bearer Token")
        project = await credential_factory.create_project()
        cred = await credential_factory.create(ct, project, name=f"cascade-{uuid4().hex[:8]}")

        integration = await integration_factory.create(name=f"cascade-int-{uuid4().hex[:8]}")
        integration.management_credential_id = cred.id
        await test_db_session.commit()

        get_before = await auth_client.get(f"{BASE_URL}/{integration.id}")
        assert get_before.status_code == 200
        assert get_before.json()["management_credential_id"] == str(cred.id)

        delete_resp = await auth_client.delete(f"/api/v1/credentials/{cred.id}")
        assert delete_resp.status_code == 204

        get_after = await auth_client.get(f"{BASE_URL}/{integration.id}")
        assert get_after.status_code == 200
        assert get_after.json()["management_credential_id"] is None
