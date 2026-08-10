"""Tests for WebSocket connection lifecycle manager.

Simplified test suite focusing on:
- Health check business logic (healthy vs stale)
- Cleanup algorithm
- Multiple clients tracking for same resource
- Monitoring task lifecycle
- Periodic activity timestamp updates
"""

import asyncio
import time
from collections.abc import AsyncGenerator, Generator
from uuid import uuid4

import pytest
from orchestrator_test_sdk.e2e import async_poll_for

from syntara.core.constants import WebSocketConfig
from syntara.core.websocket.manager import (
    WebSocketConnectionInfo,
    WebSocketConnectionLifecycleManager,
)


class TestWebSocketConnectionHealth:
    """Tests for connection health check business logic."""

    def test_check_health_healthy(self) -> None:
        """Test health check returns True for healthy connection."""
        info = WebSocketConnectionInfo(
            connection_id=uuid4(),
            channel="test",
            client_ip="192.168.1.1",
        )

        assert info.check_health(timeout_seconds=60) is True
        assert info.is_active is True

    def test_check_health_stale(self) -> None:
        """Test health check returns False and marks inactive for stale connection."""
        info = WebSocketConnectionInfo(
            connection_id=uuid4(),
            channel="test",
            client_ip="192.168.1.1",
        )

        # Set last_activity_at to old timestamp
        info.last_activity_at = time.time() - 100  # 100 seconds ago

        assert info.check_health(timeout_seconds=60) is False
        assert info.is_active is False


class TestWebSocketConnectionLifecycleManager:
    """Tests for WebSocketConnectionLifecycleManager business logic."""

    @pytest.fixture(autouse=True)
    def _setup_and_teardown(self) -> Generator[None, None, None]:
        """Clear manager state before and after each test."""
        manager = WebSocketConnectionLifecycleManager()
        manager.clear_all()
        yield
        manager.clear_all()

    @pytest.mark.asyncio
    async def test_cleanup_stale_connections(self) -> None:
        """Test cleanup removes stale connections but keeps fresh ones."""
        manager = WebSocketConnectionLifecycleManager()

        # Create fresh connection
        fresh_conn_id = manager.add_connection(
            channel="invocations",
            resource_id="fresh-resource",
            client_ip="192.168.1.1",
        )

        # Create stale connection
        stale_conn_id = manager.add_connection(
            channel="invocations",
            resource_id="stale-resource",
            client_ip="192.168.1.2",
        )

        # Make the stale connection old
        stale_info = manager.get_connection(stale_conn_id)
        if stale_info:
            stale_info.last_activity_at = time.time() - 15000  # >4 hours to exceed ACTIVITY_TIMEOUT

        # Cleanup stale connections
        removed = await manager.cleanup_stale_connections()

        # Verify stale removed, fresh kept
        assert removed == 1
        assert manager.get_connection(fresh_conn_id) is not None
        assert manager.get_connection(stale_conn_id) is None

    @pytest.mark.asyncio
    async def test_cleanup_stale_connections_closes_websocket(self) -> None:
        """Test that cleanup actually closes the WebSocket connection."""
        from unittest.mock import AsyncMock, MagicMock

        manager = WebSocketConnectionLifecycleManager()

        # Create mock WebSocket
        mock_websocket = MagicMock()
        mock_websocket.close = AsyncMock()

        # Add connection with WebSocket
        conn_id = manager.add_connection(
            channel="test",
            client_ip="192.168.1.1",
            websocket=mock_websocket,
        )

        # Make it stale
        conn_info = manager.get_connection(conn_id)
        if conn_info:
            conn_info.last_activity_at = time.time() - 15000  # >4 hours to exceed ACTIVITY_TIMEOUT

        # Cleanup
        removed = await manager.cleanup_stale_connections()

        # Verify WebSocket.close() was called with correct parameters
        assert removed == 1
        mock_websocket.close.assert_called_once_with(code=1001, reason="Connection timeout")
        assert manager.get_connection(conn_id) is None

    def test_multiple_clients_same_resource(self) -> None:
        """Test multiple clients can track the same resource."""
        manager = WebSocketConnectionLifecycleManager()

        resource_id = str(uuid4())

        # Add two connections for same resource
        conn_id1 = manager.add_connection(
            channel="invocations",
            resource_id=resource_id,
            client_ip="192.168.1.1",
        )

        conn_id2 = manager.add_connection(
            channel="invocations",
            resource_id=resource_id,
            client_ip="192.168.1.2",
        )

        # Both connections should be tracked for the resource
        assert manager.get_active_connection_count_for_resource(resource_id) == 2

        connections = manager.get_connections_for_resource(resource_id)
        assert len(connections) == 2
        assert conn_id1 in [c.connection_id for c in connections]
        assert conn_id2 in [c.connection_id for c in connections]


class TestMonitoringTaskLifecycle:
    """Tests for monitoring task start/stop lifecycle."""

    @pytest.fixture(autouse=True)
    async def _setup_and_teardown(self) -> AsyncGenerator[None, None]:
        """Clear manager state and stop monitoring before and after each test."""
        manager = WebSocketConnectionLifecycleManager()

        # Ensure monitoring is stopped and task is cancelled
        manager.stop_monitoring()
        if manager._monitoring_task and not manager._monitoring_task.done():
            try:
                await asyncio.wait_for(manager._monitoring_task, timeout=2.0)
            except (TimeoutError, asyncio.CancelledError):
                pass

        manager.clear_all()

        yield

        # Cleanup after test
        manager.stop_monitoring()
        if manager._monitoring_task and not manager._monitoring_task.done():
            try:
                await asyncio.wait_for(manager._monitoring_task, timeout=2.0)
            except (TimeoutError, asyncio.CancelledError):
                pass

        manager.clear_all()

    @pytest.mark.asyncio
    async def test_start_monitoring_creates_task(self) -> None:
        """Test that start_monitoring creates a background task."""
        manager = WebSocketConnectionLifecycleManager()

        # Start monitoring
        manager.start_monitoring()

        # Verify task was created
        assert manager._monitoring_task is not None
        assert not manager._monitoring_task.done()

        # Clean up
        task = manager._monitoring_task
        manager.stop_monitoring()
        if task:
            await async_poll_for(lambda: task.done(), description="monitoring task to finish")

    @pytest.mark.asyncio
    async def test_stop_monitoring_cancels_task(self) -> None:
        """Test that stop_monitoring cancels the background task."""
        manager = WebSocketConnectionLifecycleManager()

        # Start and then stop monitoring
        manager.start_monitoring()
        task = manager._monitoring_task
        assert task is not None
        assert not task.done()

        manager.stop_monitoring()

        # Give event loop time to process cancellation
        await asyncio.sleep(0)

        # Task reference should be reset to None
        assert manager._monitoring_task is None

        # Original task should be cancelled
        assert task.done()
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_start_monitoring_twice_does_not_create_duplicate_task(self) -> None:
        """Test that calling start_monitoring twice doesn't create duplicate tasks."""
        manager = WebSocketConnectionLifecycleManager()

        # Start monitoring twice
        manager.start_monitoring()
        first_task = manager._monitoring_task

        manager.start_monitoring()
        second_task = manager._monitoring_task

        # Should be the same task
        assert first_task is second_task

        # Clean up
        task = first_task
        manager.stop_monitoring()
        if task:
            await async_poll_for(lambda: task.done(), description="monitoring task to finish")

    @pytest.mark.asyncio
    async def test_monitoring_task_runs_cleanup_periodically(self) -> None:
        """Test that monitoring task runs cleanup on stale connections."""
        manager = WebSocketConnectionLifecycleManager()

        # Override cleanup interval for faster testing
        original_interval = WebSocketConfig.CLEANUP_INTERVAL
        WebSocketConfig.CLEANUP_INTERVAL = 1  # 1 second for testing

        try:
            # Create a stale connection
            conn_id = manager.add_connection(
                channel="test",
                client_ip="192.168.1.1",
                resource_id="test-resource",
            )

            # Make it stale
            conn_info = manager.get_connection(conn_id)
            if conn_info:
                conn_info.last_activity_at = time.time() - 15000  # >4 hours to exceed ACTIVITY_TIMEOUT

            # Start monitoring
            manager.start_monitoring()

            # Poll until the stale connection is cleaned up
            await async_poll_for(
                lambda: manager.get_connection(conn_id) is None,
                timeout=5.0,
                description="stale connection to be cleaned up",
            )

        finally:
            # Restore original interval
            WebSocketConfig.CLEANUP_INTERVAL = original_interval
            manager.stop_monitoring()


class TestActivityTimestampUpdates:
    """Tests for activity timestamp update functionality."""

    @pytest.fixture(autouse=True)
    def _setup_and_teardown(self) -> Generator[None, None, None]:
        """Clear manager state before and after each test."""
        manager = WebSocketConnectionLifecycleManager()
        manager.clear_all()
        yield
        manager.clear_all()

    def test_update_activity_refreshes_timestamp(self) -> None:
        """Test that update_activity refreshes the last_activity_at timestamp."""
        manager = WebSocketConnectionLifecycleManager()

        conn_id = manager.add_connection(
            channel="test",
            client_ip="192.168.1.1",
        )

        # Get initial timestamp
        conn_info = manager.get_connection(conn_id)
        assert conn_info is not None
        initial_activity = conn_info.last_activity_at

        # Wait a bit
        time.sleep(0.1)

        # Update activity
        manager.update_activity(conn_id)

        # Verify timestamp was updated
        updated_info = manager.get_connection(conn_id)
        assert updated_info is not None
        assert updated_info.last_activity_at > initial_activity

    def test_update_activity_marks_connection_active(self) -> None:
        """Test that update_activity marks connection as active."""
        manager = WebSocketConnectionLifecycleManager()

        conn_id = manager.add_connection(
            channel="test",
            client_ip="192.168.1.1",
        )

        # Make connection inactive
        conn_info = manager.get_connection(conn_id)
        if conn_info:
            conn_info.is_active = False
            conn_info.last_activity_at = time.time() - 15000  # >4 hours to exceed ACTIVITY_TIMEOUT

        # Update activity
        manager.update_activity(conn_id)

        # Verify connection is now active
        updated_info = manager.get_connection(conn_id)
        assert updated_info is not None
        assert updated_info.is_active is True

    @pytest.mark.asyncio
    async def test_update_activity_prevents_stale_cleanup(self) -> None:
        """Test that updating activity prevents connection from being marked stale."""
        manager = WebSocketConnectionLifecycleManager()

        conn_id = manager.add_connection(
            channel="test",
            client_ip="192.168.1.1",
        )

        # Update activity regularly to keep connection alive
        for _ in range(3):
            await asyncio.sleep(0.05)
            manager.update_activity(conn_id)

        # Run cleanup
        cleaned = await manager.cleanup_stale_connections()

        # Connection should NOT be cleaned up
        assert cleaned == 0
        assert manager.get_connection(conn_id) is not None
