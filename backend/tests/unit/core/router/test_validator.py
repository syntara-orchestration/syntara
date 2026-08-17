"""Unit tests for router validator.

- Validation rules and business logic
- Route matching and parameter validation
- Error detection and reporting
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from syntara.core.router.loader import EndpointDefinition, OpenAPISchema
from syntara.core.router.validator import (
    RouteInfo,
    RouteValidator,
    ValidationError,
    log_validation_errors,
)

# ============================================================================
# ValidationError Tests
# ============================================================================


class TestValidationError:
    """Tests for ValidationError class."""

    @pytest.mark.parametrize(
        ("details", "expected"),
        [
            ({"key": "value"}, {"key": "value"}),
            (None, {}),
        ],
        ids=["with-details", "without-details"],
    )
    def test_initialization(self, details: dict[str, str] | None, expected: dict[str, str]) -> None:
        """Test ValidationError initialization with and without details."""
        error = ValidationError(
            error_type="test_error",
            message="Test message",
            details=details,
        )

        assert error.error_type == "test_error"
        assert error.message == "Test message"
        assert error.details == expected

    def test_string_representation(self) -> None:
        """Test ValidationError string representation for debugging."""
        error = ValidationError("missing_handler", "Handler not found")

        repr_str = repr(error)

        assert "ValidationError" in repr_str
        assert "missing_handler" in repr_str
        assert "Handler not found" in repr_str


# ============================================================================
# RouteInfo Tests
# ============================================================================


class TestRouteInfo:
    """Tests for RouteInfo class."""

    def test_route_info_properties(self) -> None:
        """Test RouteInfo extracts properties correctly from FastAPI route."""

        async def test_handler(param1: str, param2: int) -> dict[str, str]:
            return {"test": "data"}

        route = APIRoute(
            path="/api/v1/test",
            endpoint=test_handler,
            methods=["GET", "POST"],
            name="test_route",
        )

        route_info = RouteInfo(route)

        assert route_info.path == "/api/v1/test"
        assert route_info.methods == {"GET", "POST"}
        assert route_info.name == "test_route"
        assert route_info.function_name == "test_handler"
        assert route_info.function_signature is not None
        assert route_info.parameter_names == ["param1", "param2"]

    def test_parameter_names_excludes_self(self) -> None:
        """Test that parameter_names excludes 'self' parameter."""

        async def method(self, param1: str) -> dict[str, str]:
            return {}

        route = APIRoute(path="/test", endpoint=method, methods=["GET"])
        route_info = RouteInfo(route)

        assert "self" not in route_info.parameter_names
        assert "param1" in route_info.parameter_names

    def test_handles_none_endpoint(self) -> None:
        """Test RouteInfo handles None endpoint gracefully."""
        route = MagicMock()
        route.path = "/test"
        route.methods = {"GET"}
        route.name = "test"
        route.endpoint = None

        route_info = RouteInfo(route)

        assert route_info.function_name == ""
        assert route_info.parameter_names == []


# ============================================================================
# RouteValidator Tests
# ============================================================================


class TestRouteValidator:
    """Tests for RouteValidator class."""

    # ------------------------------------------------------------------------
    # API Prefix Validation
    # ------------------------------------------------------------------------

    @pytest.mark.parametrize(
        ("path", "domain", "should_pass"),
        [
            ("/api/v1/example/test", "example", True),
            ("/api/v2/workflows/run", "workflows", True),
            ("/api/v1/example/nested/path/test", "example", True),
            ("/api/v1/wrong/test", "example", False),
            ("/api/v1/test", "example", False),
            ("/test", "example", False),
        ],
        ids=[
            "valid-v1",
            "valid-v2",
            "valid-nested",
            "wrong-domain",
            "missing-domain",
            "no-api-prefix",
        ],
    )
    def test_validate_api_prefix(self, path: str, domain: str, *, should_pass: bool) -> None:
        """Test API prefix validation with various path patterns."""
        app = FastAPI()
        validator = RouteValidator(app, [])

        mock_schema = MagicMock(spec=OpenAPISchema)
        mock_schema.filename = f"{domain}.yaml"
        mock_schema.domain = domain
        mock_schema.base_path = ""  # No server base path

        endpoint = MagicMock(spec=EndpointDefinition)
        endpoint.path = path
        endpoint.method = "get"

        mock_schema.endpoints = [endpoint]

        validator._validate_api_prefix(mock_schema)

        if should_pass:
            assert len(validator.errors) == 0
        else:
            assert len(validator.errors) == 1
            assert validator.errors[0].error_type == "invalid_api_prefix"

    @pytest.mark.parametrize(
        ("endpoint_path", "base_path", "domain", "should_pass"),
        [
            # With server base path /api/v1
            ("/example", "/api/v1", "example", True),
            ("/example/items", "/api/v1", "example", True),
            ("/example/{id}", "/api/v1", "example", True),
            # With different base path /api/v2
            ("/workflows", "/api/v2", "workflows", True),
            # Without server base path (absolute paths)
            ("/api/v1/example", "", "example", True),
            ("/api/v2/workflows", "", "workflows", True),
            # Should fail - wrong domain
            ("/other", "/api/v1", "example", False),
            ("/api/v1/other", "", "example", False),
            # Should fail - missing prefix entirely
            ("/example", "", "example", False),
        ],
        ids=[
            "relative-with-base",
            "relative-with-base-subpath",
            "relative-with-base-param",
            "different-version",
            "absolute-no-base-v1",
            "absolute-no-base-v2",
            "wrong-domain-with-base",
            "wrong-domain-no-base",
            "missing-prefix",
        ],
    )
    def test_validate_api_prefix_with_server_base_path(
        self,
        endpoint_path: str,
        base_path: str,
        domain: str,
        *,
        should_pass: bool,
    ) -> None:
        """Test API prefix validation combines server base path with endpoint path."""
        app = FastAPI()
        validator = RouteValidator(app, [])

        mock_schema = MagicMock(spec=OpenAPISchema)
        mock_schema.filename = f"{domain}/openapi.json"
        mock_schema.domain = domain
        mock_schema.base_path = base_path

        endpoint = MagicMock(spec=EndpointDefinition)
        endpoint.path = endpoint_path
        endpoint.method = "get"

        mock_schema.endpoints = [endpoint]

        validator._validate_api_prefix(mock_schema)

        if should_pass:
            assert len(validator.errors) == 0, f"Expected no errors for {base_path}{endpoint_path}"
        else:
            assert len(validator.errors) == 1
            assert validator.errors[0].error_type == "invalid_api_prefix"
            error_details = validator.errors[0].details
            assert "full_path" in error_details
            assert "base_path" in error_details

    # ------------------------------------------------------------------------
    # Route Matching
    # ------------------------------------------------------------------------

    @pytest.mark.parametrize(
        ("registered_path", "registered_method", "search_path", "search_method", "should_match"),
        [
            ("/api/v1/test", "GET", "/api/v1/test", "get", True),
            ("/api/v1/test", "GET", "/api/v1/other", "get", False),
            ("/api/v1/test", "GET", "/api/v1/test", "post", False),
        ],
        ids=["exact-match", "path-mismatch", "method-mismatch"],
    )
    def test_find_matching_route(
        self,
        registered_path: str,
        registered_method: str,
        search_path: str,
        search_method: str,
        *,
        should_match: bool,
    ) -> None:
        """Test route matching with various path and method combinations."""
        app = FastAPI()

        # Register route with specific method
        if registered_method == "GET":

            @app.get(registered_path)
            async def handler() -> dict[str, str]:
                return {}
        else:

            @app.post(registered_path)
            async def handler() -> dict[str, str]:
                return {}

        validator = RouteValidator(app, [])
        routes = validator._extract_routes()

        mock_schema = MagicMock(spec=OpenAPISchema)
        mock_schema.base_path = ""  # No base path for this test

        endpoint = MagicMock(spec=EndpointDefinition)
        endpoint.path = search_path
        endpoint.method = search_method

        matching_route = validator._find_matching_route(endpoint, mock_schema, routes)

        if should_match:
            assert matching_route is not None
            assert matching_route.path == search_path
        else:
            assert matching_route is None

    # ------------------------------------------------------------------------
    # Parameter Validation
    # ------------------------------------------------------------------------

    @pytest.mark.parametrize(
        ("handler_params", "required_params", "should_pass", "expected_missing"),
        [
            (["param1", "param2"], ["param1", "param2"], True, []),
            (["param1"], ["param1", "param2"], False, ["param2"]),
            (["param1", "param2", "extra"], ["param1", "param2"], True, []),
        ],
        ids=["all-present", "missing-required", "extra-params-ok"],
    )
    def test_validate_parameters(
        self,
        handler_params: list[str],
        required_params: list[str],
        *,
        should_pass: bool,
        expected_missing: list[str],
    ) -> None:
        """Test parameter validation with various combinations."""
        app = FastAPI()

        # Build handler dynamically based on handler_params
        param_str = ", ".join([f"{p}: str" for p in handler_params])
        handler_code = f"async def get_test({param_str}) -> dict[str, str]: return {{}}"

        # Execute to create function
        namespace: dict[str, Any] = {}
        exec(handler_code, namespace)  # noqa: S102
        handler = namespace["get_test"]

        # Type assert to fix mypy warning
        assert callable(handler), "Handler must be callable"

        app.add_api_route("/api/v1/example/test", handler, methods=["GET"])

        validator = RouteValidator(app, [])
        routes = validator._extract_routes()
        route = next(r for r in routes if r.path == "/api/v1/example/test")

        mock_schema = MagicMock(spec=OpenAPISchema)
        mock_schema.filename = "example.yaml"

        endpoint = MagicMock(spec=EndpointDefinition)
        endpoint.required_parameters = required_params
        endpoint.method = "get"
        endpoint.path = "/api/v1/example/test"

        validator._validate_parameters(endpoint, route, mock_schema)

        if should_pass:
            assert len(validator.errors) == 0
        else:
            assert len(validator.errors) == 1
            assert validator.errors[0].error_type == "missing_parameters"
            assert set(validator.errors[0].details["missing"]) == set(expected_missing)

    # ------------------------------------------------------------------------
    # Business Logic Tests
    # ------------------------------------------------------------------------

    def test_validate_returns_empty_list_when_valid(self) -> None:
        """Test that validate returns empty list when all routes are valid."""
        app = FastAPI()

        @app.get("/api/v1/example/test")
        async def get_test() -> dict[str, str]:
            return {"test": "data"}

        mock_schema = MagicMock(spec=OpenAPISchema)
        mock_schema.filename = "example.yaml"
        mock_schema.domain = "example"
        mock_schema.base_path = ""  # No server base path

        endpoint = MagicMock(spec=EndpointDefinition)
        endpoint.path = "/api/v1/example/test"
        endpoint.method = "get"
        endpoint.operation_id = "getTest"
        endpoint.expected_function_name = "get_test"
        endpoint.required_parameters = []
        endpoint.parameters = []

        mock_schema.endpoints = [endpoint]

        validator = RouteValidator(app, [mock_schema])
        errors = validator.validate()

        assert errors == []

    def test_missing_handler_error(self) -> None:
        """Test that missing handler error is added correctly."""
        app = FastAPI()
        validator = RouteValidator(app, [])

        mock_schema = MagicMock(spec=OpenAPISchema)
        mock_schema.filename = "example.yaml"
        mock_schema.domain = "example"

        endpoint = MagicMock(spec=EndpointDefinition)
        endpoint.path = "/api/v1/example/test"
        endpoint.method = "get"
        endpoint.operation_id = "getTest"
        endpoint.expected_function_name = "get_test"

        validator._add_missing_handler_error(endpoint, mock_schema)

        assert len(validator.errors) == 1
        assert validator.errors[0].error_type == "missing_handler"
        assert "get_test()" in validator.errors[0].details["expected_function"]

    def test_function_naming_validation(self) -> None:
        """Test function naming validation detects mismatches."""
        app = FastAPI()

        @app.get("/api/v1/example/test")
        async def wrong_name() -> dict[str, str]:
            return {}

        validator = RouteValidator(app, [])
        routes = validator._extract_routes()
        route = next(r for r in routes if r.path == "/api/v1/example/test")

        mock_schema = MagicMock(spec=OpenAPISchema)
        mock_schema.filename = "example.yaml"

        endpoint = MagicMock(spec=EndpointDefinition)
        endpoint.expected_function_name = "get_test"
        endpoint.operation_id = "getTest"
        endpoint.method = "get"
        endpoint.path = "/api/v1/example/test"

        validator._validate_function_naming(endpoint, route, mock_schema)

        assert len(validator.errors) == 1
        assert validator.errors[0].error_type == "function_name_mismatch"
        assert validator.errors[0].details["expected"] == "get_test"
        assert validator.errors[0].details["actual"] == "wrong_name"

    def test_orphaned_route_detection(self) -> None:
        """Test that orphaned routes (routes without specs) are detected."""
        app = FastAPI()

        @app.get("/api/v1/example/orphaned")
        async def orphaned_handler() -> dict[str, str]:
            return {}

        validator = RouteValidator(app, [])
        routes = validator._extract_routes()

        mock_schema = MagicMock(spec=OpenAPISchema)
        mock_schema.endpoints = []

        validator.schemas = [mock_schema]
        validator._validate_orphaned_routes(routes)

        orphaned_errors = [e for e in validator.errors if e.error_type == "orphaned_handler"]
        assert any("/api/v1/example/orphaned" in e.details.get("path", "") for e in orphaned_errors)

    @pytest.mark.parametrize(
        ("path", "expected_domain"),
        [
            ("/api/v1/example/test", "example"),
            ("/api/v2/workflows/run", "workflows"),
            ("/api/v1/users", "users"),
            ("/test", None),
            ("/api/test", None),
            ("", None),
        ],
        ids=["v1-example", "v2-workflows", "v1-users", "no-api", "no-version", "empty"],
    )
    def test_extract_domain_from_path(self, path: str, expected_domain: str | None) -> None:
        """Test domain extraction from various path patterns."""
        app = FastAPI()
        validator = RouteValidator(app, [])

        domain = validator._extract_domain_from_path(path)

        assert domain == expected_domain

    def test_full_validation_with_multiple_error_types(self) -> None:
        """Test full validation flow detects multiple error types."""
        app = FastAPI()

        @app.get("/api/v1/example/test1")
        async def wrong_name() -> dict[str, str]:
            return {}

        @app.get("/api/v1/example/test2")
        async def get_test2(param1: str) -> dict[str, str]:
            return {}

        @app.get("/api/v1/example/orphaned")
        async def orphaned_route() -> dict[str, str]:
            return {}

        mock_schema = MagicMock(spec=OpenAPISchema)
        mock_schema.filename = "example.yaml"
        mock_schema.domain = "example"
        mock_schema.base_path = ""  # No base path

        endpoint1 = MagicMock(spec=EndpointDefinition)
        endpoint1.path = "/api/v1/example/test1"
        endpoint1.method = "get"
        endpoint1.operation_id = "getTest1"
        endpoint1.expected_function_name = "get_test1"
        endpoint1.required_parameters = []

        endpoint2 = MagicMock(spec=EndpointDefinition)
        endpoint2.path = "/api/v1/example/test2"
        endpoint2.method = "get"
        endpoint2.operation_id = "getTest2"
        endpoint2.expected_function_name = "get_test2"
        endpoint2.required_parameters = ["param1", "param2"]

        endpoint3 = MagicMock(spec=EndpointDefinition)
        endpoint3.path = "/api/v1/example/missing"
        endpoint3.method = "get"
        endpoint3.operation_id = "getMissing"
        endpoint3.expected_function_name = "get_missing"
        endpoint3.required_parameters = []

        mock_schema.endpoints = [endpoint1, endpoint2, endpoint3]

        validator = RouteValidator(app, [mock_schema])
        errors = validator.validate()

        error_types = {e.error_type for e in errors}
        assert "function_name_mismatch" in error_types
        assert "missing_parameters" in error_types
        assert "missing_handler" in error_types
        assert "orphaned_handler" in error_types


# ============================================================================
# Logging Tests
# ============================================================================


class TestLogValidationErrors:
    """Tests for log_validation_errors function."""

    def test_no_errors_logs_success(self) -> None:
        """Test logging when there are no errors."""
        with patch("syntara.core.router.validator.logger") as mock_logger:
            log_validation_errors([])

            # Verify logger.info was called with success message
            mock_logger.info.assert_called_once()
            assert "All routes validated successfully" in mock_logger.info.call_args[0][0]

    def test_logs_errors_with_grouping(self) -> None:
        """Test that errors are logged and grouped by type."""
        errors = [
            ValidationError("missing_handler", "Handler 1 not found"),
            ValidationError("missing_handler", "Handler 2 not found"),
            ValidationError("function_name_mismatch", "Name mismatch"),
        ]

        with patch("syntara.core.router.validator.logger") as mock_logger:
            log_validation_errors(errors)

            # Verify logger.warning was called with error summary (uses format strings)
            warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
            warning_str = " ".join(warning_calls)

            assert "VALIDATION ERRORS" in warning_str
            assert "Found %d issue" in warning_str or "3" in warning_str
            assert "MISSING HANDLER" in warning_str
            assert "FUNCTION NAME MISMATCH" in warning_str

    def test_logs_error_details(self) -> None:
        """Test that error details are logged."""
        error = ValidationError(
            error_type="missing_handler",
            message="Handler not found",
            details={
                "path": "/api/v1/test",
                "expected_function": "get_test()",
                "schema_file": "example.yaml",
            },
        )

        with patch("syntara.core.router.validator.logger") as mock_logger:
            log_validation_errors([error])

            # Verify logger.error was called with error details (uses format strings)
            error_calls = [str(call) for call in mock_logger.error.call_args_list]
            error_str = " ".join(error_calls)

            assert "/api/v1/test" in error_str
            assert "get_test()" in error_str
            assert "example.yaml" in error_str
