"""Tests for cluster synchronization in IntegrationService.

Tests the creation, update, and deletion of cluster records when
OpenShift integrations are created, updated, and deleted.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.integrations.models.integration import (
    IntegrationCreate,
    IntegrationType,
)
from syntara.integrations.services.integration_service import IntegrationService


def _openshift_create(
    name: str = "Test OpenShift",
    credential_id: str | None = None,
    **kwargs: object,
) -> IntegrationCreate:
    """Helper to build an IntegrationCreate for OpenShift."""
    credential_id = credential_id or str(uuid4())
    defaults: dict[str, object] = {
        "name": name,
        "integration_type": IntegrationType.OPENSHIFT,
        "configuration": {
            "integration_type": "openshift",
            "base_url": "https://openshift.example.com:6443",
            "namespace": "syntara-workers",
        },
        "management_credential_id": credential_id,
    }
    defaults.update(kwargs)
    return IntegrationCreate(**defaults)


class TestClusterSyncOnCreate:
    """Tests for cluster sync during integration creation."""

    @pytest.mark.asyncio
    async def test_openshift_create_without_cluster_sync_service(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Cluster sync is optional; integration creation succeeds without it."""
        service = IntegrationService(test_db_session, test_user, cluster_sync_service=None)
        data = _openshift_create()

        result = await service.create_integration(data)

        assert result.name == "Test OpenShift"
        assert result.integration_type == IntegrationType.OPENSHIFT

    @pytest.mark.asyncio
    async def test_openshift_create_with_cluster_sync(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        credential_factory,
    ) -> None:
        """Creating an OpenShift integration syncs a cluster record."""
        # Setup credential
        ct = await credential_factory.create_type("HTTP Bearer Token")
        project = await credential_factory.create_project()
        cred = await credential_factory.create(ct, project, inputs={"token": "test-api-key"})

        # Mock cluster sync service
        mock_sync_service = AsyncMock()
        mock_sync_service.create_cluster = AsyncMock(return_value=MagicMock())

        service = IntegrationService(
            test_db_session,
            test_user,
            secret_service=credential_factory.secret_service,
            cluster_sync_service=mock_sync_service,
        )

        data = _openshift_create(credential_id=str(cred.id))
        result = await service.create_integration(data)

        assert result.name == "Test OpenShift"
        # Verify cluster sync was called
        mock_sync_service.create_cluster.assert_called_once()
        call_kwargs = mock_sync_service.create_cluster.call_args[1]
        assert call_kwargs["name"] == "Test OpenShift"
        assert call_kwargs["endpoint"] == "https://openshift.example.com:6443"
        assert call_kwargs["api_key"] == "test-api-key"
        assert call_kwargs["created_by"] == test_user.id
        assert "integration_id" in call_kwargs["labels"]
        assert "integration_name" in call_kwargs["labels"]

    @pytest.mark.asyncio
    async def test_openshift_create_without_credential(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Creating an OpenShift integration without credential still succeeds (sync skipped)."""
        from syntara.integrations.exceptions import IntegrationCredentialRequiredError

        mock_sync_service = AsyncMock()
        mock_sync_service.create_cluster = AsyncMock()

        service = IntegrationService(
            test_db_session,
            test_user,
            cluster_sync_service=mock_sync_service,
        )

        # No credential provided; should fail credential validation
        data = _openshift_create(credential_id=None)

        # IntegrationService validates credential requirement at create time
        with pytest.raises(IntegrationCredentialRequiredError):
            await service.create_integration(data)

    @pytest.mark.asyncio
    async def test_mcp_create_does_not_sync_cluster(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Creating a non-OpenShift integration does not sync clusters."""
        mock_sync_service = AsyncMock()

        service = IntegrationService(
            test_db_session,
            test_user,
            cluster_sync_service=mock_sync_service,
        )

        data = IntegrationCreate(
            name="Test MCP",
            integration_type=IntegrationType.MCP_SERVER,
            configuration={"integration_type": "mcp_server", "base_url": "http://localhost:8080"},
        )

        result = await service.create_integration(data)

        assert result.integration_type == IntegrationType.MCP_SERVER
        mock_sync_service.create_cluster.assert_not_called()

    @pytest.mark.asyncio
    async def test_cluster_sync_failure_does_not_fail_integration_create(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        credential_factory,
    ) -> None:
        """If cluster sync fails, integration creation still succeeds."""
        # Setup credential
        ct = await credential_factory.create_type("HTTP Bearer Token")
        project = await credential_factory.create_project()
        cred = await credential_factory.create(ct, project, inputs={"token": "test-api-key"})

        # Mock cluster sync service that raises an error
        mock_sync_service = AsyncMock()
        mock_sync_service.create_cluster = AsyncMock(side_effect=RuntimeError("Cluster sync failed"))

        service = IntegrationService(
            test_db_session,
            test_user,
            secret_service=credential_factory.secret_service,
            cluster_sync_service=mock_sync_service,
        )

        data = _openshift_create(credential_id=str(cred.id))

        # Integration creation should still succeed despite cluster sync failure
        result = await service.create_integration(data)
        assert result.name == "Test OpenShift"

    @pytest.mark.asyncio
    async def test_cluster_sync_with_missing_api_key_field(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        credential_factory,
    ) -> None:
        """If credential has no api_key/token, cluster sync is skipped gracefully."""
        # Setup credential with no api_key field
        ct = await credential_factory.create_type("HTTP Bearer Token")
        project = await credential_factory.create_project()
        cred = await credential_factory.create(ct, project, inputs={"some_other_field": "value"})

        mock_sync_service = AsyncMock()
        mock_sync_service.create_cluster = AsyncMock()

        service = IntegrationService(
            test_db_session,
            test_user,
            secret_service=credential_factory.secret_service,
            cluster_sync_service=mock_sync_service,
        )

        data = _openshift_create(credential_id=str(cred.id))
        result = await service.create_integration(data)

        # Integration creation succeeds, but cluster sync is not called
        assert result.name == "Test OpenShift"
        mock_sync_service.create_cluster.assert_not_called()


class TestClusterSyncOnDelete:
    """Tests for cluster sync during integration deletion."""

    @pytest.mark.asyncio
    async def test_openshift_delete_syncs_cluster(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        credential_factory,
    ) -> None:
        """Deleting an OpenShift integration requests cluster deletion."""
        # Create an integration first
        ct = await credential_factory.create_type("HTTP Bearer Token")
        project = await credential_factory.create_project()
        cred = await credential_factory.create(ct, project, inputs={"token": "test-api-key"})

        mock_sync_service = AsyncMock()
        mock_sync_service.create_cluster = AsyncMock(return_value=MagicMock())
        mock_sync_service.delete_cluster = AsyncMock(return_value=MagicMock())

        service = IntegrationService(
            test_db_session,
            test_user,
            secret_service=credential_factory.secret_service,
            cluster_sync_service=mock_sync_service,
        )

        # Create the integration
        data = _openshift_create(credential_id=str(cred.id))
        result = await service.create_integration(data)
        integration_id = result.id

        # Now delete it
        await service.delete_integration(integration_id)

        # Verify cluster sync delete was called
        mock_sync_service.delete_cluster.assert_called_once()
        call_kwargs = mock_sync_service.delete_cluster.call_args[1]
        assert call_kwargs["updated_by"] == test_user.id

    @pytest.mark.asyncio
    async def test_mcp_delete_does_not_sync_cluster(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Deleting a non-OpenShift integration does not sync clusters."""
        mock_sync_service = AsyncMock()

        service = IntegrationService(
            test_db_session,
            test_user,
            cluster_sync_service=mock_sync_service,
        )

        # Create an MCP integration
        data = IntegrationCreate(
            name="Test MCP",
            integration_type=IntegrationType.MCP_SERVER,
            configuration={"integration_type": "mcp_server", "base_url": "http://localhost:8080"},
        )
        result = await service.create_integration(data)

        # Delete it
        await service.delete_integration(result.id)

        # Cluster sync should not be called
        mock_sync_service.delete_cluster.assert_not_called()

    @pytest.mark.asyncio
    async def test_cluster_sync_delete_failure_does_not_fail_integration_delete(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        credential_factory,
    ) -> None:
        """If cluster sync delete fails, integration deletion still succeeds."""
        # Setup
        ct = await credential_factory.create_type("HTTP Bearer Token")
        project = await credential_factory.create_project()
        cred = await credential_factory.create(ct, project, inputs={"token": "test-api-key"})

        mock_sync_service = AsyncMock()
        mock_sync_service.create_cluster = AsyncMock(return_value=MagicMock())
        mock_sync_service.delete_cluster = AsyncMock(side_effect=RuntimeError("Delete failed"))

        service = IntegrationService(
            test_db_session,
            test_user,
            secret_service=credential_factory.secret_service,
            cluster_sync_service=mock_sync_service,
        )

        # Create and delete
        data = _openshift_create(credential_id=str(cred.id))
        result = await service.create_integration(data)

        # Delete should succeed despite cluster sync failure
        await service.delete_integration(result.id)

        # Verify the integration is actually deleted
        from syntara.integrations.exceptions import IntegrationNotFoundError

        with pytest.raises(IntegrationNotFoundError):
            await service.get_integration(result.id)
