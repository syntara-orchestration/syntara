"""Unit tests for router loader.

- OpenAPI schema loading (JSON/YAML formats)
- Endpoint parsing and extraction
- Parameter handling (path, query, required/optional)
- Error handling for invalid schemas
- camelCase to snake_case conversion
- Domain extraction from filenames
"""

from typing import Any
from unittest.mock import patch

import pytest

from syntara.core.router.loader import (
    EndpointDefinition,
    OpenAPISchema,
    load_openapi_schema,
    load_schemas,
)

# ============================================================================
# EndpointDefinition Tests
# ============================================================================


class TestEndpointDefinition:
    """Tests for EndpointDefinition class."""

    def test_initialization_and_properties(self) -> None:
        """Test EndpointDefinition initialization and all properties."""
        parameters = [
            {"name": "id", "in": "path", "required": True},
            {"name": "filter", "in": "query", "required": False},
        ]
        request_body = {"required": True, "content": {}}

        endpoint = EndpointDefinition(
            path="/api/v1/test",
            method="GET",  # Should normalize to lowercase
            operation_id="getTest",
            parameters=parameters,
            request_body=request_body,
        )

        # Basic properties
        assert endpoint.path == "/api/v1/test"
        assert endpoint.method == "get"  # Normalized
        assert endpoint.operation_id == "getTest"
        assert endpoint.parameters == parameters
        assert endpoint.request_body == request_body

        # String representation
        repr_str = repr(endpoint)
        assert "Endpoint" in repr_str
        assert "GET" in repr_str  # Uppercase in repr
        assert "/api/v1/test" in repr_str

    @pytest.mark.parametrize(
        ("operation_id", "expected_name"),
        [
            ("getExample", "get_example"),
            ("createExampleItem", "create_example_item"),
            ("UpdateUserProfile", "update_user_profile"),
            ("simple", "simple"),
            ("getHTTPStatus", "get_httpstatus"),  # Consecutive caps stay together
            ("getV1API", "get_v1api"),
            ("handleCAPS", "handle_caps"),
        ],
        ids=["camelCase", "multi-word", "PascalCase", "lowercase", "consecutive-caps", "version-caps", "mixed-caps"],
    )
    def test_expected_function_name_conversion(self, operation_id: str, expected_name: str) -> None:
        """Test camelCase to snake_case conversion for function names."""
        endpoint = EndpointDefinition(path="/test", method="get", operation_id=operation_id, parameters=[])

        assert endpoint.expected_function_name == expected_name

    @pytest.mark.parametrize(
        ("parameters", "expected_path", "expected_query"),
        [
            (
                [{"name": "id", "in": "path"}],
                ["id"],
                [],
            ),
            (
                [{"name": "id", "in": "path"}, {"name": "slug", "in": "path"}],
                ["id", "slug"],
                [],
            ),
            (
                [{"name": "filter", "in": "query"}],
                [],
                ["filter"],
            ),
            (
                [{"name": "id", "in": "path"}, {"name": "q", "in": "query"}],
                ["id"],
                ["q"],
            ),
            ([], [], []),
        ],
        ids=["single-path", "multiple-path", "only-query", "mixed", "empty"],
    )
    def test_parameter_filtering(
        self,
        parameters: list[dict[str, str]],
        expected_path: list[str],
        expected_query: list[str],
    ) -> None:
        """Test path and query parameter extraction."""
        endpoint = EndpointDefinition(path="/test", method="get", operation_id="getTest", parameters=parameters)

        assert endpoint.path_parameters == expected_path
        assert endpoint.query_parameters == expected_query

    @pytest.mark.parametrize(
        ("parameters", "expected_required"),
        [
            ([{"name": "id", "required": True}], ["id"]),
            ([{"name": "id", "required": False}], []),
            ([{"name": "id", "in": "path"}], ["id"]),  # Path param without required field defaults to True
            ([{"name": "q", "in": "query"}], []),  # Query param without required field defaults to False
            (
                [
                    {"name": "a", "required": True},
                    {"name": "b", "required": False},
                    {"name": "c", "in": "path"},  # Path param defaults to required
                    {"name": "d", "in": "query"},  # Query param defaults to optional
                ],
                ["a", "c"],
            ),
            ([], []),
        ],
        ids=[
            "explicit-true",
            "explicit-false",
            "path-param-defaults-required",
            "query-param-defaults-optional",
            "mixed",
            "empty",
        ],
    )
    def test_required_parameters(self, parameters: list[dict[str, Any]], expected_required: list[str]) -> None:
        """Test required parameter extraction.

        Per OpenAPI 3.0 specification:
        - Path parameters without 'required' field default to True (required)
        - Query/header/cookie parameters without 'required' field default to False (optional)
        """
        endpoint = EndpointDefinition(path="/test", method="get", operation_id="getTest", parameters=parameters)

        assert endpoint.required_parameters == expected_required


# ============================================================================
# OpenAPISchema Tests
# ============================================================================


class TestOpenAPISchema:
    """Tests for OpenAPISchema class."""

    def test_schema_parsing_and_properties(self) -> None:
        """Test OpenAPISchema initialization, endpoint parsing, and properties."""
        schema_data = {
            "openapi": "3.0.3",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/api/v1/test": {
                    "get": {
                        "operationId": "getTest",
                        "parameters": [{"name": "id", "in": "path", "required": True}],
                    }
                }
            },
        }

        schema = OpenAPISchema("example/openapi.json", schema_data)

        # Basic properties
        assert schema.filename == "example/openapi.json"
        assert schema.schema_data == schema_data
        assert len(schema.endpoints) == 1

        # Endpoint parsing
        endpoint = schema.endpoints[0]
        assert endpoint.path == "/api/v1/test"
        assert endpoint.method == "get"
        assert endpoint.operation_id == "getTest"

        # String representation
        repr_str = repr(schema)
        assert "OpenAPISchema" in repr_str
        assert "example/openapi.json" in repr_str
        assert "1 endpoint" in repr_str

    @pytest.mark.parametrize(
        ("filename", "expected_domain"),
        [
            ("example/openapi.json", "example"),
            ("example/openapi.yaml", "example"),
            ("example/openapi.yml", "example"),
            ("workflows/openapi.json", "workflows"),
            ("agent_orchestrator/openapi.yaml", "agent_orchestrator"),
            ("example.json", "example"),
            ("workflows.yaml", "workflows"),
            # Ancillary router prefix support
            ("example/sub_openapi.json", "sub"),
            ("workflows/admin_openapi.yaml", "admin"),
            ("domain/custom_openapi.yml", "custom"),
        ],
        ids=[
            "dir-json",
            "dir-yaml",
            "dir-yml",
            "workflows-dir",
            "underscore-dir",
            "flat-json",
            "flat-yaml",
            "sub-prefix-json",
            "admin-prefix-yaml",
            "custom-prefix-yml",
        ],
    )
    def test_domain_extraction(self, filename: str, expected_domain: str) -> None:
        """Test domain extraction from various filename patterns."""
        schema_data = {
            "openapi": "3.0.3",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {},
        }

        schema = OpenAPISchema(filename, schema_data)

        assert schema.domain == expected_domain

    @pytest.mark.parametrize(
        ("servers", "expected_base_path"),
        [
            # Single server with base path
            ([{"url": "http://localhost:8000/api/v1"}], "/api/v1"),
            ([{"url": "https://prod.example.com/api/v2"}], "/api/v2"),
            # Multiple servers with same base path
            (
                [
                    {"url": "http://localhost:8000/api/v1"},
                    {"url": "https://prod.example.com/api/v1"},
                ],
                "/api/v1",
            ),
            # Multiple servers with different versions (common prefix)
            (
                [
                    {"url": "http://localhost:8000/api/v1"},
                    {"url": "https://prod.example.com/api/v2"},
                ],
                "/api",
            ),
            # No servers (edge case - should return empty string)
            ([], ""),
            # Servers without paths (edge case)
            ([{"url": "http://localhost:8000"}], ""),
            # Mixed - some with paths, some without
            (
                [
                    {"url": "http://localhost:8000/api/v1"},
                    {"url": "https://prod.example.com"},
                ],
                "",
            ),
            # Trailing slashes should be removed
            ([{"url": "http://localhost:8000/api/v1/"}], "/api/v1"),
        ],
        ids=[
            "single-v1",
            "single-v2",
            "multiple-same-base",
            "multiple-different-versions",
            "no-servers",
            "servers-no-paths",
            "mixed-servers",
            "trailing-slash",
        ],
    )
    def test_base_path_extraction(self, servers: list[dict[str, str]], expected_base_path: str) -> None:
        """Test base path extraction from server URLs."""
        schema_data = {
            "openapi": "3.0.3",
            "info": {"title": "Test", "version": "1.0.0"},
            "servers": servers,
            "paths": {},
        }

        schema = OpenAPISchema("test.json", schema_data)

        assert schema.base_path == expected_base_path

    def test_multiple_http_methods_per_path(self) -> None:
        """Test parsing endpoints when a path has multiple HTTP methods."""
        schema_data = {
            "openapi": "3.0.3",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {
                "/api/v1/items": {
                    "get": {"operationId": "listItems"},
                    "post": {"operationId": "createItem"},
                    "delete": {"operationId": "deleteAllItems"},
                }
            },
        }

        schema = OpenAPISchema("test.json", schema_data)

        assert len(schema.endpoints) == 3
        methods = {endpoint.method for endpoint in schema.endpoints}
        assert methods == {"get", "post", "delete"}

    def test_missing_operation_id_handling(self) -> None:
        """Test that endpoints without operationId are skipped with warning."""
        schema_data = {
            "openapi": "3.0.3",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {
                "/api/v1/valid": {"get": {"operationId": "getValid"}},
                "/api/v1/invalid": {"get": {}},  # Missing operationId
            },
        }

        with patch("syntara.core.router.loader.logger") as mock_logger:
            schema = OpenAPISchema("test.json", schema_data)

        assert len(schema.endpoints) == 1
        assert schema.endpoints[0].operation_id == "getValid"

        # Verify logger.warning was called with the expected message
        mock_logger.warning.assert_called_once()
        assert "Missing operationId" in mock_logger.warning.call_args[0][0]

    def test_request_body_and_empty_paths(self) -> None:
        """Test request body parsing and handling of empty paths."""
        # Test with request body
        schema_with_body = OpenAPISchema(
            "test.json",
            {
                "openapi": "3.0.3",
                "info": {"title": "Test", "version": "1.0.0"},
                "paths": {
                    "/api/v1/items": {
                        "post": {
                            "operationId": "createItem",
                            "requestBody": {
                                "required": True,
                                "content": {"application/json": {"schema": {"type": "object"}}},
                            },
                        }
                    }
                },
            },
        )

        assert len(schema_with_body.endpoints) == 1
        assert schema_with_body.endpoints[0].request_body is not None
        assert schema_with_body.endpoints[0].request_body["required"] is True

        # Test with empty paths
        schema_empty = OpenAPISchema(
            "test.json",
            {"openapi": "3.0.3", "info": {"title": "Test", "version": "1.0.0"}, "paths": {}},
        )

        assert len(schema_empty.endpoints) == 0


# ============================================================================
# Schema Loading Tests
# ============================================================================


class TestLoadOpenAPISchema:
    """Tests for load_openapi_schema function."""

    def test_load_existing_schema(self) -> None:
        """Test loading an existing schema from the project."""
        schema = load_openapi_schema("projects/openapi.yaml")

        assert schema is not None
        assert schema.filename == "projects/openapi.yaml"
        assert schema.domain == "projects"
        assert len(schema.endpoints) > 0

    def test_error_handling(self) -> None:
        """Test various error conditions return None with appropriate logging."""
        with patch("syntara.core.router.loader.logger") as mock_logger:
            # File not found
            schema = load_openapi_schema("nonexistent_test_file_12345.json")
            assert schema is None

            # Verify logger.error was called with "not found" message
            assert mock_logger.error.called
            call_args_str = str(mock_logger.error.call_args)
            assert "not found" in call_args_str

        # Invalid schema structure (missing required fields) - OpenAPISchema handles gracefully
        schema_data = {"invalid": "structure"}
        schema = OpenAPISchema("test.json", schema_data)
        assert len(schema.endpoints) == 0  # No endpoints in invalid structure

    def test_format_support(self) -> None:
        """Test that both JSON and YAML formats are supported."""
        json_data = {
            "openapi": "3.0.3",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {"/test": {"get": {"operationId": "getTest"}}},
        }

        # Both JSON and YAML use the same data structure internally
        json_schema = OpenAPISchema("test.json", json_data)
        yaml_schema = OpenAPISchema("test.yaml", json_data)

        assert len(json_schema.endpoints) == 1
        assert len(yaml_schema.endpoints) == 1
        assert json_schema.endpoints[0].operation_id == yaml_schema.endpoints[0].operation_id


class TestLoadSchemas:
    """Tests for load_schemas batch loading function."""

    def test_batch_loading_scenarios(self) -> None:
        """Test batch loading with various scenarios."""
        # Single valid schema
        schemas = load_schemas(["projects/openapi.yaml"])
        assert len(schemas) == 1
        assert schemas[0].domain == "projects"

        # Partial failures (1 valid, 1 invalid)
        with patch("syntara.core.router.loader.logger") as mock_logger:
            schemas = load_schemas(["projects/openapi.yaml", "nonexistent_test_12345.json"])
            assert len(schemas) == 1

            # Verify logger.info was called with the summary message (uses kwargs format)
            assert mock_logger.info.called
            call_args = mock_logger.info.call_args
            assert "Loaded schema files successfully" in call_args[0][0]
            assert call_args[1]["loaded_count"] == 1  # successful
            assert call_args[1]["total_count"] == 2  # total

        # All failures
        with patch("syntara.core.router.loader.logger") as mock_logger:
            schemas = load_schemas(["nonexistent1_test.json", "nonexistent2_test.json"])
            assert schemas == []

            # Verify logger.info was called with the summary message (uses kwargs format)
            assert mock_logger.info.called
            call_args = mock_logger.info.call_args
            assert "Loaded schema files successfully" in call_args[0][0]
            assert call_args[1]["loaded_count"] == 0  # successful
            assert call_args[1]["total_count"] == 2  # total

        # Empty list
        schemas = load_schemas([])
        assert schemas == []

    def test_ancillary_router_domain_extraction(self) -> None:
        """Test domain extraction for ancillary routers with prefixes."""
        schema_data = {
            "openapi": "3.0.3",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {},
        }

        # Test various prefix patterns
        test_cases = [
            ("domain/sub_openapi.json", "sub"),
            ("workflows/admin_openapi.yaml", "admin"),
            ("api/custom_openapi.yml", "custom"),
            ("example/test_openapi.json", "test"),
        ]

        for filename, expected_domain in test_cases:
            schema = OpenAPISchema(filename, schema_data)
            assert schema.domain == expected_domain, f"Failed for {filename}"
