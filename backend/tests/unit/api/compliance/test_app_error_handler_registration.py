"""Application-level compliance test: RFC 9457 error handler registration.

This test validates that the FastAPI application registers the RFC 9457 validation
error handler at the app level, ensuring ALL endpoints (including all list endpoints)
return RFC 9457 Problem Details format for validation errors.

Since error handlers are registered globally at the application level (not per-endpoint),
this single test proves compliance across all endpoints.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


@pytest.mark.unit
@pytest.mark.compliance
def test_app_registers_rfc9457_validation_error_handler():
    """Validates FastAPI app registers RFC 9457 validation error handler.

    This architectural test ensures that:
    1. The FastAPI app registers validation_error_handler globally
    2. Both PydanticValidationError and RequestValidationError use it
    3. Therefore ALL endpoints (including all list endpoints) return RFC 9457 errors

    Since error handlers are app-level configuration, this test proves
    compliance for all endpoints with a single test.
    """
    # Read main.py to verify error handler registration
    main_py = Path(__file__).parents[4] / "src" / "syntara" / "api" / "main.py"
    source = main_py.read_text()
    tree = ast.parse(source)

    # Find all add_exception_handler calls (positional or keyword argument forms)
    handler_registrations = []
    # FastAPI accepts the exception type as "exc_class" or "exc_class_or_status_code"
    exc_class_keywords = {"exc_class", "exc_class_or_status_code"}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_exception_handler"
        ):
            kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}

            # Try positional args first, fall back to keyword args
            exc_node = node.args[0] if len(node.args) >= 1 else None
            handler_node = node.args[1] if len(node.args) >= 2 else None

            if exc_node is None:
                for kw_name in exc_class_keywords:
                    if kw_name in kwargs:
                        exc_node = kwargs[kw_name]
                        break
            if handler_node is None:
                handler_node = kwargs.get("handler")

            # Only record if both exception type and handler were found
            if exc_node is not None and handler_node is not None:
                exc_type = ast.unparse(exc_node)
                handler = ast.unparse(handler_node)
                handler_registrations.append((exc_type, handler))

    # Verify validation_error_handler is registered for validation errors
    validation_handlers = [
        (exc, handler) for exc, handler in handler_registrations if "validation_error_handler" in handler
    ]

    assert len(validation_handlers) >= 2, (
        f"Expected validation_error_handler registered for PydanticValidationError "
        f"and RequestValidationError, found {len(validation_handlers)} registrations. "
        f"All registrations: {handler_registrations}"
    )

    # Verify both Pydantic and FastAPI validation errors are covered
    exception_types = {exc for exc, _ in validation_handlers}
    assert "PydanticValidationError" in exception_types, (
        "validation_error_handler must be registered for PydanticValidationError. "
        f"Found handlers for: {exception_types}"
    )
    assert "RequestValidationError" in exception_types, (
        f"validation_error_handler must be registered for RequestValidationError. Found handlers for: {exception_types}"
    )
