"""Unit tests for ClusterSyncService."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from execution_plane.cluster.cluster_sync_service import ClusterSyncService
from execution_plane.models.cluster import Cluster, ClusterStatus


@pytest.fixture
def mock_registry():
    """Create a mock ClusterRegistry."""
    return AsyncMock()


@pytest.fixture
def mock_store():
    """Create a mock ClusterStore."""
    return AsyncMock()


@pytest.fixture
def cluster_sync_service(mock_registry, mock_store):
    """Create a ClusterSyncService with mocked dependencies."""
    return ClusterSyncService(mock_registry, mock_store)


class TestCreateCluster:
    """Tests for ClusterSyncService.create_cluster()."""

    @pytest.mark.asyncio
    async def test_create_cluster_success(self, cluster_sync_service, mock_registry):
        """Successfully creates a cluster via registry.register()."""
        cluster_id = uuid4()
        mock_cluster = MagicMock(spec=Cluster)
        mock_cluster.id = cluster_id
        mock_cluster.name = "test-cluster"
        mock_cluster.status = ClusterStatus.REGISTERING
        mock_registry.register = AsyncMock(return_value=mock_cluster)

        user_id = uuid4()
        result = await cluster_sync_service.create_cluster(
            name="test-cluster",
            endpoint="https://api.example.com:6443",
            api_key="secret-key",
            created_by=user_id,
            labels={"env": "test"},
        )

        assert result == mock_cluster
        mock_registry.register.assert_called_once_with(
            name="test-cluster",
            endpoint="https://api.example.com:6443",
            api_key="secret-key",
            created_by=user_id,
            labels={"env": "test"},
        )

    @pytest.mark.asyncio
    async def test_create_cluster_without_labels(self, cluster_sync_service, mock_registry):
        """Create cluster with no labels defaults to empty dict."""
        mock_cluster = MagicMock(spec=Cluster)
        mock_registry.register = AsyncMock(return_value=mock_cluster)

        user_id = uuid4()
        await cluster_sync_service.create_cluster(
            name="test-cluster",
            endpoint="https://api.example.com:6443",
            api_key="secret-key",
            created_by=user_id,
        )

        mock_registry.register.assert_called_once()
        call_kwargs = mock_registry.register.call_args[1]
        assert call_kwargs["labels"] == {}

    @pytest.mark.asyncio
    async def test_create_cluster_handles_registry_exception(self, cluster_sync_service, mock_registry):
        """Registry exceptions are propagated."""
        mock_registry.register = AsyncMock(side_effect=RuntimeError("Registry failed"))

        user_id = uuid4()
        with pytest.raises(RuntimeError, match="Registry failed"):
            await cluster_sync_service.create_cluster(
                name="test-cluster",
                endpoint="https://api.example.com:6443",
                api_key="secret-key",
                created_by=user_id,
            )


class TestUpdateCluster:
    """Tests for ClusterSyncService.update_cluster()."""

    @pytest.mark.asyncio
    async def test_update_cluster_endpoint_only(self, cluster_sync_service, mock_store):
        """Update cluster endpoint only."""
        cluster_id = uuid4()
        mock_cluster = MagicMock(spec=Cluster)
        mock_cluster.id = cluster_id
        mock_store.get = AsyncMock(return_value=mock_cluster)

        user_id = uuid4()
        result = await cluster_sync_service.update_cluster(
            cluster_id=cluster_id,
            endpoint="https://new-api.example.com:6443",
            updated_by=user_id,
        )

        # Currently, update is a no-op (returns cluster as-is)
        assert result == mock_cluster

    @pytest.mark.asyncio
    async def test_update_cluster_not_found(self, cluster_sync_service, mock_store):
        """Update returns None if cluster not found."""
        cluster_id = uuid4()
        mock_store.get = AsyncMock(return_value=None)

        result = await cluster_sync_service.update_cluster(
            cluster_id=cluster_id,
            endpoint="https://new-api.example.com:6443",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_update_cluster_no_updates(self, cluster_sync_service, mock_store):
        """Update with no fields returns cluster as-is."""
        cluster_id = uuid4()
        mock_cluster = MagicMock(spec=Cluster)
        mock_store.get = AsyncMock(return_value=mock_cluster)

        result = await cluster_sync_service.update_cluster(cluster_id=cluster_id)

        assert result == mock_cluster
        mock_store.get.assert_called_once_with(cluster_id)

    @pytest.mark.asyncio
    async def test_update_cluster_handles_exception(self, cluster_sync_service, mock_store):
        """Update exceptions are caught and None is returned."""
        cluster_id = uuid4()
        mock_store.get = AsyncMock(side_effect=RuntimeError("Store failed"))

        result = await cluster_sync_service.update_cluster(cluster_id=cluster_id)

        assert result is None


class TestDeleteCluster:
    """Tests for ClusterSyncService.delete_cluster()."""

    @pytest.mark.asyncio
    async def test_delete_cluster_success(self, cluster_sync_service, mock_store):
        """Successfully deletes (marks as draining) a cluster."""
        cluster_id = uuid4()
        mock_cluster = MagicMock(spec=Cluster)
        mock_cluster.id = cluster_id
        mock_cluster.status = ClusterStatus.DRAINING
        mock_store.request_delete = AsyncMock(return_value=mock_cluster)

        user_id = uuid4()
        result = await cluster_sync_service.delete_cluster(cluster_id=cluster_id, updated_by=user_id)

        assert result == mock_cluster
        mock_store.request_delete.assert_called_once_with(cluster_id, user_id)

    @pytest.mark.asyncio
    async def test_delete_cluster_not_found(self, cluster_sync_service, mock_store):
        """Delete returns None if cluster not found."""
        cluster_id = uuid4()
        from execution_plane.cluster.cluster_store import ClusterNotFoundError

        mock_store.request_delete = AsyncMock(side_effect=ClusterNotFoundError(cluster_id))

        user_id = uuid4()
        result = await cluster_sync_service.delete_cluster(cluster_id=cluster_id, updated_by=user_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_cluster_handles_exception(self, cluster_sync_service, mock_store):
        """Delete exceptions are caught and None is returned."""
        cluster_id = uuid4()
        mock_store.request_delete = AsyncMock(side_effect=RuntimeError("Delete failed"))

        user_id = uuid4()
        result = await cluster_sync_service.delete_cluster(cluster_id=cluster_id, updated_by=user_id)

        assert result is None
