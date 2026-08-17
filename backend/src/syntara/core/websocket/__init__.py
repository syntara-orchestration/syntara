"""WebSocket core functionality for Syntara.

This package provides dynamic WebSocket message handling using AsyncAPI specifications.
Uses a hook-based system for message validation and processing with plain Python dicts.
"""

from syntara.core.websocket.connection import (
    ConnectionInfo,
    WebSocketConnectionManager,
    get_connection_manager,
)
from syntara.core.websocket.endpoint_factory import (
    create_websocket_endpoint,
    scan_handler_specs,
)
from syntara.core.websocket.hooks import WebSocketHooks, discover_hooks
from syntara.core.websocket.manager import (
    ConnectionState,
    WebSocketConnectionInfo,
    WebSocketConnectionLifecycleManager,
    get_connection_lifecycle_manager,
)
from syntara.core.websocket.schema_validator import (
    ValidationError,
    clear_validator_cache,
    validate_message,
)

__all__ = [
    "ConnectionInfo",
    "ConnectionState",
    "ValidationError",
    "WebSocketConnectionInfo",
    "WebSocketConnectionLifecycleManager",
    "WebSocketConnectionManager",
    "WebSocketHooks",
    "clear_validator_cache",
    "create_websocket_endpoint",
    "discover_hooks",
    "get_connection_lifecycle_manager",
    "get_connection_manager",
    "scan_handler_specs",
    "validate_message",
]
