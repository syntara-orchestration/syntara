"""Unit tests for exception registry system."""
# ruff: noqa: N818, A001  # Exception names don't need Error suffix in tests, BaseException shadowing is fine

import importlib
from unittest.mock import Mock, patch

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import syntara.aap.exceptions
from syntara.core.exception_registry import (
    _exception_registry,
    fastapi_exception,
    register_exceptions,
)


class TestFastAPIExceptionDecorator:
    """Test suite for @fastapi_exception decorator."""

    def setup_method(self) -> None:
        """Clear the registry before each test."""
        _exception_registry.clear()

    def test_decorator_registers_exception_with_function_handler(self) -> None:
        """Test that decorator registers exception with function handler."""
        # Mock handler function
        mock_handler = Mock()

        @fastapi_exception(handler=mock_handler)
        class TestException(Exception):
            pass

        # Verify registration
        assert TestException in _exception_registry
        assert _exception_registry[TestException] is mock_handler

    def test_decorator_registers_exception_with_string_handler(self) -> None:
        """Test that decorator registers exception with string handler."""
        handler_path = "syntara.tool_manager.error_handlers.tool_not_found_handler"

        @fastapi_exception(handler=handler_path)
        class TestException(Exception):
            pass

        # Verify registration
        assert TestException in _exception_registry
        assert _exception_registry[TestException] == handler_path

    def test_multiple_exceptions_registration(self) -> None:
        """Test that multiple exceptions can be registered."""
        handler1 = Mock()
        handler2 = Mock()

        @fastapi_exception(handler=handler1)
        class Exception1(Exception):
            pass

        @fastapi_exception(handler=handler2)
        class Exception2(Exception):
            pass

        # Verify both are registered
        assert Exception1 in _exception_registry
        assert Exception2 in _exception_registry
        assert _exception_registry[Exception1] is handler1
        assert _exception_registry[Exception2] is handler2

    def test_decorator_with_inheritance(self) -> None:
        """Test that decorator works with exception inheritance."""
        base_handler = Mock()
        derived_handler = Mock()

        @fastapi_exception(handler=base_handler)
        class BaseException(Exception):
            pass

        @fastapi_exception(handler=derived_handler)
        class DerivedException(BaseException):
            pass

        # Verify both are registered independently
        assert BaseException in _exception_registry
        assert DerivedException in _exception_registry
        assert _exception_registry[BaseException] is base_handler
        assert _exception_registry[DerivedException] is derived_handler


class TestIntegrationUsage:
    """Integration tests for typical usage patterns."""

    def setup_method(self) -> None:
        """Clear the registry before each test."""
        _exception_registry.clear()

    def test_full_decorator_and_registration_workflow(self) -> None:
        """Test the complete workflow from decoration to registration."""
        mock_app = Mock(spec=FastAPI)

        # Create a mock handler function
        def test_handler(request: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(status_code=500, content={"error": "test error"})

        # Use decorator
        @fastapi_exception(handler=test_handler)
        class TestException(Exception):
            pass

        # Verify exception was registered
        assert TestException in _exception_registry
        assert _exception_registry[TestException] is test_handler

        # Register with FastAPI app
        register_exceptions(mock_app)

        # Verify handler was added to app
        mock_app.add_exception_handler.assert_called_once_with(TestException, test_handler)

    @patch("syntara.core.exception_registry.importlib.import_module")
    def test_string_handler_workflow(self, mock_import: Mock) -> None:
        """Test workflow using string handler to avoid circular imports."""
        mock_app = Mock(spec=FastAPI)

        # Setup mock module and handler
        mock_module = Mock()
        mock_handler = Mock()
        mock_module.test_handler = mock_handler
        mock_import.return_value = mock_module

        # Use decorator with string path
        @fastapi_exception(handler="syntara.test.handlers.test_handler")
        class TestException(Exception):
            pass

        # Register with FastAPI app
        register_exceptions(mock_app)

        # Verify import and registration
        mock_import.assert_called_once_with("syntara.test.handlers")
        mock_app.add_exception_handler.assert_called_once_with(TestException, mock_handler)

    def test_multiple_decorators_with_mixed_handlers(self) -> None:
        """Test using multiple decorators with both function and string handlers."""
        # Function handler
        func_handler = Mock()

        @fastapi_exception(handler=func_handler)
        class FunctionHandledException(Exception):
            pass

        @fastapi_exception(handler="syntara.module.string_handler")
        class StringHandledException(Exception):
            pass

        # Verify both are in registry
        assert len(_exception_registry) == 2
        assert FunctionHandledException in _exception_registry
        assert StringHandledException in _exception_registry
        assert _exception_registry[FunctionHandledException] is func_handler
        assert _exception_registry[StringHandledException] == "syntara.module.string_handler"

    def test_registry_persistence_across_modules(self) -> None:
        """Test that registry persists across different module imports."""
        # This simulates how exceptions defined in different modules
        # all end up in the same global registry

        # First "module"
        handler1 = Mock()

        @fastapi_exception(handler=handler1)
        class Module1Exception(Exception):
            pass

        # Second "module"
        handler2 = Mock()

        @fastapi_exception(handler=handler2)
        class Module2Exception(Exception):
            pass

        # Verify both are in the global registry
        assert len(_exception_registry) == 2
        assert Module1Exception in _exception_registry
        assert Module2Exception in _exception_registry

        # Register all at once
        mock_app = Mock(spec=FastAPI)
        register_exceptions(mock_app)

        # Verify both handlers were registered
        assert mock_app.add_exception_handler.call_count == 2


class TestAAPExceptionRegistration:
    """Test that AAP exception handlers are registered via @fastapi_exception decorator.

    Uses importlib.reload to re-execute the module-level decorators, since earlier
    test classes clear the global _exception_registry.
    """

    def test_aap_exceptions_registered_after_import(self) -> None:
        """All 4 AAP exceptions should appear in _exception_registry after import."""
        # Re-execute the module to re-fire @fastapi_exception decorators,
        # since prior test classes call _exception_registry.clear().
        importlib.reload(syntara.aap.exceptions)

        from syntara.aap.exceptions import (
            AAPAuthenticationError,
            AAPConnectionError,
            AAPNotConfiguredError,
            AAPUpstreamError,
        )

        for exc_class in (
            AAPNotConfiguredError,
            AAPConnectionError,
            AAPAuthenticationError,
            AAPUpstreamError,
        ):
            assert exc_class in _exception_registry, f"{exc_class.__name__} not found in _exception_registry"
