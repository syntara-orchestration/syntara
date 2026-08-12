"""WebSocket connection lifecycle management.

This module provides general-purpose connection lifecycle management for WebSocket
connections, including health monitoring, state tracking, and multi-client coordination.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID, uuid4

import structlog

from syntara.core.constants import WebSocketConfig

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = structlog.stdlib.get_logger(__name__)


class ConnectionState(Enum):
    """WebSocket connection states."""

    CONNECTING = "connecting"  # Initial handshake in progress
    ACTIVE = "active"  # Successfully connected, consuming events
    RECONNECTING = "reconnecting"  # Temporary disconnect, attempting reconnection
    CLOSED = "closed"  # Connection terminated


@dataclass
class WebSocketConnectionInfo:
    """Information about an active WebSocket connection.

    Attributes:
        connection_id: Unique identifier for the connection
        channel: WebSocket channel/endpoint name
        client_ip: Client IP address
        websocket: WebSocket connection object (for closing stale connections)
        resource_id: Optional ID of the resource being accessed (e.g., invocation_id, session_id)
        user_agent: Client user agent string (optional)
        connected_at: Timestamp when connection was established
        last_activity_at: Last activity timestamp (message send/receive)
        metadata: Additional connection metadata (extensible for use-case specific data)
        is_active: Connection health status
        state: Current connection state

    """

    connection_id: UUID
    channel: str
    client_ip: str
    websocket: "WebSocket | None" = None
    resource_id: str | None = None
    user_agent: str | None = None
    connected_at: float = field(default_factory=time.time)
    last_activity_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    state: ConnectionState = ConnectionState.CONNECTING

    def update_activity(self) -> None:
        """Update the last activity timestamp."""
        self.last_activity_at = time.time()
        self.is_active = True

    def check_health(self, timeout_seconds: float = 14400) -> bool:
        """Check if connection is healthy based on last activity.

        Args:
            timeout_seconds: Timeout in seconds (default: 14400s = 4 hours)

        Returns:
            True if connection is healthy, False otherwise

        """
        time_since_activity = time.time() - self.last_activity_at
        if time_since_activity > timeout_seconds:
            self.is_active = False
            return False
        return True

    def update_metadata(self, key: str, value: Any) -> None:  # noqa: ANN401
        """Update connection metadata.

        Args:
            key: Metadata key
            value: Metadata value

        """
        self.metadata[key] = value

    def transition_to(self, new_state: ConnectionState) -> None:
        """Transition connection to a new state.

        Args:
            new_state: Target connection state

        """
        old_state = self.state
        self.state = new_state
        logger.debug(
            "Connection transitioned",
            connection_id=self.connection_id,
            old_state=old_state.value,
            new_state=new_state.value,
        )


class WebSocketConnectionLifecycleManager:
    """Manager for WebSocket connection lifecycle.

    Provides connection tracking, health monitoring, and multi-client coordination
    for any WebSocket use case.

    Features:
        - Connection state management (Connecting → Active → Reconnecting → Closed)
        - Health monitoring via activity tracking (4-hour timeout)
        - Multi-client support (multiple connections per resource)
        - Automatic cleanup of stale connections
        - Channel-based grouping
        - Extensible metadata support

    Examples:
        >>> manager = WebSocketConnectionLifecycleManager()
        >>> conn_id = manager.add_connection(
        ...     channel="invocations",
        ...     client_ip="192.168.1.1",
        ...     resource_id="550e8400-e29b-41d4-a716-446655440000",
        ...     user_agent="Mozilla/5.0"
        ... )
        >>> manager.activate_connection(conn_id)
        >>> manager.update_activity(conn_id)
        >>> manager.get_connections_for_resource("550e8400-...")
        [WebSocketConnectionInfo(...)]

    """

    _instance: ClassVar["WebSocketConnectionLifecycleManager | None"] = None
    _initialized: bool = False

    def __new__(cls) -> "WebSocketConnectionLifecycleManager":
        """Ensure singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the connection lifecycle manager.

        Note: Only initializes once due to singleton pattern.
        """
        # Only initialize once (singleton pattern)
        if self._initialized:
            return

        self._connections: dict[UUID, WebSocketConnectionInfo] = {}
        self._resource_connections: dict[str, set[UUID]] = {}  # resource_id -> set of connection_ids
        self._channel_connections: dict[str, set[UUID]] = {}  # channel -> set of connection_ids
        self._monitoring_task: asyncio.Task[None] | None = None
        self._initialized = True
        logger.info("WebSocketConnectionLifecycleManager initialized")

    def add_connection(
        self,
        channel: str,
        client_ip: str,
        websocket: "WebSocket | None" = None,
        resource_id: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UUID:
        """Add a new WebSocket connection.

        Args:
            channel: WebSocket channel/endpoint name
            client_ip: Client IP address
            websocket: WebSocket connection object (optional, can be set later)
            resource_id: Optional resource ID (e.g., invocation_id, session_id)
            user_agent: Client user agent string (optional)
            metadata: Optional metadata dict

        Returns:
            Connection ID (UUID)

        """
        connection_id = uuid4()

        connection_info = WebSocketConnectionInfo(
            connection_id=connection_id,
            channel=channel,
            client_ip=client_ip,
            websocket=websocket,
            resource_id=resource_id,
            user_agent=user_agent,
            metadata=metadata or {},
        )

        self._connections[connection_id] = connection_info

        # Track resource → connection mapping (if resource_id provided)
        if resource_id:
            if resource_id not in self._resource_connections:
                self._resource_connections[resource_id] = set()
            self._resource_connections[resource_id].add(connection_id)

        # Track channel → connection mapping
        if channel not in self._channel_connections:
            self._channel_connections[channel] = set()
        self._channel_connections[channel].add(connection_id)

        logger.info(
            "WebSocket connection added",
            connection_id=str(connection_id),
            channel=channel,
            resource_id=resource_id,
            client_ip=client_ip,
            state=ConnectionState.CONNECTING.value,
        )

        return connection_id

    def activate_connection(self, connection_id: UUID) -> None:
        """Transition connection to active state after successful handshake.

        Args:
            connection_id: Connection ID to activate

        """
        connection = self._connections.get(connection_id)
        if connection:
            connection.transition_to(ConnectionState.ACTIVE)
            logger.info("Connection activated", connection_id=connection_id)
        else:
            logger.warning("Attempted to activate non-existent connection", connection_id=connection_id)

    def remove_connection(self, connection_id: UUID, reason: str = "closed") -> None:
        """Remove a WebSocket connection.

        Args:
            connection_id: Connection ID to remove
            reason: Reason for removal (for logging)

        """
        connection = self._connections.pop(connection_id, None)

        if connection:
            # Update state to closed
            connection.transition_to(ConnectionState.CLOSED)

            # Remove from resource tracking
            if connection.resource_id and connection.resource_id in self._resource_connections:
                self._resource_connections[connection.resource_id].discard(connection_id)
                if not self._resource_connections[connection.resource_id]:
                    del self._resource_connections[connection.resource_id]

            # Remove from channel tracking
            if connection.channel in self._channel_connections:
                self._channel_connections[connection.channel].discard(connection_id)
                if not self._channel_connections[connection.channel]:
                    del self._channel_connections[connection.channel]

            duration = time.time() - connection.connected_at
            logger.info(
                "WebSocket connection removed",
                connection_id=str(connection_id),
                channel=connection.channel,
                resource_id=connection.resource_id,
                client_ip=connection.client_ip,
                duration_seconds=duration,
                reason=reason,
            )
        else:
            logger.warning("Attempted to remove non-existent connection", connection_id=connection_id)

    def update_activity(self, connection_id: UUID) -> None:
        """Update activity timestamp for a connection.

        Args:
            connection_id: Connection ID to update

        """
        connection = self._connections.get(connection_id)
        if connection:
            connection.update_activity()
        else:
            logger.warning("Attempted to update activity for non-existent connection", connection_id=connection_id)

    def update_metadata(self, connection_id: UUID, key: str, value: Any) -> None:  # noqa: ANN401
        """Update connection metadata.

        Args:
            connection_id: Connection ID
            key: Metadata key
            value: Metadata value

        """
        connection = self._connections.get(connection_id)
        if connection:
            connection.update_metadata(key, value)

    def get_connection(self, connection_id: UUID) -> WebSocketConnectionInfo | None:
        """Get connection information.

        Args:
            connection_id: Connection ID

        Returns:
            WebSocketConnectionInfo if found, None otherwise

        """
        return self._connections.get(connection_id)

    def get_connections_for_resource(self, resource_id: str) -> list[WebSocketConnectionInfo]:
        """Get all active connections for a resource.

        Args:
            resource_id: Resource ID (e.g., invocation_id)

        Returns:
            List of WebSocketConnectionInfo for the resource

        """
        connection_ids = self._resource_connections.get(resource_id, set())
        return [self._connections[conn_id] for conn_id in connection_ids if conn_id in self._connections]

    def get_connections_for_channel(self, channel: str) -> list[WebSocketConnectionInfo]:
        """Get all active connections for a channel.

        Args:
            channel: Channel name

        Returns:
            List of WebSocketConnectionInfo for the channel

        """
        connection_ids = self._channel_connections.get(channel, set())
        return [self._connections[conn_id] for conn_id in connection_ids if conn_id in self._connections]

    def get_active_connection_count(self) -> int:
        """Get total number of active connections.

        Returns:
            Number of active connections

        """
        return len(self._connections)

    def get_active_connection_count_for_resource(self, resource_id: str) -> int:
        """Get number of active connections for a resource.

        Args:
            resource_id: Resource ID

        Returns:
            Number of active connections for the resource

        """
        return len(self._resource_connections.get(resource_id, set()))

    def get_active_connection_count_for_channel(self, channel: str) -> int:
        """Get number of active connections for a channel.

        Args:
            channel: Channel name

        Returns:
            Number of active connections for the channel

        """
        return len(self._channel_connections.get(channel, set()))

    async def cleanup_stale_connections(self) -> int:
        """Clean up connections that haven't had activity in timeout period.

        Closes the WebSocket connection and removes from tracking.

        Returns:
            Number of connections cleaned up

        """
        stale_connections = []

        for connection_id, connection in self._connections.items():
            if not connection.check_health(WebSocketConfig.ACTIVITY_TIMEOUT):
                stale_connections.append((connection_id, connection))

        for connection_id, connection in stale_connections:
            # Close the WebSocket connection if available
            if connection.websocket:
                try:
                    await connection.websocket.close(code=1001, reason="Connection timeout")
                    logger.debug("Closed stale WebSocket connection", connection_id=connection_id)
                except Exception:
                    logger.exception("Error closing stale WebSocket connection", connection_id=connection_id)

            # Remove from lifecycle manager tracking
            self.remove_connection(connection_id, reason="timeout")

        if stale_connections:
            logger.warning("Cleaned up stale connections", stale_connection_count=len(stale_connections))

        return len(stale_connections)

    async def monitor_connections(self) -> None:
        """Background task to monitor connection health and cleanup stale connections.

        Runs cleanup every 30 seconds.
        """
        while True:
            try:
                # Cleanup stale connections
                cleaned = await self.cleanup_stale_connections()

                # Log metrics
                active_count = self.get_active_connection_count()
                if active_count > 0:
                    logger.debug("Active WebSocket connections", active_count=active_count)
                if cleaned > 0:
                    logger.info("Cleaned up stale WebSocket connections", cleaned_count=cleaned)

                await asyncio.sleep(WebSocketConfig.CLEANUP_INTERVAL)

            except Exception:
                logger.exception("Error in connection monitoring")
                await asyncio.sleep(WebSocketConfig.CLEANUP_INTERVAL)

    def start_monitoring(self) -> None:
        """Start the background connection monitoring task."""
        if self._monitoring_task is None or self._monitoring_task.done():
            self._monitoring_task = asyncio.create_task(self.monitor_connections())
            logger.info("Started WebSocket connection monitoring")
        else:
            logger.warning("Connection monitoring already running")

    def stop_monitoring(self) -> None:
        """Stop the background connection monitoring task."""
        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            logger.info("Stopped WebSocket connection monitoring")
        # Reset task reference after cancellation
        self._monitoring_task = None

    def clear_all(self) -> None:
        """Clear all connections.

        Warning: This is primarily for testing purposes.
        """
        count = len(self._connections)
        self._connections.clear()
        self._resource_connections.clear()
        self._channel_connections.clear()
        logger.warning("Cleared all connections", connection_count=count)


# Global singleton instance
_lifecycle_manager = WebSocketConnectionLifecycleManager()


def get_connection_lifecycle_manager() -> WebSocketConnectionLifecycleManager:
    """Get the global connection lifecycle manager instance.

    Returns:
        Singleton WebSocketConnectionLifecycleManager instance

    Examples:
        >>> manager = get_connection_lifecycle_manager()
        >>> conn_id = manager.add_connection(
        ...     channel="invocations",
        ...     client_ip="192.168.1.1",
        ...     resource_id="550e8400-..."
        ... )

    """
    return _lifecycle_manager
