"""WebSocket hook system for input/output interception.

This module provides a hook-based system for intercepting and processing
WebSocket messages. Hooks have default behaviors that can be overridden
per handler.
"""

from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import structlog

from syntara.core.websocket.schema_validator import ValidationError, validate_message

logger = structlog.stdlib.get_logger(__name__)


class WebSocketHooks:
    """Base class for WebSocket message hooks.

    Provides default implementations for all hooks. Handler modules can
    override specific hooks by implementing functions with matching names.
    """

    def __init__(self, spec_path: str | Path) -> None:
        """Initialize hooks with the AsyncAPI spec path.

        Args:
            spec_path: Path to the AsyncAPI specification file

        """
        self.spec_path = Path(spec_path)

    async def before_receive(self, data: dict[str, Any], message_type: str, channel: str) -> dict[str, Any]:
        """Validate and preprocess incoming message.

        Default behavior: Validate against AsyncAPI schema.

        Args:
            data: Raw incoming message data
            message_type: Expected message type name
            channel: Channel name

        Returns:
            Validated message data

        Raises:
            ValidationError: If validation fails

        """
        # Default: Schema validation
        validate_message(data, message_type, self.spec_path)
        logger.debug("Validated message on channel", message_type=message_type, channel=channel)
        return data

    async def after_receive(self, data: dict[str, Any], _channel: str) -> dict[str, Any]:
        """Process validated input message.

        Default behavior: Pass-through (no transformation).

        Args:
            data: Validated message data
            _channel: Channel name (unused in default implementation)

        Returns:
            Processed message data

        """
        return data

    async def before_send(self, response: dict[str, Any], _channel: str) -> dict[str, Any]:
        """Process response before sending to client.

        Default behavior: Add timestamp if not present.

        Args:
            response: Response data from handler
            _channel: Channel name (unused in default implementation)

        Returns:
            Processed response data ready to send

        """
        if "timestamp" not in response:
            response["timestamp"] = datetime.now(UTC).isoformat()
        return response

    async def on_validation_error(self, error: ValidationError, _channel: str) -> dict[str, Any]:
        """Format validation error as response.

        Default behavior: Standard error format with error type and message.

        Args:
            error: Validation error that occurred
            _channel: Channel name (unused in default implementation)

        Returns:
            Error response dict

        """
        return {
            "error": error.error_type,
            "message": error.message,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def on_handler_error(self, error: Exception, _channel: str) -> dict[str, Any]:
        """Format handler error as response.

        Default behavior: Standard error format for internal errors.

        Args:
            error: Exception that occurred in handler
            _channel: Channel name (unused in default implementation)

        Returns:
            Error response dict

        """
        return {
            "error": "INTERNAL_ERROR",
            "message": f"Handler error: {error!s}",
            "timestamp": datetime.now(UTC).isoformat(),
        }


def discover_hooks(handler_module: ModuleType, spec_path: str | Path) -> WebSocketHooks:
    """Discover and build hooks from a handler module.

    This function creates a WebSocketHooks instance and checks if the handler
    module has custom hook implementations. If found, they override the defaults.

    Args:
        handler_module: Handler module that may contain hook implementations
        spec_path: Path to the AsyncAPI specification

    Returns:
        WebSocketHooks instance with handler-specific overrides

    Examples:
        >>> import importlib
        >>> handler = importlib.import_module("syntara.ws.example")
        >>> hooks = discover_hooks(handler, "example.yaml")
        >>> # hooks.before_receive will use handler's version if defined

    """
    hooks = WebSocketHooks(spec_path)

    # Check for handler-specific hook overrides
    hook_methods = [
        "before_receive",
        "after_receive",
        "before_send",
        "on_validation_error",
        "on_handler_error",
    ]

    for hook_name in hook_methods:
        if hasattr(handler_module, hook_name):
            handler_hook = getattr(handler_module, hook_name)
            if callable(handler_hook):
                # Bind the handler's hook function to the hooks instance
                setattr(hooks, hook_name, handler_hook)
                logger.debug("Handler provides custom hook", hook_name=hook_name)

    return hooks


async def call_hook(
    hooks: WebSocketHooks,
    hook_name: str,
    *args: Any,  # noqa: ANN401
    **kwargs: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Call a hook method safely.

    Args:
        hooks: WebSocketHooks instance
        hook_name: Name of the hook to call
        *args: Positional arguments to pass to hook
        **kwargs: Keyword arguments to pass to hook

    Returns:
        Result from hook method

    """
    hook_method = getattr(hooks, hook_name)
    return await hook_method(*args, **kwargs)
