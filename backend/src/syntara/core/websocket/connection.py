"""WebSocket connection management.

This module provides connection tracking and lifecycle management for WebSocket connections.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar

import structlog

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class ConnectionInfo:
    """Information about an active WebSocket connection.

    Attributes:
        connection_id: Unique identifier for the connection
        client_address: Client IP address and port
        channel: WebSocket channel name (e.g., "hello")
        connected_at: Timestamp when connection was established

    """

    connection_id: str
    client_address: str
    channel: str
    connected_at: datetime


class WebSocketConnectionManager:
    """Manager for tracking active WebSocket connections.

    This class maintains an in-memory registry of active connections and provides
    methods for connection lifecycle management with structlog.

    Examples:
        >>> manager = WebSocketConnectionManager()
        >>> manager.add_connection("conn-123", "192.168.1.1:54321", "hello")
        >>> manager.get_active_count()
        1
        >>> manager.remove_connection("conn-123")
        >>> manager.get_active_count()
        0

    """

    _instance: ClassVar["WebSocketConnectionManager | None"] = None
    _initialized: bool = False

    def __new__(cls) -> "WebSocketConnectionManager":
        """Ensure singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the connection manager.

        Note: Only initializes once due to singleton pattern.
        """
        # Only initialize once (singleton pattern)
        if self._initialized:
            return

        self._connections: dict[str, ConnectionInfo] = {}
        self._initialized = True
        logger.info("WebSocket connection manager initialized")

    def add_connection(self, connection_id: str, client_address: str, channel: str) -> None:
        """Add a new active connection.

        Args:
            connection_id: Unique identifier for the connection
            client_address: Client IP address and port (e.g., "192.168.1.1:54321")
            channel: WebSocket channel name (e.g., "hello")

        Examples:
            >>> manager = WebSocketConnectionManager()
            >>> manager.add_connection("conn-123", "192.168.1.1:54321", "hello")

        """
        connection_info = ConnectionInfo(
            connection_id=connection_id,
            client_address=client_address,
            channel=channel,
            connected_at=datetime.now(UTC),
        )

        self._connections[connection_id] = connection_info

        logger.info(
            "WebSocket connection established",
            connection_id=connection_id,
            client_address=client_address,
            channel=channel,
            timestamp=connection_info.connected_at.isoformat(),
        )

    def remove_connection(self, connection_id: str) -> None:
        """Remove an active connection.

        Args:
            connection_id: Unique identifier for the connection to remove

        Examples:
            >>> manager = WebSocketConnectionManager()
            >>> manager.add_connection("conn-123", "192.168.1.1:54321", "hello")
            >>> manager.remove_connection("conn-123")

        """
        connection_info = self._connections.pop(connection_id, None)

        if connection_info:
            duration = (datetime.now(UTC) - connection_info.connected_at).total_seconds()
            logger.info(
                "WebSocket connection closed",
                connection_id=connection_id,
                client_address=connection_info.client_address,
                channel=connection_info.channel,
                duration_seconds=duration,
                timestamp=datetime.now(UTC).isoformat(),
            )
        else:
            logger.warning(
                "Attempted to remove non-existent connection",
                connection_id=connection_id,
            )

    def get_active_count(self) -> int:
        """Get the number of active connections.

        Returns:
            Number of currently active connections

        Examples:
            >>> manager = WebSocketConnectionManager()
            >>> manager.get_active_count()
            0
            >>> manager.add_connection("conn-123", "192.168.1.1:54321", "hello")
            >>> manager.get_active_count()
            1

        """
        return len(self._connections)

    def get_active_count_by_channel(self, channel: str) -> int:
        """Get the number of active connections for a specific channel.

        Args:
            channel: WebSocket channel name

        Returns:
            Number of active connections for the specified channel

        Examples:
            >>> manager = WebSocketConnectionManager()
            >>> manager.add_connection("conn-123", "192.168.1.1:54321", "hello")
            >>> manager.add_connection("conn-456", "192.168.1.2:54322", "echo")
            >>> manager.get_active_count_by_channel("hello")
            1

        """
        return sum(1 for conn in self._connections.values() if conn.channel == channel)

    def get_active_count_by_client(self, client_address: str) -> int:
        """Get the number of active connections for a specific client.

        Args:
            client_address: Client IP address (without port)

        Returns:
            Number of active connections for the specified client

        Examples:
            >>> manager = WebSocketConnectionManager()
            >>> manager.add_connection("conn-123", "192.168.1.1:54321", "hello")
            >>> manager.add_connection("conn-456", "192.168.1.1:54322", "echo")
            >>> manager.get_active_count_by_client("192.168.1.1")
            2

        """
        # Extract IP address from client_address (remove port)
        client_ip = client_address.rsplit(":", maxsplit=1)[0] if ":" in client_address else client_address
        return sum(
            1 for conn in self._connections.values() if conn.client_address.rsplit(":", maxsplit=1)[0] == client_ip
        )

    def get_connection_info(self, connection_id: str) -> ConnectionInfo | None:
        """Get information about a specific connection.

        Args:
            connection_id: Unique identifier for the connection

        Returns:
            ConnectionInfo if found, None otherwise

        Examples:
            >>> manager = WebSocketConnectionManager()
            >>> manager.add_connection("conn-123", "192.168.1.1:54321", "hello")
            >>> info = manager.get_connection_info("conn-123")
            >>> info.channel
            'hello'

        """
        return self._connections.get(connection_id)

    def clear_all(self) -> None:
        """Clear all connections.

        Warning: This is primarily for testing purposes.
        """
        count = len(self._connections)
        self._connections.clear()
        logger.warning("Cleared all connections", count=count)


# Global singleton instance
_manager = WebSocketConnectionManager()


def get_connection_manager() -> WebSocketConnectionManager:
    """Get the global connection manager instance.

    Returns:
        Singleton WebSocketConnectionManager instance

    Examples:
        >>> manager = get_connection_manager()
        >>> manager.add_connection("conn-123", "192.168.1.1:54321", "hello")

    """
    return _manager
