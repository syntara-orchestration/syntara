"""WebSocket endpoint bootstrap interceptor system.

This module provides a flexible interceptor pattern for hooking into the
WebSocket endpoint creation lifecycle during application bootstrap.
"""

from typing import TYPE_CHECKING, Any

import structlog

from syntara.core.websocket import channel_validator
from syntara.core.websocket.endpoint_factory import _HANDLER_MODULE_CACHE

if TYPE_CHECKING:
    from types import ModuleType

    from syntara.core.websocket.channel_validator import ChannelValidationResult

logger = structlog.stdlib.get_logger(__name__)


class WebSocketInterceptor:
    """Base class for WebSocket bootstrap interceptors.

    Interceptors can hook into various phases of the WebSocket endpoint
    creation lifecycle to perform validation, logging, metrics, or other
    cross-cutting concerns.
    """

    def on_bootstrap_start(self, specs: dict[str, Any]) -> None:
        """Handle WebSocket bootstrap start event.

        Args:
            specs: Dictionary mapping component names to their loaded AsyncAPI specs

        """

    def before_endpoint_creation(self, component_name: str, channel_name: str, channel_config: dict[str, Any]) -> None:
        """Handle event before WebSocket endpoint creation.

        Args:
            component_name: Name of the component (e.g., 'example')
            channel_name: Name of the channel (e.g., 'chat')
            channel_config: Channel configuration from AsyncAPI spec

        """

    def after_endpoint_creation(
        self, component_name: str, channel_name: str, endpoint: object, *, success: bool, error: Exception | None = None
    ) -> None:
        """Handle event after WebSocket endpoint creation attempt.

        Args:
            component_name: Name of the component
            channel_name: Name of the channel
            endpoint: The created endpoint (if successful)
            success: Whether endpoint creation succeeded
            error: Exception raised during creation (if any)

        """

    def on_bootstrap_complete(self, results: dict[str, Any]) -> None:
        """Handle WebSocket bootstrap completion event.

        Args:
            results: Summary of bootstrap results including successes and failures

        """


class InterceptorRegistry:
    """Registry for managing and executing WebSocket interceptors."""

    def __init__(self) -> None:
        """Initialize the interceptor registry."""
        self._interceptors: list[WebSocketInterceptor] = []

    def register(self, interceptor: WebSocketInterceptor) -> None:
        """Register an interceptor.

        Args:
            interceptor: The interceptor to register

        """
        self._interceptors.append(interceptor)
        logger.debug("Registered interceptor", interceptor_class=interceptor.__class__.__name__)

    def on_bootstrap_start(self, specs: dict[str, Any]) -> None:
        """Execute on_bootstrap_start for all registered interceptors.

        Args:
            specs: Dictionary mapping component names to their AsyncAPI specs

        """
        for interceptor in self._interceptors:
            try:
                interceptor.on_bootstrap_start(specs)
            except Exception:
                logger.exception("Error in on_bootstrap_start", interceptor_class=interceptor.__class__.__name__)

    def before_endpoint_creation(self, component_name: str, channel_name: str, channel_config: dict[str, Any]) -> None:
        """Execute before_endpoint_creation for all registered interceptors.

        Args:
            component_name: Name of the component
            channel_name: Name of the channel
            channel_config: Channel configuration from AsyncAPI spec

        """
        for interceptor in self._interceptors:
            try:
                interceptor.before_endpoint_creation(component_name, channel_name, channel_config)
            except Exception:
                logger.exception("Error in before_endpoint_creation", interceptor_class=interceptor.__class__.__name__)

    def after_endpoint_creation(
        self, component_name: str, channel_name: str, endpoint: object, *, success: bool, error: Exception | None = None
    ) -> None:
        """Execute after_endpoint_creation for all registered interceptors.

        Args:
            component_name: Name of the component
            channel_name: Name of the channel
            endpoint: The created endpoint (if successful)
            success: Whether endpoint creation succeeded
            error: Exception raised during creation (if any)

        """
        for interceptor in self._interceptors:
            try:
                interceptor.after_endpoint_creation(
                    component_name, channel_name, endpoint, success=success, error=error
                )
            except Exception:
                logger.exception("Error in after_endpoint_creation", interceptor_class=interceptor.__class__.__name__)

    def on_bootstrap_complete(self, results: dict[str, Any]) -> None:
        """Execute on_bootstrap_complete for all registered interceptors.

        Args:
            results: Summary of bootstrap results

        """
        for interceptor in self._interceptors:
            try:
                interceptor.on_bootstrap_complete(results)
            except Exception:
                logger.exception("Error in on_bootstrap_complete", interceptor_class=interceptor.__class__.__name__)


# Global registry instance
_registry = InterceptorRegistry()


def get_registry() -> InterceptorRegistry:
    """Get the global interceptor registry.

    Returns:
        The global InterceptorRegistry instance

    """
    return _registry


class ValidationInterceptor(WebSocketInterceptor):
    """Interceptor that validates channel mappings during bootstrap.

    This interceptor validates that:
    - Channel names follow snake_case convention
    - All handle_* and on_connect_* functions have corresponding channels
    - Channels have corresponding handler functions (warning only)
    """

    def __init__(self) -> None:
        """Initialize the validation interceptor."""
        self.specs: dict[str, dict[str, Any]] = {}
        self.channel_modules: dict[str, dict[str, ModuleType]] = {}
        self.component_names: list[str] = []
        self.validation_results: list[ChannelValidationResult] = []

    def on_bootstrap_start(self, specs: dict[str, Any]) -> None:
        """Collect all AsyncAPI specs for validation.

        Args:
            specs: Dictionary mapping component names to their AsyncAPI specs

        """
        self.specs = specs.copy()
        self.component_names = list(specs.keys())
        logger.debug("ValidationInterceptor: Starting validation", component_count=len(specs))

    def before_endpoint_creation(
        self,
        component_name: str,
        channel_name: str,
        channel_config: dict[str, Any],  # noqa: ARG002
    ) -> None:
        """Collect channel-to-module mappings from cache for later validation.

        Args:
            component_name: Name of the component
            channel_name: Name of the channel
            channel_config: Channel configuration from AsyncAPI spec (unused)

        """
        # Get module for this specific channel from endpoint_factory's cache
        module = _HANDLER_MODULE_CACHE.get(component_name, {}).get(channel_name)
        if module is not None:
            if component_name not in self.channel_modules:
                self.channel_modules[component_name] = {}
            self.channel_modules[component_name][channel_name] = module

    def on_bootstrap_complete(self, results: dict[str, Any]) -> None:  # noqa: ARG002
        """Run comprehensive validation after all endpoints are created.

        For components with multiple handler files, validates each module
        against only its channels to avoid false positives.

        Args:
            results: Summary of bootstrap results (unused in current validation)

        """
        logger.info("Running channel mapping validation...")

        validation_results = []
        total_errors = 0
        total_warnings = 0

        for component_name in self.component_names:
            spec = self.specs.get(component_name)
            channel_modules = self.channel_modules.get(component_name, {})

            if not spec:
                logger.warning("No spec found for component", component_name=component_name)
                continue

            if not channel_modules:
                logger.warning("No handler modules found for component", component_name=component_name)
                continue

            # Group channels by their handler module
            module_to_channels: dict[ModuleType, list[str]] = {}
            for channel_name, module in channel_modules.items():
                if module not in module_to_channels:
                    module_to_channels[module] = []
                module_to_channels[module].append(channel_name)

            # Validate each module against only its channels
            for module_idx, (handler_module, module_channels) in enumerate(module_to_channels.items(), 1):
                # Create a filtered spec containing only this module's channels
                filtered_spec = spec.copy()
                all_channels = spec.get("channels", {})
                filtered_spec["channels"] = {
                    ch_name: all_channels[ch_name] for ch_name in module_channels if ch_name in all_channels
                }

                # Get spec path for error reporting
                module_name = getattr(handler_module, "__name__", f"module_{module_idx}")
                spec_path = f"{component_name} ({module_name})"

                # Validate this module against its channels
                result = channel_validator.validate_channel_mappings(
                    component_name=component_name,
                    spec=filtered_spec,
                    spec_path=spec_path,
                    handler_module=handler_module,
                )

                validation_results.append(result)
                total_errors += len(result.errors)
                total_warnings += len(result.warnings)

        self.validation_results = validation_results

        # Log summary
        if total_errors > 0 or total_warnings > 0:
            logger.info(
                "Channel validation complete",
                errors=total_errors,
                warnings=total_warnings,
                validations=len(validation_results),
            )
        else:
            logger.info(
                "Channel validation complete: All validations passed successfully", validations=len(validation_results)
            )
