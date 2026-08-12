"""Channel validation for WebSocket handlers.

This module validates the mapping between AsyncAPI channel definitions and
Python handler functions (handle_<name> and on_connect_<name>).
"""

import inspect
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import structlog

from .utils import is_receive_only_channel, normalize_channel_name

# Re-export for external use
__all__ = [
    "ChannelValidationResult",
    "check_missing_handlers",
    "check_orphaned_handlers",
    "get_handler_function_names",
    "get_server_pathname",
    "is_snake_case",
    "normalize_channel_name",
    "validate_all_components",
    "validate_channel_addresses",
    "validate_channel_mappings",
    "validate_naming_convention",
]

logger = structlog.stdlib.get_logger(__name__)


def get_server_pathname(spec: dict[str, Any]) -> str:
    """Extract pathname from AsyncAPI server configuration.

    The pathname is prepended to all channel addresses. For example, if pathname
    is "/api/v1", channel addresses become "/api/v1/ws/component/v1/channel".

    Args:
        spec: AsyncAPI specification dictionary

    Returns:
        Pathname from servers.development.pathname, or empty string if not present

    Examples:
        >>> spec = {"servers": {"development": {"pathname": "/api/v1"}}}
        >>> get_server_pathname(spec)
        '/api/v1'

        >>> spec = {"servers": {"development": {}}}
        >>> get_server_pathname(spec)
        ''

    """
    try:
        servers = spec.get("servers", {})
        development = servers.get("development", {})
        pathname = development.get("pathname", "")
        return pathname.rstrip("/") if pathname else ""  # Remove trailing slash
    except (AttributeError, TypeError):
        return ""


@dataclass
class ChannelValidationResult:
    """Results from channel validation."""

    component_name: str
    spec_path: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    channels_validated: int = 0
    handlers_validated: int = 0

    @property
    def is_valid(self) -> bool:
        """Check if validation passed without errors.

        Returns:
            True if no errors were found

        """
        return len(self.errors) == 0

    def add_error(self, message: str) -> None:
        """Add a validation error.

        Args:
            message: Error message

        """
        self.errors.append(message)
        logger.error("Validation error in component", component=self.component_name, message=message)

    def add_warning(self, message: str) -> None:
        """Add a validation warning.

        Args:
            message: Warning message

        """
        self.warnings.append(message)
        logger.warning("Validation warning in component", component=self.component_name, message=message)


def is_snake_case(name: str) -> bool:
    """Check if a name follows snake_case convention.

    Args:
        name: Name to check

    Returns:
        True if name is in snake_case format

    Examples:
        >>> is_snake_case('agent_events')
        True
        >>> is_snake_case('agent-events')
        False
        >>> is_snake_case('coffee')
        True

    """
    # Snake case: lowercase letters, numbers, and underscores only
    return bool(re.match(r"^[a-z][a-z0-9_]*$", name))


def get_handler_function_names(module: ModuleType) -> dict[str, list[str]]:
    """Extract handler and on_connect function names from a module.

    Args:
        module: Module to inspect

    Returns:
        Dictionary with keys 'handlers' and 'on_connect', each containing
        a list of extracted channel names (without handle_/on_connect_ prefix)

    Examples:
        >>> module = ...  # Module with handle_coffee, on_connect_chat, etc.
        >>> get_handler_function_names(module)
        {'handlers': ['coffee'], 'on_connect': ['chat']}

    """
    handlers = []
    on_connect = []

    for name, obj in inspect.getmembers(module):
        if not inspect.isfunction(obj) and not inspect.iscoroutinefunction(obj):
            continue

        if name.startswith("handle_"):
            channel_name = name[len("handle_") :]
            handlers.append(channel_name)
        elif name.startswith("on_connect_"):
            channel_name = name[len("on_connect_") :]
            on_connect.append(channel_name)

    return {"handlers": handlers, "on_connect": on_connect}


def validate_naming_convention(channels: dict[str, Any], result: ChannelValidationResult) -> None:
    """Validate that channel names follow snake_case convention.

    Args:
        channels: Dictionary of channel definitions from AsyncAPI spec
        result: Validation result to update with errors

    """
    for channel_name in channels:
        if not is_snake_case(channel_name):
            normalized = normalize_channel_name(channel_name)
            result.add_error(f"Channel '{channel_name}' should be '{normalized}' (snake_case) in '{result.spec_path}'")


def check_missing_handlers(
    channels: dict[str, Any],
    handler_functions: dict[str, list[str]],
    spec: dict[str, Any],
    result: ChannelValidationResult,
) -> None:
    """Check for channels that don't have corresponding handler functions.

    For receive-only channels, missing handlers are not a problem since they
    only send events via on_connect handler.

    Args:
        channels: Dictionary of channel definitions from AsyncAPI spec
        handler_functions: Dictionary of discovered handler function names
        spec: AsyncAPI specification dictionary (for receive-only detection)
        result: Validation result to update with warnings

    """
    handler_names = set(handler_functions["handlers"])

    for channel_name in channels:
        normalized_name = normalize_channel_name(channel_name)

        if normalized_name not in handler_names:
            # Check if this is a receive-only channel
            is_receive_only = is_receive_only_channel(spec, channel_name)

            if is_receive_only:
                # Info message instead of warning for receive-only channels
                logger.info(
                    "No handler for receive-only channel (not required, events sent via on_connect)",
                    channel=channel_name,
                )
            else:
                # Warning for bidirectional channels (existing behavior)
                result.add_warning(
                    f"Missing handler 'handle_{normalized_name}' for channel "
                    f"'{channel_name}' in '{result.spec_path}' (will use default handler)"
                )


def check_orphaned_handlers(
    channels: dict[str, Any],
    handler_functions: dict[str, list[str]],
    handler_module: ModuleType,
    result: ChannelValidationResult,
) -> None:
    """Check for handler/on_connect functions without corresponding channels.

    Args:
        channels: Dictionary of channel definitions from AsyncAPI spec
        handler_functions: Dictionary of discovered handler function names
        handler_module: Handler module to extract filename from
        result: Validation result to update with errors

    """
    # Get all normalized channel names from spec
    channel_names = {normalize_channel_name(name) for name in channels}

    # Extract module filename for error reporting
    module_file = getattr(handler_module, "__file__", None)
    module_name = Path(module_file).name if module_file else handler_module.__name__

    # Check for orphaned handle_* functions
    for handler_name in handler_functions["handlers"]:
        if handler_name not in channel_names:
            result.add_error(
                f"Orphaned handler 'handle_{handler_name}' in '{module_name}' - "
                f"no channel '{handler_name}' in '{result.spec_path}'"
            )

    # Check for orphaned on_connect_* functions
    for on_connect_name in handler_functions["on_connect"]:
        if on_connect_name not in channel_names:
            result.add_error(
                f"Orphaned handler 'on_connect_{on_connect_name}' in '{module_name}' - "
                f"no channel '{on_connect_name}' in '{result.spec_path}'"
            )


def validate_channel_addresses(
    spec: dict[str, Any], component_name: str, channels: dict[str, Any], result: ChannelValidationResult
) -> None:
    """Validate that channel addresses follow the expected format.

    Supports:
    - Optional pathname prefix from servers section
    - Path variables like {invocation_id} in addresses

    Expected format (without pathname):
      /ws/{component_name}/v1/{channel_name}[/{path_variables}...]

    Expected format (with pathname):
      {pathname}/ws/{component_name}/v1/{channel_name}[/{path_variables}...]

    Args:
        spec: AsyncAPI specification dictionary
        component_name: Name of the component (e.g., 'example')
        channels: Dictionary of channel definitions from AsyncAPI spec
        result: Validation result to update with errors

    Examples:
        >>> # Valid: channel 'coffee' with address '/ws/example/v1/coffee'
        >>> # Valid: channel 'invocations' with address '/ws/example/v1/invocations/{id}'
        >>> # Invalid: channel 'coffee' with address '/ws/example_test/v1/coffee'

    """
    # Extract optional pathname from servers section
    pathname = get_server_pathname(spec)

    logger.info("Validating channels for component", channel_count=len(channels), component=component_name)
    if pathname:
        logger.info("Using pathname prefix", pathname=pathname)

    for channel_name, channel_def in channels.items():
        # Get the address from the channel definition
        address = channel_def.get("address", "")

        if not address:
            result.add_error(f"Channel '{channel_name}' in '{result.spec_path}' is missing 'address' field")
            continue

        # Build expected address using normalized channel name with optional pathname
        normalized_channel = normalize_channel_name(channel_name)
        expected_address = f"{pathname}/ws/{component_name}/v1/{normalized_channel}"

        # Strip path variables from actual address for comparison
        # Pattern: /{anything_in_braces} → removed
        # Example: /invocations/{id}/status/{status_id} → /invocations/status
        base_address = re.sub(r"\{[^}]+\}", "", address)

        logger.debug("Validating channel", channel=channel_name)
        logger.debug("Expected prefix", expected_address=expected_address)
        logger.debug("Actual address", address=address)
        logger.debug("Base (without variables)", base_address=base_address)

        # Check if base address starts with expected format (prefix match)
        # This allows additional path segments after the channel name
        # Examples:
        #   - /ws/component/v1/channel ✓
        #   - /ws/component/v1/channel/{id} ✓
        #   - /ws/component/v1/channel/{id}/status ✓
        if not base_address.startswith(expected_address):
            result.add_error(
                f"Channel '{channel_name}' address mismatch in '{result.spec_path}'\n"
                f"  Expected to start with: {expected_address}\n"
                f"  Got: {address}\n"
                f"  (Base path after removing variables: {base_address})"
            )
        else:
            logger.debug("Address valid")


def validate_channel_mappings(
    component_name: str, spec: dict[str, Any], spec_path: str, handler_module: ModuleType
) -> ChannelValidationResult:
    """Validate channel mappings between AsyncAPI spec and handler module.

    Performs comprehensive validation including:
    - Channel naming conventions (snake_case)
    - Channel address format (must match /ws/{component}/v1/{channel})
    - Orphaned handlers (handlers without channels)
    - Missing handlers (channels without handlers)

    Args:
        component_name: Name of the component (e.g., 'example')
        spec: Loaded AsyncAPI specification
        spec_path: Path to the spec file for error reporting
        handler_module: Loaded handler module to validate

    Returns:
        ChannelValidationResult with all validation errors and warnings

    """
    result = ChannelValidationResult(component_name=component_name, spec_path=spec_path)

    # Extract channels from spec
    channels = spec.get("channels", {})
    result.channels_validated = len(channels)

    if not channels:
        result.add_warning(f"No channels defined in '{spec_path}'")
        return result

    # Get all handler and on_connect functions from module
    handler_functions = get_handler_function_names(handler_module)
    result.handlers_validated = len(handler_functions["handlers"]) + len(handler_functions["on_connect"])

    # Run validations
    validate_naming_convention(channels, result)
    validate_channel_addresses(spec, component_name, channels, result)
    check_missing_handlers(channels, handler_functions, spec, result)
    check_orphaned_handlers(channels, handler_functions, handler_module, result)

    return result


def validate_all_components(
    specs: dict[str, dict[str, Any]], handler_modules: dict[str, ModuleType]
) -> list[ChannelValidationResult]:
    """Validate all components' channel mappings.

    Args:
        specs: Dictionary mapping component names to AsyncAPI specs
        handler_modules: Dictionary mapping component names to handler modules

    Returns:
        List of validation results for all components

    """
    results = []

    for component_name, spec in specs.items():
        handler_module = handler_modules.get(component_name)
        if not handler_module:
            logger.warning("No handler module found for component", component=component_name)
            continue

        # Get spec path for error reporting
        spec_path = f"{component_name}.yaml"

        result = validate_channel_mappings(
            component_name=component_name, spec=spec, spec_path=spec_path, handler_module=handler_module
        )
        results.append(result)

    return results
