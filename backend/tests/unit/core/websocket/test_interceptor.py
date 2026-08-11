"""Tests for WebSocket interceptor system."""

from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

from syntara.core.websocket.interceptor import (
    InterceptorRegistry,
    ValidationInterceptor,
    WebSocketInterceptor,
)


class MockInterceptor(WebSocketInterceptor):
    """Mock interceptor for testing."""

    def __init__(self) -> None:
        """Initialize mock interceptor with tracking."""
        self.bootstrap_started = False
        self.before_creation_calls: list[tuple[str, str]] = []
        self.after_creation_calls: list[tuple[str, str, bool]] = []
        self.bootstrap_completed = False
        self.bootstrap_results: dict[str, Any] | None = None

    def on_bootstrap_start(self, specs: dict[str, Any]) -> None:
        """Track bootstrap start."""
        self.bootstrap_started = True
        self.specs = specs

    def before_endpoint_creation(self, component_name: str, channel_name: str, _channel_config: dict[str, Any]) -> None:
        """Track before_endpoint_creation calls."""
        self.before_creation_calls.append((component_name, channel_name))

    def after_endpoint_creation(
        self,
        component_name: str,
        channel_name: str,
        _endpoint: object,
        *,
        success: bool,
        error: Exception | None = None,
    ) -> None:
        """Track after_endpoint_creation calls."""
        _ = error  # Unused in mock, available for future use
        self.after_creation_calls.append((component_name, channel_name, success))

    def on_bootstrap_complete(self, results: dict[str, Any]) -> None:
        """Track bootstrap complete."""
        self.bootstrap_completed = True
        self.bootstrap_results = results


class TestInterceptorRegistry:
    """Tests for InterceptorRegistry."""

    def test_register_interceptor(self) -> None:
        """Test registering an interceptor."""
        registry = InterceptorRegistry()
        interceptor = MockInterceptor()

        registry.register(interceptor)

        assert len(registry._interceptors) == 1
        assert registry._interceptors[0] is interceptor

    def test_on_bootstrap_start(self) -> None:
        """Test on_bootstrap_start lifecycle hook."""
        registry = InterceptorRegistry()
        interceptor = MockInterceptor()
        registry.register(interceptor)

        specs: dict[str, object] = {"example": {"channels": {}}}
        registry.on_bootstrap_start(specs)

        assert interceptor.bootstrap_started is True
        assert interceptor.specs == specs

    def test_before_endpoint_creation(self) -> None:
        """Test before_endpoint_creation lifecycle hook."""
        registry = InterceptorRegistry()
        interceptor = MockInterceptor()
        registry.register(interceptor)

        registry.before_endpoint_creation("example", "chat", {"address": "/ws/chat"})

        assert len(interceptor.before_creation_calls) == 1
        assert interceptor.before_creation_calls[0] == ("example", "chat")

    def test_after_endpoint_creation_success(self) -> None:
        """Test after_endpoint_creation with successful creation."""
        registry = InterceptorRegistry()
        interceptor = MockInterceptor()
        registry.register(interceptor)

        def mock_endpoint() -> None:
            """Mock endpoint for testing."""

        registry.after_endpoint_creation("example", "chat", mock_endpoint, success=True)

        assert len(interceptor.after_creation_calls) == 1
        assert interceptor.after_creation_calls[0] == ("example", "chat", True)

    def test_after_endpoint_creation_failure(self) -> None:
        """Test after_endpoint_creation with failed creation."""
        registry = InterceptorRegistry()
        interceptor = MockInterceptor()
        registry.register(interceptor)

        error = ValueError("Test error")
        registry.after_endpoint_creation("example", "chat", None, success=False, error=error)

        assert len(interceptor.after_creation_calls) == 1
        assert interceptor.after_creation_calls[0] == ("example", "chat", False)

    def test_on_bootstrap_complete(self) -> None:
        """Test on_bootstrap_complete lifecycle hook."""
        registry = InterceptorRegistry()
        interceptor = MockInterceptor()
        registry.register(interceptor)

        results = {
            "total_endpoints": 3,
            "success_count": 3,
            "failure_count": 0,
        }
        registry.on_bootstrap_complete(results)

        assert interceptor.bootstrap_completed is True
        assert interceptor.bootstrap_results == results

    def test_multiple_interceptors(self) -> None:
        """Test multiple interceptors are all called."""
        registry = InterceptorRegistry()
        interceptor1 = MockInterceptor()
        interceptor2 = MockInterceptor()

        registry.register(interceptor1)
        registry.register(interceptor2)

        specs: dict[str, object] = {"example": {}}
        registry.on_bootstrap_start(specs)

        assert interceptor1.bootstrap_started is True
        assert interceptor2.bootstrap_started is True

    def test_interceptor_error_handling(self) -> None:
        """Test that errors in one interceptor don't affect others."""

        class FailingInterceptor(WebSocketInterceptor):
            def on_bootstrap_start(self, _specs: dict[str, Any]) -> None:
                msg = "Test error"
                raise ValueError(msg)

        registry = InterceptorRegistry()
        failing = FailingInterceptor()
        working = MockInterceptor()

        registry.register(failing)
        registry.register(working)

        specs: dict[str, object] = {"example": {}}
        # Should not raise, error should be caught and logged
        registry.on_bootstrap_start(specs)

        # Working interceptor should still be called
        assert working.bootstrap_started is True


class TestValidationInterceptor:
    """Tests for ValidationInterceptor."""

    def test_initialization(self) -> None:
        """Test ValidationInterceptor initialization."""
        interceptor = ValidationInterceptor()

        assert interceptor.specs == {}
        assert interceptor.channel_modules == {}
        assert interceptor.component_names == []

    def test_on_bootstrap_start(self) -> None:
        """Test on_bootstrap_start collects specs."""
        interceptor = ValidationInterceptor()

        specs: dict[str, dict[str, object]] = {
            "example": {"channels": {"chat": {}}},
            "another": {"channels": {"coffee": {}}},
        }
        interceptor.on_bootstrap_start(specs)

        assert interceptor.specs == specs
        assert interceptor.component_names == ["example", "another"]

    def test_before_endpoint_creation(self) -> None:
        """Test before_endpoint_creation collects channel-to-module mappings."""
        interceptor = ValidationInterceptor()

        # Create mock modules
        mock_module1 = MagicMock(spec=ModuleType)
        mock_module2 = MagicMock(spec=ModuleType)

        # Mock _HANDLER_MODULE_CACHE to have the example component with multiple modules
        with patch(
            "syntara.core.websocket.interceptor._HANDLER_MODULE_CACHE",
            {"example": {"chat": mock_module1, "coffee": mock_module2}},
        ):
            # Call with different channels
            interceptor.before_endpoint_creation("example", "chat", {"address": "/ws/chat"})
            interceptor.before_endpoint_creation("example", "coffee", {"address": "/ws/coffee"})

            # Verify that channel-to-module mappings were collected
            assert "example" in interceptor.channel_modules
            assert interceptor.channel_modules["example"]["chat"] is mock_module1
            assert interceptor.channel_modules["example"]["coffee"] is mock_module2

    def test_on_bootstrap_complete(self) -> None:
        """Test on_bootstrap_complete runs validation."""
        interceptor = ValidationInterceptor()

        # Set up minimal data for validation
        interceptor.component_names = []
        interceptor.specs = {}
        interceptor.channel_modules = {}

        results = {"total_endpoints": 0}
        interceptor.on_bootstrap_complete(results)

        assert interceptor.validation_results == []

    def test_multiple_modules_per_component(self) -> None:
        """Test that multiple handler files per component are validated correctly."""
        interceptor = ValidationInterceptor()

        # Create two different mock modules
        module1 = MagicMock(spec=ModuleType)
        module1.__name__ = "module_file1"
        module2 = MagicMock(spec=ModuleType)
        module2.__name__ = "module_file2"

        # Mock handler functions for each module
        def mock_handle_chat(_msg: dict[str, Any], _conn_id: str) -> dict[str, Any]:
            return {}

        def mock_handle_coffee(_msg: dict[str, Any], _conn_id: str) -> dict[str, Any]:
            return {}

        module1.handle_chat = mock_handle_chat
        module2.handle_coffee = mock_handle_coffee

        # Set up component with channels from different modules
        interceptor.component_names = ["example"]
        interceptor.specs = {
            "example": {
                "channels": {
                    "chat": {"address": "/ws/example/v1/chat"},
                    "coffee": {"address": "/ws/example/v1/coffee"},
                },
                "servers": {"development": {}},
            }
        }
        interceptor.channel_modules = {"example": {"chat": module1, "coffee": module2}}

        interceptor.on_bootstrap_complete({"total_endpoints": 2})

        # Verify validation ran and succeeded for each module
        assert len(interceptor.validation_results) == 2
        assert all(result.is_valid for result in interceptor.validation_results)
