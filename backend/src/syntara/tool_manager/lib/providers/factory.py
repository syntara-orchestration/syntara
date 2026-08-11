"""Provider factory for creating and registering tool provider adapters."""

import threading
from collections.abc import Callable
from typing import Any

from syntara.core.exceptions import SafeValueError
from syntara.tool_manager.lib.providers.base import ToolProviderAdapter
from syntara.tool_manager.lib.providers.mcp import MCPProvider


class ProviderFactory:
    """Factory for creating and managing tool provider adapters.

    This factory implements a registry pattern for provider types and provides
    thread-safe registration and instantiation of provider adapters.
    """

    def __init__(self) -> None:
        """Initialize the provider factory with an empty registry."""
        self._provider_types: dict[str, Callable[..., ToolProviderAdapter]] = {}
        self._lock = threading.Lock()

    def register_provider_type(
        self,
        provider_type: str,
        provider_class: Callable[..., ToolProviderAdapter],
    ) -> None:
        """Register a provider adapter class for a provider type.

        Args:
            provider_type: Unique string identifier for the provider type
            provider_class: Callable that creates provider adapter instances

        Raises:
            ValueError: If provider_type is already registered or invalid
            TypeError: If provider_class doesn't implement ToolProviderAdapter

        """
        if not provider_type or not isinstance(provider_type, str):
            msg = "Provider type must be a non-empty string"
            raise SafeValueError(msg)

        if not callable(provider_class):
            msg = "Provider class must be callable"  # type: ignore[unreachable]
            raise TypeError(msg)

        with self._lock:
            if provider_type in self._provider_types:
                msg = f"Provider type '{provider_type}' is already registered"
                raise SafeValueError(msg)

            self._provider_types[provider_type] = provider_class

    def create_provider_instance(
        self,
        provider_type: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> ToolProviderAdapter:
        """Create an instance of a provider adapter.

        Args:
            provider_type: String identifier for the provider type
            **kwargs: Keyword arguments to pass to the provider constructor

        Returns:
            ToolProviderAdapter instance

        Raises:
            ValueError: If provider_type is not registered or creation fails
            TypeError: If created instance doesn't implement ToolProviderAdapter

        """
        if not provider_type or not isinstance(provider_type, str):
            msg = "Provider type must be a non-empty string"
            raise SafeValueError(msg)

        with self._lock:
            if provider_type not in self._provider_types:
                available = ", ".join(sorted(self._provider_types.keys()))
                msg = f"Unknown provider type '{provider_type}'. Available types: {available}"
                raise SafeValueError(msg)

            provider_class = self._provider_types[provider_type]

        try:
            instance = provider_class(**kwargs)
        except Exception as e:
            msg = f"Failed to create provider instance for type '{provider_type}'"
            raise TypeError(msg) from e

        # Runtime validation for defense in depth (type system should guarantee this)
        if not isinstance(instance, ToolProviderAdapter):
            msg = (  # type: ignore[unreachable]
                f"Provider class for '{provider_type}' must implement ToolProviderAdapter"
            )
            raise TypeError(msg)

        return instance

    def get_registered_provider_types(self) -> list[str]:
        """Get list of registered provider types.

        Returns:
            Sorted list of registered provider type strings

        """
        with self._lock:
            return sorted(self._provider_types.keys())

    def is_registered(self, provider_type: str) -> bool:
        """Check if a provider type is registered.

        Args:
            provider_type: String identifier for the provider type

        Returns:
            True if provider type is registered, False otherwise

        """
        with self._lock:
            return provider_type in self._provider_types

    def unregister_provider_type(self, provider_type: str) -> None:
        """Unregister a provider type from the factory.

        Args:
            provider_type: String identifier for the provider type

        Raises:
            ValueError: If provider_type is not registered

        """
        with self._lock:
            if provider_type not in self._provider_types:
                msg = f"Provider type '{provider_type}' is not registered"
                raise SafeValueError(msg)

            del self._provider_types[provider_type]


# ===================================================
# Generator for dependency injection
# ---------------------------------------------------
_provider_factory: ProviderFactory = ProviderFactory()
_provider_factory.register_provider_type("mcp", MCPProvider)


async def get_provider_factory() -> ProviderFactory:
    """Return the singleton ProviderFactory instance.

    Returns:
        ProviderFactory for dependency injection

    """
    return _provider_factory


# ===================================================
