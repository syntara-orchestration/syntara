"""Integration tests for provider factory and adapters.

Tests cover:
- Factory and provider integration
- Provider lifecycle management
- End-to-end provider operations
- Error handling across components
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any, cast

import pytest

from syntara.core.exceptions import SafeValueError
from syntara.tool_manager.lib.providers.factory import ProviderFactory
from tests.unit.fixtures.mock_mcp_provider import MockMCPProvider

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from syntara.tool_manager.models.tool import Tool


class TestProviderIntegration:
    """Test suite for provider factory and adapter integration."""

    def test_factory_provider_registration_and_creation(self) -> None:
        """Test complete flow from registration to provider creation."""
        factory = ProviderFactory()

        # Register MockProvider
        factory.register_provider_type("mcp", MockMCPProvider)

        # Create instance with custom configuration
        provider = factory.create_provider_instance(
            "mcp",
            integration_name="integration_test",
            base_url="http://localhost:8000/mcp",
            api_key="api-key",
        )

        # Verify correct type and configuration
        assert isinstance(provider, MockMCPProvider)
        assert provider.integration_name == "integration_test"

    @pytest.mark.asyncio
    async def test_factory_created_provider_functionality(self) -> None:
        """Test that factory-created providers work correctly."""
        factory = ProviderFactory()
        factory.register_provider_type("mcp", MockMCPProvider)

        # Create provider instance
        provider = factory.create_provider_instance(
            "mcp",
            base_url="http://localhost:8000/mcp",
            api_key="api-key",
        )

        # Test connection validation
        connection_result = await provider.validate_connection()
        assert connection_result.valid is True
        assert connection_result.provider_type == "mcp"

        # Test tool refresh
        tools = await provider.refresh_tools()
        assert len(tools) > 0

        # Test tool schema retrieval
        first_tool = tools[0]
        schema = await provider.get_tool_schema(first_tool.name)
        assert schema.name == first_tool.name

        # Test tool validation
        validation_result = await provider.validate_tool(first_tool.name)
        assert validation_result.success is True

    def test_multiple_provider_types_registration(self) -> None:
        """Test registering and creating multiple provider types."""
        factory = ProviderFactory()

        # Create different provider classes
        class MockProviderTypeA(MockMCPProvider):
            provider_type = "type_a"

        class MockProviderTypeB(MockMCPProvider):
            provider_type = "type_b"

        # Register multiple types
        factory.register_provider_type("type_a", MockProviderTypeA)
        factory.register_provider_type("type_b", MockProviderTypeB)

        # Create instances of each type
        provider_a = factory.create_provider_instance(
            "type_a",
            integration_name="provider_a",
            base_url="http://localhost:8000/mcp",
            api_key="api-key",
        )
        provider_b = factory.create_provider_instance(
            "type_b",
            integration_name="provider_b",
            base_url="http://localhost:8001/mcp",
            api_key="api-key",
        )

        # Verify correct types
        assert isinstance(provider_a, MockProviderTypeA)
        assert isinstance(provider_b, MockProviderTypeB)
        assert provider_a.integration_name == "provider_a"
        assert provider_b.integration_name == "provider_b"

    def test_factory_provider_lifecycle(self) -> None:
        """Test complete provider lifecycle through factory."""
        factory = ProviderFactory()

        # Initially no types registered
        assert len(factory.get_registered_provider_types()) == 0

        # Register provider type
        factory.register_provider_type("lifecycle_test", MockMCPProvider)
        assert factory.is_registered("lifecycle_test")

        # Create multiple instances
        provider1 = factory.create_provider_instance(
            "lifecycle_test",
            integration_name="instance1",
            base_url="http://localhost:8000/mcp",
            api_key="api-key",
        )
        provider2 = factory.create_provider_instance(
            "lifecycle_test",
            integration_name="instance2",
            base_url="http://localhost:8000/mcp",
            api_key="api-key",
        )

        # Both should be valid but different instances
        assert provider1 is not provider2
        assert cast("MockMCPProvider", provider1).integration_name == "instance1"
        assert cast("MockMCPProvider", provider2).integration_name == "instance2"

        # Unregister type
        factory.unregister_provider_type("lifecycle_test")
        assert not factory.is_registered("lifecycle_test")

        # Can't create new instances after unregistering
        with pytest.raises(SafeValueError, match="Unknown provider type"):
            factory.create_provider_instance("lifecycle_test")

        # But existing instances still work (they're independent)
        assert cast("MockMCPProvider", provider1).integration_name == "instance1"
        assert cast("MockMCPProvider", provider2).integration_name == "instance2"

    @pytest.mark.asyncio
    async def test_concurrent_provider_operations(self) -> None:
        """Test concurrent operations with multiple provider instances."""
        factory = ProviderFactory()
        factory.register_provider_type("concurrent", MockMCPProvider)

        # Create multiple provider instances
        providers = [
            factory.create_provider_instance(
                "concurrent",
                integration_name=f"provider_{i}",
                base_url=f"http://localhost:800{i}/mcp",
                api_key="api-key",
            )
            for i in range(5)
        ]

        # Run concurrent operations
        tasks: list[Coroutine[Any, Any, Any]] = []
        for provider in providers:
            tasks.append(provider.validate_connection())
            tasks.append(provider.refresh_tools())

        # Wait for all to complete
        results = await asyncio.gather(*tasks)

        # Should have results from all operations
        assert len(results) == 10  # 5 providers * 2 operations each

        # Check connection results (every other result)
        for i in range(0, 10, 2):
            connection_result = results[i]
            assert connection_result.valid is True

        # Check tool refresh results (every other result, offset by 1)
        for i in range(1, 10, 2):
            tools: list[Tool] = results[i]
            assert len(tools) > 0

    def test_factory_error_handling_integration(self) -> None:
        """Test error handling across factory and provider components."""
        factory = ProviderFactory()

        # Test provider registration error handling
        with pytest.raises(SafeValueError, match="Provider type must be a non-empty string"):
            factory.register_provider_type("", MockMCPProvider)

        with pytest.raises(TypeError, match="Provider class must be callable"):
            factory.register_provider_type("test", "not_callable")  # type: ignore[arg-type]

        # Test provider creation error handling
        with pytest.raises(SafeValueError, match="Unknown provider type"):
            factory.create_provider_instance("nonexistent")

        # Register valid provider
        factory.register_provider_type("valid", MockMCPProvider)

        # Test duplicate registration
        with pytest.raises(SafeValueError, match="already registered"):
            factory.register_provider_type("valid", MockMCPProvider)

        # Test successful creation after registration
        provider = factory.create_provider_instance(
            "valid",
            base_url="http://localhost:8000/mcp",
            api_key="api-key",
        )
        assert isinstance(provider, MockMCPProvider)

    def test_factory_thread_safety_with_provider_creation(self) -> None:
        """Test thread safety when creating providers concurrently."""
        factory = ProviderFactory()
        factory.register_provider_type("thread_safe", MockMCPProvider)

        created_providers = []
        creation_errors = []

        def create_provider_with_config(thread_id: int) -> None:
            try:
                instance = factory.create_provider_instance(
                    "thread_safe",
                    integration_name=f"thread_{thread_id}",
                    base_url="http://localhost:8000/mcp",
                    api_key="api-key",
                )
                created_providers.append(instance)
            except (SafeValueError, TypeError) as e:
                creation_errors.append(e)

        # Create providers from multiple threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(create_provider_with_config, i) for i in range(20)]

            for future in as_completed(futures):
                future.result()

        # Should have no errors and 20 providers
        assert len(creation_errors) == 0
        assert len(created_providers) == 20

        # All should have unique names
        provider_names = {cast("MockMCPProvider", p).integration_name for p in created_providers}
        assert len(provider_names) == 20  # All unique names

        # All should be correct type
        for provider in created_providers:
            assert isinstance(provider, MockMCPProvider)
