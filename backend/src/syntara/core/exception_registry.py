"""Exception registration system for automatic FastAPI error handler registration.

This module provides decorators and utilities for automatically registering
exception classes with their corresponding error handlers, eliminating the need
for manual registration in main.py.

Example:
    ```python
    from syntara.core.exception_registry import fastapi_exception
    from syntara.tool_manager.error_handlers import tool_not_found_handler

    @fastapi_exception(handler=tool_not_found_handler)
    class ToolNotFoundError(Exception):
        pass
    ```

"""

import importlib
from collections.abc import Callable
from typing import Any, TypeVar, cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Type for exception classes
ExceptionType = TypeVar("ExceptionType", bound=BaseException)

# Type for error handler functions
ErrorHandler = Callable[[Request, Any], JSONResponse]

# Global registry of exception classes and their handlers
_exception_registry: dict[type[BaseException], ErrorHandler | str] = {}


def fastapi_exception(
    *,
    handler: ErrorHandler | str,
) -> Callable[[type[ExceptionType]], type[ExceptionType]]:
    """Automatically register an exception with FastAPI.

    This decorator registers the exception class with its error handler
    in the global registry. The registered exceptions can then be
    automatically added to a FastAPI app using register_exceptions().

    Args:
        handler: The error handler function or a string module path to the handler
                 (e.g., "syntara.tool_manager.error_handlers.tool_not_found_handler")

    Returns:
        The decorated exception class (unchanged)

    Example:
        ```python
        @fastapi_exception(handler=tool_not_found_handler)
        class ToolNotFoundError(Exception):
            pass

        # Or to avoid circular imports:
        @fastapi_exception(handler="syntara.tool_manager.error_handlers.tool_not_found_handler")
        class ToolNotFoundError(Exception):
            pass
        ```

    """

    def decorator(exception_class: type[ExceptionType]) -> type[ExceptionType]:
        # Register the exception with its handler
        _exception_registry[exception_class] = handler
        return exception_class

    return decorator


def _resolve_handler(handler: ErrorHandler | str) -> ErrorHandler:
    """Resolve a handler string to the actual function.

    Args:
        handler: Either a function or a string like "module.function"

    Returns:
        The resolved function

    """
    if isinstance(handler, str):
        # Split module and function name
        module_path, func_name = handler.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return cast("ErrorHandler", getattr(module, func_name))
    return handler


def register_exceptions(app: FastAPI) -> None:
    """Register all decorated exceptions with the FastAPI app.

    This function should be called once during app initialization to
    register all exceptions that have been decorated with @fastapi_exception.

    Args:
        app: The FastAPI application instance

    Example:
        ```python
        from syntara.core.exception_registry import register_exceptions

        app = FastAPI()
        register_exceptions(app)
        ```

    """
    for exception_class, handler in _exception_registry.items():
        resolved_handler = _resolve_handler(handler)
        app.add_exception_handler(exception_class, resolved_handler)  # type: ignore[arg-type]
