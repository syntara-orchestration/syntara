"""Unit tests for ProviderFactory.

Tests cover:
- Provider registration and creation
- Thread safety
- Error handling and validation
- Registry management
- Provider type validation
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import UUID

import pytest

from syntara.core.exceptions import SafeValueError
from syntara.tool_manager.lib.providers.base import ToolProviderAdapter
from syntara.tool_manager.lib.providers.factory import ProviderFactory
from syntara.tool_manager.lib.providers.mcp import MCPProvider


class TestProviderFactory:
    """Test suite for ProviderFactory class."""

    def test_factory_initialization(self) -> None:
        """Test ProviderFactory initialization."""
        factory = ProviderFactory()

        # Should start with empty registry
        assert factory.get_registered_provider_types() == []
        assert not factory.is_registered("any_type")

    def test_register_provider_type_success(self) -> None:
        """Test successful provider type registration."""
        factory = ProviderFactory()

        # Register MCPProvider
        factory.register_provider_type("mcp", MCPProvider)

        # Should be registered
        assert factory.is_registered("mcp")
        assert factory.get_registered_provider_types() == ["mcp"]

    def test_register_multiple_provider_types(self) -> None:
        """Test registering multiple provider types."""
        factory = ProviderFactory()

        # Define additional mock provider classes
        class MCPProviderA(MCPProvider):
            pass

        class MCPProviderB(MCPProvider):
            pass

        # Register multiple types
        factory.register_provider_type("mcp_a", MCPProviderA)
        factory.register_provider_type("mcp_b", MCPProviderB)
        factory.register_provider_type("mcp_original", MCPProvider)

        # Should have all types registered
        registered_types = factory.get_registered_provider_types()
        assert len(registered_types) == 3
        assert "mcp_a" in registered_types
        assert "mcp_b" in registered_types
        assert "mcp_original" in registered_types

        # Should be sorted
        assert registered_types == sorted(registered_types)

    def test_register_provider_type_invalid_inputs(self) -> None:
        """Test provider type registration with invalid inputs."""
        factory = ProviderFactory()

        # Empty provider type should raise SafeValueError
        with pytest.raises(SafeValueError, match="Provider type must be a non-empty string"):
            factory.register_provider_type("", MCPProvider)

        # None provider type should raise SafeValueError
        with pytest.raises(SafeValueError, match="Provider type must be a non-empty string"):
            factory.register_provider_type(None, MCPProvider)  # type: ignore[arg-type]

        # Non-string provider type should raise SafeValueError
        with pytest.raises(SafeValueError, match="Provider type must be a non-empty string"):
            factory.register_provider_type(123, MCPProvider)  # type: ignore[arg-type]

        # Non-callable provider class should raise TypeError
        with pytest.raises(TypeError, match="Provider class must be callable"):
            factory.register_provider_type("test", "not_callable")  # type: ignore[arg-type]

    def test_register_duplicate_provider_type(self) -> None:
        """Test registering duplicate provider type raises error."""
        factory = ProviderFactory()

        # Register once
        factory.register_provider_type("mcp", MCPProvider)

        # Try to register again should raise SafeValueError
        with pytest.raises(SafeValueError, match="Provider type 'mcp' is already registered"):
            factory.register_provider_type("mcp", MCPProvider)

    def test_create_provider_instance_success(self) -> None:
        """Test successful provider instance creation."""
        factory = ProviderFactory()
        factory.register_provider_type("mcp", MCPProvider)

        # Create instance with required parameters
        instance = factory.create_provider_instance("mcp", base_url="http://localhost:8080", api_key="test-key")

        # Should be correct type and implement protocol
        assert isinstance(instance, MCPProvider)
        assert isinstance(instance, ToolProviderAdapter)

    def test_create_provider_instance_with_kwargs(self) -> None:
        """Test provider instance creation with keyword arguments."""
        factory = ProviderFactory()
        factory.register_provider_type("mcp", MCPProvider)

        # Create instance with kwargs (MCP uses different parameters)
        instance = factory.create_provider_instance("mcp", base_url="http://localhost:8080", api_key="test-key")

        # Should have correct configuration
        assert isinstance(instance, MCPProvider)

    def test_create_provider_instance_invalid_type(self) -> None:
        """Test creating instance with unregistered provider type."""
        factory = ProviderFactory()

        # Try to create instance of unregistered type
        with pytest.raises(SafeValueError, match="Unknown provider type 'nonexistent'"):
            factory.create_provider_instance("nonexistent")

    def test_create_provider_instance_invalid_inputs(self) -> None:
        """Test provider instance creation with invalid inputs."""
        factory = ProviderFactory()
        factory.register_provider_type("mcp", MCPProvider)

        # Empty provider type should raise SafeValueError
        with pytest.raises(SafeValueError, match="Provider type must be a non-empty string"):
            factory.create_provider_instance("")

        # None provider type should raise SafeValueError
        with pytest.raises(SafeValueError, match="Provider type must be a non-empty string"):
            factory.create_provider_instance(None)  # type: ignore[arg-type]

    def test_create_provider_instance_construction_failure(self) -> None:
        """Test provider instance creation when constructor fails."""
        factory = ProviderFactory()

        class FailingProvider(MCPProvider):
            def __init__(
                self,
                base_url: str,
                api_key: str,
                integration_id: UUID | None = None,
                integration_name: str | None = "mcp-integration",
            ) -> None:
                super().__init__(
                    integration_id=integration_id, integration_name=integration_name, base_url=base_url, api_key=api_key
                )
                msg = "Intentional construction failure"
                raise RuntimeError(msg)

        factory.register_provider_type("failing", FailingProvider)

        # Should wrap construction errors
        with pytest.raises(TypeError, match="Failed to create provider instance for type 'failing'"):
            factory.create_provider_instance("failing")

    def test_unregister_provider_type_success(self) -> None:
        """Test successful provider type unregistration."""
        factory = ProviderFactory()
        factory.register_provider_type("mcp", MCPProvider)

        # Should be registered
        assert factory.is_registered("mcp")

        # Unregister
        factory.unregister_provider_type("mcp")

        # Should no longer be registered
        assert not factory.is_registered("mcp")
        assert factory.get_registered_provider_types() == []

    def test_unregister_provider_type_not_registered(self) -> None:
        """Test unregistering non-existent provider type."""
        factory = ProviderFactory()

        # Try to unregister non-existent type
        with pytest.raises(SafeValueError, match="Provider type 'nonexistent' is not registered"):
            factory.unregister_provider_type("nonexistent")

    def test_thread_safety_registration(self) -> None:
        """Test thread safety of provider registration."""
        factory = ProviderFactory()
        registration_errors = []

        def register_provider(provider_type: str) -> None:
            try:
                factory.register_provider_type(provider_type, MCPProvider)
            except (SafeValueError, TypeError) as e:
                registration_errors.append(e)

        # Register multiple providers concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(register_provider, f"mcp_{i}") for i in range(20)]

            # Wait for all to complete
            for future in as_completed(futures):
                future.result()

        # Should have no errors (all should succeed)
        assert len(registration_errors) == 0

        # Should have all 20 providers registered
        registered_types = factory.get_registered_provider_types()
        assert len(registered_types) == 20

        # All should be registered
        for i in range(20):
            assert factory.is_registered(f"mcp_{i}")

    def test_thread_safety_duplicate_registration(self) -> None:
        """Test thread safety when multiple threads try to register same type."""
        factory = ProviderFactory()
        registration_errors = []
        successful_registrations = []

        def register_same_provider() -> None:
            try:
                factory.register_provider_type("duplicate", MCPProvider)
                successful_registrations.append(True)
            except SafeValueError as e:
                if "already registered" in str(e):
                    registration_errors.append(e)
                else:
                    raise  # Re-raise unexpected errors

        # Try to register same provider from multiple threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(register_same_provider) for _ in range(20)]

            # Wait for all to complete
            for future in as_completed(futures):
                future.result()

        # Should have exactly one successful registration and 19 errors
        assert len(successful_registrations) == 1
        assert len(registration_errors) == 19

        # Provider should be registered
        assert factory.is_registered("duplicate")

    def test_thread_safety_creation(self) -> None:
        """Test thread safety of provider instance creation."""
        factory = ProviderFactory()
        factory.register_provider_type("mcp", MCPProvider)

        created_instances = []
        creation_errors = []

        def create_provider() -> None:
            try:
                instance = factory.create_provider_instance("mcp", base_url="http://localhost:8080", api_key="test-key")
                created_instances.append(instance)
            except (SafeValueError, TypeError) as e:
                creation_errors.append(e)

        # Create multiple instances concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(create_provider) for _ in range(50)]

            # Wait for all to complete
            for future in as_completed(futures):
                future.result()

        # Should have no errors
        assert len(creation_errors) == 0

        # Should have 50 instances
        assert len(created_instances) == 50

        # All should be MCPProvider instances
        for instance in created_instances:
            assert isinstance(instance, MCPProvider)

    def test_registry_management(self) -> None:
        """Test comprehensive registry management operations."""
        factory = ProviderFactory()

        # Start empty
        assert factory.get_registered_provider_types() == []

        # Register some providers
        factory.register_provider_type("provider_a", MCPProvider)
        factory.register_provider_type("provider_b", MCPProvider)
        factory.register_provider_type("provider_c", MCPProvider)

        # Check registry state
        registered = factory.get_registered_provider_types()
        assert len(registered) == 3
        assert "provider_a" in registered
        assert "provider_b" in registered
        assert "provider_c" in registered

        # Check individual registration status
        assert factory.is_registered("provider_a")
        assert factory.is_registered("provider_b")
        assert factory.is_registered("provider_c")
        assert not factory.is_registered("provider_d")

        # Unregister one
        factory.unregister_provider_type("provider_b")

        # Check updated state
        registered = factory.get_registered_provider_types()
        assert len(registered) == 2
        assert "provider_a" in registered
        assert not factory.is_registered("provider_b")
        assert "provider_c" in registered

        # Can re-register after unregistering
        factory.register_provider_type("provider_b", MCPProvider)
        assert factory.is_registered("provider_b")

    def test_error_messages_contain_available_types(self) -> None:
        """Test that error messages include available provider types."""
        factory = ProviderFactory()
        factory.register_provider_type("provider_x", MCPProvider)
        factory.register_provider_type("provider_y", MCPProvider)

        # Error message should list available types
        with pytest.raises(SafeValueError, match="Unknown provider type 'nonexistent'") as exc_info:
            factory.create_provider_instance("nonexistent")

        error_message = str(exc_info.value)
        assert "Available types: provider_x, provider_y" in error_message

    def test_performance_with_many_providers(self) -> None:
        """Test factory performance with many registered providers."""
        factory = ProviderFactory()

        # Register many providers
        num_providers = 1000
        start_time = time.time()

        for i in range(num_providers):
            factory.register_provider_type(f"provider_{i:04d}", MCPProvider)

        registration_time = time.time() - start_time

        # Registration should be reasonably fast (less than 1.5 second for 1000)
        assert registration_time < 1.5

        # Check all are registered
        assert len(factory.get_registered_provider_types()) == num_providers

        # Create instances should also be fast
        start_time = time.time()

        for i in range(10):  # Create fewer instances to keep test fast
            instance = factory.create_provider_instance(
                f"provider_{i:04d}", base_url="http://localhost:8080", api_key="test-key"
            )
            assert isinstance(instance, MCPProvider)

        creation_time = time.time() - start_time
        assert creation_time < 0.1  # Should be very fast for 10 instances
