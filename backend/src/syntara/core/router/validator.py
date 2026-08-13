"""Route validation logic."""

import inspect
import re
from typing import Any

import structlog
from fastapi import FastAPI

from .loader import EndpointDefinition, OpenAPISchema

logger = structlog.stdlib.get_logger("syntara.core.router.validator")


class ValidationError:
    """Represents a validation error."""

    def __init__(self, error_type: str, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize validation error with type, message, and optional details."""
        self.error_type = error_type
        self.message = message
        self.details = details or {}

    def __repr__(self) -> str:
        """Return string representation of validation error."""
        return f"<ValidationError {self.error_type}: {self.message}>"


class RouteInfo:
    """Information about a registered FastAPI route."""

    def __init__(self, route: Any) -> None:  # noqa: ANN401
        """Initialize route info from a FastAPI route or effective route context."""
        self.path = route.path
        self.methods = route.methods or set()
        self.name = route.name
        self.endpoint = route.endpoint

    @property
    def function_name(self) -> str:
        """Get the handler function name."""
        return self.endpoint.__name__ if self.endpoint is not None else ""

    @property
    def function_signature(self) -> inspect.Signature | None:
        """Get the handler function signature."""
        return inspect.signature(self.endpoint) if self.endpoint is not None else None

    @property
    def parameter_names(self) -> list[str]:
        """Get list of function parameter names (excluding 'self')."""
        if not self.function_signature:
            return []
        return [name for name in self.function_signature.parameters if name != "self"]

    def __repr__(self) -> str:
        """Return string representation of route."""
        methods_str = ",".join(sorted(self.methods))
        return f"<Route {methods_str} {self.path} -> {self.function_name}()>"


class RouteValidator:
    """Validates FastAPI routes against OpenAPI schemas."""

    def __init__(self, app: FastAPI, schemas: list[OpenAPISchema]) -> None:
        """Initialize validator with FastAPI app and OpenAPI schemas."""
        self.app = app
        self.schemas = schemas
        self.errors: list[ValidationError] = []

    def validate(self) -> list[ValidationError]:
        """Run all validation checks.

        Returns:
            List of validation errors found

        """
        self.errors = []

        logger.info("Starting route validation...")

        # Get all routes from FastAPI app
        routes = self._extract_routes()
        logger.info("Found registered routes in FastAPI app", route_count=len(routes))

        # Validate each schema
        for schema in self.schemas:
            logger.info("Validating schema", schema_filename=schema.filename)
            self._validate_schema(schema, routes)

        # Check for orphaned routes (routes without specs)
        self._validate_orphaned_routes(routes)

        return self.errors

    def _extract_routes(self) -> list[RouteInfo]:
        """Extract all routes from FastAPI app."""
        from syntara.core.router_discovery import iter_api_routes  # noqa: PLC0415

        return [RouteInfo(route) for route in iter_api_routes(self.app)]

    def _validate_schema(self, schema: OpenAPISchema, routes: list[RouteInfo]) -> None:
        """Validate a single schema against registered routes."""
        # First, validate API prefix for all paths in schema
        self._validate_api_prefix(schema)

        # Then validate each endpoint
        for endpoint in schema.endpoints:
            self._validate_endpoint(endpoint, schema, routes)

    def _validate_api_prefix(self, schema: OpenAPISchema) -> None:
        """Validate that all paths follow /api/v{version}/{domain} pattern.

        Combines the server base path with endpoint path before validation.
        This handles OpenAPI schemas where server URLs include the API prefix.

        For example:
        - Server URL: http://localhost:8000/api/v1
        - Endpoint path: /example
        - Combined path: /api/v1/example (validated)
        """
        pattern = re.compile(r"^/api/v\d+/" + re.escape(schema.domain) + r"(/.*)?$")
        base_path = schema.base_path

        for endpoint in schema.endpoints:
            # Combine base path from server URL with endpoint path
            full_path = f"{base_path}{endpoint.path}" if base_path else endpoint.path

            if not pattern.match(full_path):
                self.errors.append(
                    ValidationError(
                        error_type="invalid_api_prefix",
                        message=f"Invalid API prefix in {schema.filename}",
                        details={
                            "path": endpoint.path,
                            "full_path": full_path,
                            "base_path": base_path,
                            "method": endpoint.method.upper(),
                            "expected_pattern": f"/api/v{{version}}/{schema.domain}",
                            "domain": schema.domain,
                        },
                    )
                )

    def _validate_endpoint(
        self,
        endpoint: EndpointDefinition,
        schema: OpenAPISchema,
        routes: list[RouteInfo],
    ) -> None:
        """Validate a single endpoint from OpenAPI spec."""
        # Find matching route
        matching_route = self._find_matching_route(endpoint, schema, routes)

        if not matching_route:
            self._add_missing_handler_error(endpoint, schema)
            return

        # Validate function naming
        self._validate_function_naming(endpoint, matching_route, schema)

        # Validate parameters
        self._validate_parameters(endpoint, matching_route, schema)

    def _find_matching_route(
        self,
        endpoint: EndpointDefinition,
        schema: OpenAPISchema,
        routes: list[RouteInfo],
    ) -> RouteInfo | None:
        """Find route that matches the endpoint specification.

        Combines server base path with endpoint path to find the actual registered route.
        """
        # Combine base path with endpoint path to get the full registered path
        full_path = f"{schema.base_path}{endpoint.path}" if schema.base_path else endpoint.path

        for route in routes:
            if route.path == full_path and endpoint.method.upper() in route.methods:
                return route
        return None

    def _add_missing_handler_error(self, endpoint: EndpointDefinition, schema: OpenAPISchema) -> None:
        """Add error for missing handler implementation."""
        self.errors.append(
            ValidationError(
                error_type="missing_handler",
                message=f"Missing handler for {endpoint.method.upper()} {endpoint.path}",
                details={
                    "operation_id": endpoint.operation_id,
                    "expected_function": endpoint.expected_function_name + "()",
                    "expected_location": f"./app/{schema.domain}/router.py",
                    "schema_file": schema.filename,
                },
            )
        )

    def _validate_function_naming(
        self,
        endpoint: EndpointDefinition,
        route: RouteInfo,
        schema: OpenAPISchema,
    ) -> None:
        """Validate that function name matches operationId convention."""
        expected_name = endpoint.expected_function_name
        actual_name = route.function_name

        if expected_name != actual_name:
            self.errors.append(
                ValidationError(
                    error_type="function_name_mismatch",
                    message=f"Function name mismatch for {endpoint.method.upper()} {endpoint.path}",
                    details={
                        "expected": expected_name,
                        "actual": actual_name,
                        "operation_id": endpoint.operation_id,
                        "schema_file": schema.filename,
                    },
                )
            )

    def _validate_parameters(
        self,
        endpoint: EndpointDefinition,
        route: RouteInfo,
        schema: OpenAPISchema,
    ) -> None:
        """Validate that function signature includes required parameters."""
        required_params = set(endpoint.required_parameters)
        actual_params = set(route.parameter_names)

        # Check for missing required parameters
        missing_params = required_params - actual_params

        if missing_params:
            self.errors.append(
                ValidationError(
                    error_type="missing_parameters",
                    message=f"Missing parameters in {route.function_name}()",
                    details={
                        "missing": sorted(missing_params),
                        "expected": sorted(required_params),
                        "actual": sorted(actual_params),
                        "path": endpoint.path,
                        "method": endpoint.method.upper(),
                        "schema_file": schema.filename,
                    },
                )
            )

    def _validate_orphaned_routes(self, routes: list[RouteInfo]) -> None:
        """Check for routes that don't have corresponding OpenAPI specs."""
        # Build set of all spec endpoints for quick lookup
        # Combine server base path with endpoint path to get full registered path
        spec_endpoints: set[tuple[str, str]] = set()
        for schema in self.schemas:
            for endpoint in schema.endpoints:
                full_path = f"{schema.base_path}{endpoint.path}" if schema.base_path else endpoint.path
                spec_endpoints.add((full_path, endpoint.method.upper()))

        # Check each route
        for route in routes:
            for method in route.methods:
                endpoint_key = (route.path, method)
                if endpoint_key not in spec_endpoints:
                    # Try to find which schema this should belong to
                    domain = self._extract_domain_from_path(route.path)

                    self.errors.append(
                        ValidationError(
                            error_type="orphaned_handler",
                            message=f"Orphaned handler: {method} {route.path}",
                            details={
                                "function": route.function_name + "()",
                                "path": route.path,
                                "method": method,
                                "inferred_domain": domain,
                                "message": "No corresponding OpenAPI specification found",
                            },
                        )
                    )

    def _extract_domain_from_path(self, path: str) -> str | None:
        """Extract domain from API path (e.g., /api/v1/example -> example)."""
        match = re.match(r"^/api/v\d+/([^/]+)", path)
        return match.group(1) if match else None


def log_validation_errors(errors: list[ValidationError]) -> None:
    """Log validation errors in a structured, readable format."""
    if not errors:
        logger.info("✓ All routes validated successfully")
        return

    logger.warning("=" * 80)
    logger.warning("VALIDATION ERRORS: Found issues", issue_count=len(errors))
    logger.warning("=" * 80)

    # Group errors by type
    errors_by_type: dict[str, list[ValidationError]] = {}
    for error in errors:
        if error.error_type not in errors_by_type:
            errors_by_type[error.error_type] = []
        errors_by_type[error.error_type].append(error)

    # Log each error type group
    for error_type, error_list in errors_by_type.items():
        logger.warning("Error type summary", error_type=error_type.upper().replace("_", " "), count=len(error_list))
        logger.warning("-" * 80)

        for error in error_list:
            logger.error("Validation error", message=error.message)
            for key, value in error.details.items():
                logger.error("Error detail", key=key, value=value)
            logger.error("")

    logger.warning("=" * 80)
    logger.warning("Application starting despite validation errors (non-blocking mode)", error_count=len(errors))
    logger.warning("=" * 80)
